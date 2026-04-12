import bpy, time
from .ops_connection import _get_mido, DEV, _get_bpm, _claim_blender_master, _log_event


# ── Viewport navigation ───────────────────────────────────────────────────────

class SCORESYNC_OT_open_area(bpy.types.Operator):
    """Switch the current editor area to a different type (e.g. VSE ↔ 3D View)."""
    bl_idname  = "scoresync.open_area"
    bl_label   = "Switch Editor Area"
    bl_options = {'REGISTER'}

    editor_type: bpy.props.StringProperty(
        name="Editor Type",
        description="Blender area type to switch to (e.g. SEQUENCE_EDITOR, VIEW_3D)",
        default="SEQUENCE_EDITOR",
    )

    def execute(self, context):
        context.area.type = self.editor_type
        return {'FINISHED'}

_TX_LOCK_S = 0.35   # seconds to ignore incoming transport after an outbound send

def _arm_tx_lock():
    DEV.tx_lock_until = time.time() + _TX_LOCK_S

# Throttle so we don't spam the DAW if you hammer the button
_LAST_LOCATE_TS = 0.0
_LOCATE_MIN_MS = 110  # feel free to tune

def _tx_dbg(scene, text):
    if getattr(scene, "scoresync_debug", False):
        print("[ScoreSync TX]", text)

def _send_spp(scene, frame: int) -> bool:
    """
    Send MIDI Song Position Pointer in true SPP units (1/16 notes).
    Converts Blender frame -> seconds -> beats -> SPP units.
    """
    mido = _get_mido()
    if not mido or not DEV.out_port:
        return False

    fps = float(scene.render.fps or 30) / float(scene.render.fps_base or 1.0)
    bpm = _get_bpm(scene)
    seconds = max(0.0, float(frame) / fps)
    beats = seconds * (bpm / 60.0)
    spp_units = int(beats * 4.0)  # 4 x 1/16 notes per beat

    _tx_dbg(scene, f"SPP pos={spp_units} (from frame={frame}) bpm={bpm:.2f} fps={fps:.3f}")

    try:
        DEV.out_port.send(mido.Message('songpos', pos=max(0, spp_units)))
        return True
    except Exception as e:
        _tx_dbg(scene, f"SPP send failed: {e}")
        return False




def _send_start(scene) -> bool:
    _tx_dbg(scene, "Sent START to DAW")
    mido = _get_mido()
    if not mido or not DEV.out_port:
        return False
    try:
        DEV.out_port.send(mido.Message('start'))
        return True
    except Exception as e:
        _tx_dbg(scene, f"START send failed: {e}")
        return False


def _send_continue(scene) -> bool:
    _tx_dbg(scene, "Sent CONTINUE to DAW")
    mido = _get_mido()
    if not mido or not DEV.out_port:
        return False
    try:
        DEV.out_port.send(mido.Message('continue'))
        return True
    except Exception as e:
        _tx_dbg(scene, f"CONTINUE send failed: {e}")
        return False


def _send_stop(scene) -> bool:
    _tx_dbg(scene, "Sent STOP to DAW")
    mido = _get_mido()
    if not mido or not DEV.out_port:
        return False
    try:
        DEV.out_port.send(mido.Message('stop'))
        return True
    except Exception as e:
        _tx_dbg(scene, f"STOP send failed: {e}")
        return False


def _send_mmc_play(scene) -> bool:
    _tx_dbg(scene, "Sent MMC PLAY to DAW")
    mido = _get_mido()
    if not mido or not DEV.out_port:
        return False
    try:
        DEV.out_port.send(mido.Message('sysex', data=[0x7F, 0x7F, 0x06, 0x02]))
        return True
    except Exception as e:
        _tx_dbg(scene, f"MMC PLAY failed: {e}")
        return False


def _send_mmc_stop(scene) -> bool:
    _tx_dbg(scene, "Sent MMC STOP to DAW")
    mido = _get_mido()
    if not mido or not DEV.out_port:
        return False
    try:
        DEV.out_port.send(mido.Message('sysex', data=[0x7F, 0x7F, 0x06, 0x01]))
        return True
    except Exception as e:
        _tx_dbg(scene, f"MMC STOP failed: {e}")
        return False


class SCORESYNC_OT_play(bpy.types.Operator):
    bl_idname = "scoresync.tx_play"
    bl_label = "Play (to DAW)"

    def execute(self, context):
        scene = context.scene
        frame = int(scene.frame_current)

        _tx_dbg(scene, f"Play pressed at frame={frame}")

        _claim_blender_master(scene)
        _send_spp(scene, frame)
        _arm_tx_lock()
        ok = _send_start(scene)
        _send_mmc_play(scene)
        _log_event("TX play", f"frame={frame}")

        if not ok:
            self.report({'WARNING'}, "No MIDI Out or DAW not listening")
            return {'CANCELLED'}

        return {'FINISHED'}

