import bpy
from .ops_connection import _get_mido, DEV

class SCORESYNC_OT_check_fl_script(bpy.types.Operator):
    bl_idname = "scoresync.check_fl_script"
    bl_label = "Check FL Script"
    bl_description = "Send a probe to FL; script should echo back (CC#119)"

    def execute(self, context):
        scene = context.scene
        mido = _get_mido()
        if not mido or not DEV.out_port:
            self.report({'WARNING'}, "No MIDI Out selected")
            return {'CANCELLED'}

        # reset flag before probe
        scene.scoresync_script_ok = False

        # Send CC#119 value 7 (magic)
        try:
            DEV.out_port.send(mido.Message('control_change', control=119, value=7, channel=0))
        except Exception:
            self.report({'WARNING'}, "Failed to send probe on MIDI Out")
            return {'CANCELLED'}

        self.report({'INFO'}, "Probe sent. If FL script is active and Output is enabled, it will echo back.")
        return {'FINISHED'}
