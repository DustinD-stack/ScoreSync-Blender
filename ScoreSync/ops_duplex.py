import bpy, time
from .ops_connection import _get_mido, DEV, _get_bpm, _claim_blender_master, _blender_is_master

# Internal state for scrubbing detection
_LAST_FRAME = None
_LAST_CHANGE_TS = 0.0
_SENDING = False
_TIMER_RUNNING = False

# ------------------ MTC helpers ------------------
# Build hh:mm:ss:ff from current Blender frame using chosen MTC fps (24/25/30).
def _frame_to_tc(frame: int, mtc_fps: int, scene_fps: float):
    if scene_fps <= 0:
        scene_fps = 30.0
    seconds = max(0.0, float(frame) / float(scene_fps))
    hh = int(seconds // 3600)
    seconds -= hh * 3600
    mm = int(seconds // 60)
    seconds -= mm * 60
    ss = int(seconds)
    frac = seconds - ss
    ff = int(round(frac * mtc_fps))
    # clamp to frame range for the chosen mtc_fps
    if ff >= mtc_fps:
        ff = 0
        ss += 1
        if ss >= 60:
            ss = 0
            mm += 1
            if mm >= 60:
                mm = 0
                hh += 1
    return hh & 0x1F, mm & 0x3F, ss & 0x3F, ff & 0x1F  # mask to valid ranges

# Send one full 8-nibble Quarter-Frame burst representing current timecode
def _send_mtc_burst(hh: int, mm: int, ss: int, ff: int, mtc_fps: int) -> bool:
    mido = _get_mido()
    if not mido or not DEV.out_port:
        return False
    # FPS flag lives in the high bits of the hours nibble in message 7.
    fps_flag = {24: 0b00, 25: 0b01, 30: 0b11}.get(mtc_fps, 0b11)
    try:
        # QF 0..7: (type, value)
        qfs = [
            (0, (ff     ) & 0x0F),                # frames low
            (1, (ff >> 4) & 0x01),                # frames high (bit 4)
            (2, (ss     ) & 0x0F),                # seconds low
            (3, (ss >> 4) & 0x03),                # seconds high (bits 4-5)
            (4, (mm     ) & 0x0F),                # minutes low
            (5, (mm >> 4) & 0x03),                # minutes high
            (6, (hh     ) & 0x0F),                # hours low
            (7, ((hh >> 4) & 0x01) | (fps_flag << 1)),  # hours high + fps flag
        ]
        for ft, val in qfs:
            DEV.out_port.send(mido.Message('quarter_frame', frame_type=ft, value=val))
        return True
    except Exception:
        return False

def _scene_fps(scene) -> float:
    # Blender FPS can be fps / fps_base
    fps = float(getattr(scene.render, "fps", 30) or 30)
    fps_base = float(getattr(scene.render, "fps_base", 1.0) or 1.0)
    return fps / fps_base if fps_base != 0 else fps

def _frame_to_spp_units(scene, frame: int) -> int:
    fps = _scene_fps(scene)
    bpm = _get_bpm(scene)

    seconds = max(0.0, float(frame) / fps)
    beats = seconds * (bpm / 60.0)
    spp_units = int(beats * 4.0)  # 4 x 1/16 notes per beat
    return max(0, spp_units)

def _send_spp(scene, frame: int) -> bool:
    """Send true MIDI SPP units (1/16 notes), not raw frames."""
    mido = _get_mido()
    if not mido or not DEV.out_port:
        return False
    try:
        spp_units = _frame_to_spp_units(scene, frame)
        DEV.out_port.send(mido.Message('songpos', pos=spp_units))
        return True
    except Exception:
        return False

# ------------------ Duplex tick ------------------
def _duplex_tick():
    global _LAST_FRAME, _LAST_CHANGE_TS, _SENDING, _TIMER_RUNNING

    if not _TIMER_RUNNING:
        return None  # returning None stops the Blender timer
    scene = bpy.context.scene
    if not scene:
        return 0.15


    mode = getattr(scene, "scoresync_duplex_mode", "OFF")
    rate_hz = max(5, int(getattr(scene, "scoresync_duplex_rate_hz", 20)))
    debounce_ms = max(40, int(getattr(scene, "scoresync_duplex_debounce_ms", 140)))
    use_mtc = bool(getattr(scene, "scoresync_duplex_use_mtc", False))
    mtc_fps_sel = str(getattr(scene, "scoresync_duplex_mtc_fps", "30"))
    mtc_fps = 30 if mtc_fps_sel == "30" else (25 if mtc_fps_sel == "25" else 24)

    # Early out if OFF or no MIDI Out
    if mode == "OFF" or DEV.out_port is None:
        _SENDING = False
        _LAST_FRAME = scene.frame_current
        _LAST_CHANGE_TS = time.time()
        return 1.0

    now = time.time()
    frame = int(scene.frame_current)

    master_mode = getattr(scene, "scoresync_master_mode", "AUTO")

    # FL-locked: never push outbound
    if master_mode == "FL":
        _SENDING = False
        _LAST_FRAME = frame
        _LAST_CHANGE_TS = now
        return 1.0 / 12

    # While FL is playing, silence outgoing SPP/MTC regardless of mode.
    # (BLENDER-locked users who want to fight FL mid-playback can use the buttons.)
    if DEV.fl_is_playing:
        _SENDING = False
        _LAST_FRAME = frame
        _LAST_CHANGE_TS = now
        return 1.0 / 12

    # AUTO mode: if FL recently sent an SPP (FL was scrubbing), stay quiet for
    # 400 ms so Blender doesn't echo back. This is the "FL took master by scrubbing"
    # case — Blender hasn't claimed master yet so _blender_is_master() is False.
    _FL_SPP_QUIET_S = 0.40
    if master_mode == "AUTO" and not _blender_is_master():
        if (now - DEV.last_fl_spp_ts) < _FL_SPP_QUIET_S:
            _SENDING = False
            _LAST_FRAME = frame
            _LAST_CHANGE_TS = now
            return 1.0 / 12

    allow_push = True  # Blender master (locked or AUTO hold) → push to FL

    if allow_push:
        if _LAST_FRAME is None:
            _LAST_FRAME = frame
            _LAST_CHANGE_TS = now

        changed = (frame != _LAST_FRAME)
        if changed:
            _LAST_FRAME = frame
            _LAST_CHANGE_TS = now
            _SENDING = True  # actively scrubbing
            if master_mode != "FL":
                _claim_blender_master(scene)

            if use_mtc:
                hh, mm, ss, ff = _frame_to_tc(frame, mtc_fps, _scene_fps(scene))
                _send_mtc_burst(hh, mm, ss, ff, mtc_fps)
            else:
                _send_spp(scene, frame)

        # While scrubbing, stream at rate_hz
        if _SENDING:
            if use_mtc:
                hh, mm, ss, ff = _frame_to_tc(frame, mtc_fps, _scene_fps(scene))
                _send_mtc_burst(hh, mm, ss, ff, mtc_fps)
            else:
                _send_spp(scene, frame)

        # Debounce finalize: send a clean SPP locate when hand stops
        if _SENDING and (now - _LAST_CHANGE_TS) * 1000.0 >= debounce_ms:
            _send_spp(scene, frame)
            _SENDING = False

    # Tick rate: higher when scrubbing, lower when idle
    return 1.0 / float(rate_hz if _SENDING else 12)

# ------------------ Public timer controls ------------------
def scoresync_duplex_timer_register():
    global _TIMER_RUNNING
    if _TIMER_RUNNING:
        return
    bpy.app.timers.register(_duplex_tick, first_interval=0.2)
    _TIMER_RUNNING = True

def scoresync_duplex_timer_unregister():
    global _TIMER_RUNNING
    _TIMER_RUNNING = False
    try:
        bpy.app.timers.unregister(_duplex_tick)
    except Exception:
        pass


class SCORESYNC_OT_set_duplex_mode(bpy.types.Operator):
    bl_idname = "scoresync.set_duplex_mode"
    bl_label = "Set Duplex Mode"
    bl_options = {'INTERNAL'}

    mode: bpy.props.EnumProperty(
        items=[('OFF','OFF',''),('ASSIST','ASSIST',''),('FORCE','FORCE','')]
    )

    def execute(self, context):
        context.scene.scoresync_duplex_mode = self.mode
        return {'FINISHED'}