class SCORESYNC_OT_stop(bpy.types.Operator):
    bl_idname = "scoresync.tx_stop"
    bl_label = "Stop (to DAW)"
    def execute(self, context):
        scene = context.scene
        _claim_blender_master(scene)
        _arm_tx_lock()
        ok = _send_stop(scene) or _send_mmc_stop(scene)
        _log_event("TX stop")
        if not ok:
            self.report({'WARNING'}, "No MIDI Out or DAW not listening")
            return {'CANCELLED'}
        return {'FINISHED'}

class SCORESYNC_OT_locate_to_timeline(bpy.types.Operator):
    bl_idname = "scoresync.tx_locate_to_timeline"
    bl_label = "Locate to Current Frame"

    def execute(self, context):
        global _LAST_LOCATE_TS
        now = time.time()
        if (now - _LAST_LOCATE_TS) * 1000.0 < _LOCATE_MIN_MS:
            return {'CANCELLED'}
        _LAST_LOCATE_TS = now

        scene = context.scene
        frame = int(scene.frame_current)
        _claim_blender_master(scene)
        _arm_tx_lock()
        ok = _send_spp(scene, frame)
        _log_event("TX locate", f"frame={frame}")
        if not ok:
            self.report({'WARNING'}, "No MIDI Out or DAW not listening")
            return {'CANCELLED'}

        return {'FINISHED'}


# ── Transport MIDI bindings ────────────────────────────────────────────────────
# Bind hardware buttons/knobs directly to transport actions and timeline control.
# Separate from the MIDI Mapping layer — these fire operators, not properties.

_TRANSPORT_TARGETS = [
    ("PLAY",        "Play",        "Start playback and send transport to DAW"),
    ("STOP",        "Stop",        "Stop playback and send transport to DAW"),
    ("NEXT_MARKER", "Next Marker", "Jump to next timeline marker"),
    ("PREV_MARKER", "Prev Marker", "Jump to previous timeline marker"),
]

_TRANSPORT_TARGET_IDS = [t[0] for t in _TRANSPORT_TARGETS]


class _TransportLearnState:
    learning       = False
    target         = ""    # e.g. "PLAY"
    capture_dirty  = False
    pending_type   = ""
    pending_ch     = 0
    pending_num    = 0
    prev_raw       = {}    # (type, ch, num) → last raw seen, for edge detection

DEV_TP = _TransportLearnState()


class TransportMidiBind(bpy.types.PropertyGroup):
    """One MIDI binding for a single transport action (stored as PointerProperty on scene)."""
    midi_type: bpy.props.EnumProperty(
        name="MIDI Type",
        items=[("CC", "CC", "Control Change threshold"), ("NOTE_ON", "Note On", "")],
        default="NOTE_ON",
    )
    channel : bpy.props.IntProperty(name="Channel", default=0, min=0, max=15)
    midi_num: bpy.props.IntProperty(name="CC / Note", default=0, min=0, max=127)
    enabled : bpy.props.BoolProperty(name="Enabled", default=True)
    bound   : bpy.props.BoolProperty(name="Bound", default=False)


def transport_learn_capture(midi_type: str, channel: int, num: int, val: int):
    """
    Called from the MIDI scan thread when transport learn is active.
    Captures the first NOTE_ON or CC that arrives.
    """
    if not DEV_TP.learning:
        return
    if midi_type == "NOTE_ON" and val == 0:
        return  # ignore note-off
    DEV_TP.pending_type  = midi_type
    DEV_TP.pending_ch    = channel
    DEV_TP.pending_num   = num
    DEV_TP.capture_dirty = True
    DEV_TP.learning      = False


def _fire_transport_target(scene, target: str):
    """Execute the Blender/ScoreSync action for a transport target."""
    try:
        if target == "PLAY":
            bpy.ops.scoresync.tx_play()
        elif target == "STOP":
            bpy.ops.scoresync.tx_stop()
        elif target == "NEXT_MARKER":
            bpy.ops.screen.marker_jump(next=True)
        elif target == "PREV_MARKER":
            bpy.ops.screen.marker_jump(next=False)
    except Exception as e:
        print(f"[ScoreSync] transport fire failed ({target}): {e}")


