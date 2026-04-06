import bpy, time
from .ops_connection import _get_mido, DEV, _get_bpm, _claim_blender_master, _log_event

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