def apply_transport_midi_tick(scene) -> bool:
    """
    Apply MIDI-driven transport actions. Call from main timer.
    Returns True when an action fired (so caller can tag_redraw).
    """
    dirty = False

    # Process pending learn capture
    if DEV_TP.capture_dirty and DEV_TP.pending_type and DEV_TP.target:
        DEV_TP.capture_dirty = False
        bind = _get_bind(scene, DEV_TP.target)
        if bind:
            bind.midi_type = DEV_TP.pending_type
            bind.channel   = DEV_TP.pending_ch
            bind.midi_num  = DEV_TP.pending_num
            bind.bound     = True
            bind.enabled   = True
            scene.scoresync_transport_learn_status = (
                f"{DEV_TP.target}: {DEV_TP.pending_type} ch{DEV_TP.pending_ch+1} "
                f"#{DEV_TP.pending_num}"
            )
            print(f"[ScoreSync] Transport learned: {DEV_TP.target} → "
                  f"{DEV_TP.pending_type} ch{DEV_TP.pending_ch+1} #{DEV_TP.pending_num}")
        DEV_TP.target = ""
        dirty = True

    try:
        from .ops_mapping import DEV_MAP
    except Exception:
        return dirty

    for target_id in _TRANSPORT_TARGET_IDS:
        bind = _get_bind(scene, target_id)
        if bind is None or not bind.enabled or not bind.bound:
            continue

        key = (bind.midi_type, bind.channel, bind.midi_num)
        raw = DEV_MAP.last_val.get(key)
        if raw is None:
            continue

        prev = DEV_TP.prev_raw.get(key)
        if raw == prev:
            continue
        DEV_TP.prev_raw[key] = raw

        # NOTE_ON: fire on rising edge (0 → nonzero)
        # CC: fire when crossing threshold 64 (low→high)
        if bind.midi_type == "NOTE_ON":
            if raw > 0 and (prev is None or prev == 0):
                _fire_transport_target(scene, target_id)
                dirty = True
        else:  # CC
            if raw > 64 and (prev is None or prev <= 64):
                _fire_transport_target(scene, target_id)
                dirty = True

    return dirty


def _get_bind(scene, target_id: str):
    """Return the TransportMidiBind PointerProperty for a target, or None."""
    attr = f"scoresync_tp_{target_id.lower()}"
    return getattr(scene, attr, None)


# ── Transport learn / clear operators ────────────────────────────────────────

class SCORESYNC_OT_transport_learn_start(bpy.types.Operator):
    """Touch any control on your controller to bind it to this transport action"""
    bl_idname   = "scoresync.transport_learn_start"
    bl_label    = "Learn Transport"
    bl_description = "Touch any pad, button, or knob to bind it to this action"

    target: bpy.props.EnumProperty(name="Target", items=_TRANSPORT_TARGETS)

    def execute(self, context):
        DEV_TP.learning      = True
        DEV_TP.target        = self.target
        DEV_TP.capture_dirty = False
        context.scene.scoresync_transport_learn_status = (
            f"Listening for {self.target}… touch any control"
        )
        self.report({'INFO'}, f"Transport learn: {self.target} — touch a control")
        try:
            from .ops_connection import start_learn_scan
            start_learn_scan()
        except Exception:
            pass
        return {'FINISHED'}


class SCORESYNC_OT_transport_learn_cancel(bpy.types.Operator):
    bl_idname = "scoresync.transport_learn_cancel"
    bl_label  = "Cancel Transport Learn"

    def execute(self, context):
        DEV_TP.learning = False
        DEV_TP.target   = ""
        context.scene.scoresync_transport_learn_status = ""
        return {'FINISHED'}


class SCORESYNC_OT_transport_clear_binding(bpy.types.Operator):
    """Clear the MIDI binding from this transport action"""
    bl_idname  = "scoresync.transport_clear_binding"
    bl_label   = "Clear Transport Binding"
    bl_options = {'REGISTER', 'UNDO'}

    target: bpy.props.EnumProperty(name="Target", items=_TRANSPORT_TARGETS)

    def execute(self, context):
        bind = _get_bind(context.scene, self.target)
        if bind:
            bind.bound   = False
            bind.enabled = True
            DEV_TP.prev_raw.pop(
                (bind.midi_type, bind.channel, bind.midi_num), None
            )
        context.scene.scoresync_transport_learn_status = (
            f"{self.target} binding cleared"
        )
        return {'FINISHED'}


transport_midi_classes = (
    TransportMidiBind,
    SCORESYNC_OT_transport_learn_start,
    SCORESYNC_OT_transport_learn_cancel,
    SCORESYNC_OT_transport_clear_binding,
)
