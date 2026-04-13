
import bpy
import os
import datetime
from .deps import deps_install

def _get_mido():
    try:
        import mido
        try:
            mido.set_backend("mido.backends.rtmidi")
        except Exception:
            pass
        return mido
    except Exception:
        return None

class SCORESYNC_OT_list_ports(bpy.types.Operator):
    bl_idname = "scoresync.list_ports"
    bl_label = "List MIDI Ports"
    bl_description = "Print available MIDI ports to the console"

    def execute(self, context):
        mido = _get_mido()
        if not mido:
            self.report({'WARNING'}, "mido not available. Install dependencies first.")
            print("[ScoreSync] mido not available. Install dependencies first.")
            return {'CANCELLED'}
        ins = mido.get_input_names()
        outs = mido.get_output_names()
        print("[ScoreSync] MIDI Inputs:")
        for n in ins:
            print("  -", n)
        print("[ScoreSync] MIDI Outputs:")
        for n in outs:
            print("  -", n)
        self.report({'INFO'}, f"Found {len(ins)} inputs / {len(outs)} outputs (see console)")
        return {'FINISHED'}

class SCORESYNC_OT_send_test(bpy.types.Operator):
    bl_idname = "scoresync.send_test"
    bl_label = "Send Test CC"
    bl_description = "Send CC#119 value=1 on the MIDI Out port to confirm the connection is alive"

    def execute(self, context):
        from .ops_connection import DEV
        mido = _get_mido()
        if not mido or not DEV.out_port:
            self.report({'WARNING'}, "No MIDI Out connected. (Re)Connect first.")
            print("[ScoreSync] Send Test: no MIDI Out port open.")
            return {'CANCELLED'}
        try:
            DEV.out_port.send(mido.Message('control_change', control=119, value=1, channel=0))
            self.report({'INFO'}, "Sent CC#119=1 on MIDI Out — check FL hint bar")
            print("[ScoreSync] Send Test: CC#119=1 sent on", DEV.out_port_name)
        except Exception as e:
            self.report({'WARNING'}, f"Send failed: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

class SCORESYNC_OT_install_deps(bpy.types.Operator):
    bl_idname = "scoresync.install_deps"
    bl_label = "Install MIDI Dependencies"
    bl_description = "Install mido + python-rtmidi into Blender's Python environment"

    def execute(self, context):
        ok, log = deps_install.install_deps(["mido", "python-rtmidi"])
        if ok:
            self.report({'INFO'}, "Dependencies installed. Click Refresh Ports.")
        else:
            self.report({'ERROR'}, "Dependency installation failed (see console).")
        print("[ScoreSync][deps] log:\n" + log)
        return {'FINISHED'}

class SCORESYNC_OT_open_docs(bpy.types.Operator):
    bl_idname = "scoresync.open_docs"
    bl_label = "Open Docs"
    bl_description = "Open ScoreSync documentation"

    def execute(self, context):
        try:
            bpy.ops.wm.url_open(url="https://example.com/scoresync-docs")
            return {'FINISHED'}
        except Exception:
            self.report({'WARNING'}, "Could not open URL")
            return {'CANCELLED'}


class SCORESYNC_OT_apply_preset(bpy.types.Operator):
    bl_idname = "scoresync.apply_preset"
    bl_label = "Apply Preset"
    bl_description = "Apply a built-in ScoreSync preset to the current scene"

    preset: bpy.props.EnumProperty(
        name="Preset",
        items=[
            ("FL_FOLLOW",      "DAW Follow",     "DAW drives everything; Blender follows"),
            ("BLENDER_ASSIST", "Blender Assist", "Auto mode; scrubbing Blender nudges the DAW when stopped"),
            ("AUTO_MASTER",    "Auto Master",    "Auto mode with longer hold and faster scrub rate"),
        ],
        default="BLENDER_ASSIST",
    )

    def execute(self, context):
        from .prefs import apply_preset, BUILTIN_PRESETS
        scene = context.scene
        ok = apply_preset(scene, self.preset)
        if ok:
            label = BUILTIN_PRESETS[self.preset]["label"]
            self.report({'INFO'}, f"Preset applied: {label}")
            print(f"[ScoreSync] Preset applied: {self.preset}")
        else:
            self.report({'WARNING'}, f"Unknown preset: {self.preset}")
        return {'FINISHED'}


class SCORESYNC_OT_snapshot(bpy.types.Operator):
    bl_idname = "scoresync.snapshot"
    bl_label = "Snapshot State"
    bl_description = "Print current ScoreSync state to the System Console"

    def execute(self, context):
        from .ops_connection import DEV, _get_bpm
        scene = context.scene
        mido = _get_mido()

        lines = [
            "=" * 50,
            f"ScoreSync Snapshot  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 50,
            f"  MIDI In  : {DEV.in_port_name or 'none'}  (listener={'running' if DEV.listener_running else 'stopped'})",
            f"  MIDI Out : {DEV.out_port_name or 'none'}  (port={'open' if DEV.out_port else 'closed'})",
            f"  FL Script: {'OK' if scene.scoresync_script_ok else 'not detected'}",
            f"  BPM      : {_get_bpm(scene):.2f}  (auto={scene.scoresync_bpm_estimate:.2f}  manual={'ON' if scene.scoresync_use_manual_bpm else 'OFF'}={scene.scoresync_manual_bpm:.2f})",
            f"  Master   : {getattr(scene, 'scoresync_master_status', '?')}  mode={getattr(scene, 'scoresync_master_mode', '?')}",
            f"  FL playing: {DEV.fl_is_playing}",
            f"  tx_lock  : {'active' if __import__('time').time() < DEV.tx_lock_until else 'clear'}",
            f"  LED      : {scene.scoresync_led_text}",
            f"  Duplex   : {scene.scoresync_duplex_mode}  rate={scene.scoresync_duplex_rate_hz}Hz  debounce={scene.scoresync_duplex_debounce_ms}ms",
            f"  Log entries: {len(DEV.event_log)}",
            "=" * 50,
        ]

        # Available ports
        if mido:
            try:
                ins  = mido.get_input_names()
                outs = mido.get_output_names()
                lines.append(f"  MIDI Inputs  ({len(ins)}): {', '.join(ins) or 'none'}")
                lines.append(f"  MIDI Outputs ({len(outs)}): {', '.join(outs) or 'none'}")
            except Exception:
                lines.append("  (could not list MIDI ports)")
        else:
            lines.append("  mido not available")

        output = "\n".join(lines)
        print(output)
        self.report({'INFO'}, "Snapshot printed to System Console")
        return {'FINISHED'}


class SCORESYNC_OT_export_log(bpy.types.Operator):
    bl_idname = "scoresync.export_log"
    bl_label = "Export Event Log"
    bl_description = "Save the last 200 ScoreSync events to a .txt file"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filename: bpy.props.StringProperty(default="scoresync_log.txt")
    filter_glob: bpy.props.StringProperty(default="*.txt", options={'HIDDEN'})

    def invoke(self, context, event):
        self.filename = f"scoresync_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        from .ops_connection import DEV, _get_bpm
        scene = context.scene

        dst = bpy.path.abspath(self.filepath)
        if not dst.endswith(".txt"):
            dst = os.path.join(dst, self.filename)

        lines = [
            f"ScoreSync Event Log  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Version: 0.6.0",
            f"MIDI In: {DEV.in_port_name or 'none'}  Out: {DEV.out_port_name or 'none'}",
            f"BPM: {_get_bpm(scene):.2f}  Master: {getattr(scene, 'scoresync_master_status', '?')}",
            "",
            f"{'Timestamp':<14} {'Type':<18} Detail",
            "-" * 60,
        ]

        if DEV.event_log:
            # Use the first entry as the reference time for relative offsets
            t0 = DEV.event_log[0]["ts"]
            for entry in DEV.event_log:
                rel = entry["ts"] - t0
                lines.append(f"+{rel:<13.3f} {entry['type']:<18} {entry.get('detail', '')}")
        else:
            lines.append("(no events recorded)")

        try:
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Log exported: {dst}")
        print(f"[ScoreSync] Log exported → {dst}")
        return {'FINISHED'}


class SCORESYNC_OT_export_fl_script(bpy.types.Operator):
    bl_idname = "scoresync.export_fl_script"
    bl_label = "Export FL Script"
    bl_description = (
        "Copy the bundled device_ScoreSync.py to a folder of your choice. "
        "Then place it in: FL Studio\\Settings\\Hardware\\ScoreSync\\"
    )

    # File browser properties
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filename: bpy.props.StringProperty(default="device_ScoreSync.py")
    filter_glob: bpy.props.StringProperty(default="*.py", options={'HIDDEN'})

    def invoke(self, context, event):
        self.filename = "device_ScoreSync.py"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        src = os.path.join(os.path.dirname(__file__), "flstudio", "device_ScoreSync.py")
        if not os.path.isfile(src):
            self.report({'ERROR'}, "Bundled FL script not found inside addon folder.")
            return {'CANCELLED'}

        dst = bpy.path.abspath(self.filepath)
        # If user picked a directory (no .py extension), append filename
        if not dst.endswith(".py"):
            dst = os.path.join(dst, "device_ScoreSync.py")

        try:
            import shutil
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"FL script exported to: {dst}")
        print(f"[ScoreSync] FL script exported → {dst}")
        return {'FINISHED'}


class SCORESYNC_OT_hardware_mode_apply(bpy.types.Operator):
    """Apply Hardware Mode defaults: DAW=master, duplex off, manual BPM on."""
    bl_idname = "scoresync.hardware_mode_apply"
    bl_label  = "Apply Hardware Mode"
    bl_description = (
        "Switch to Hardware Mode: DAW is master, duplex Off, manual BPM enabled. "
        "Hides DAW-specific UI elements (script export, health check)."
    )

    def execute(self, context):
        scene = context.scene
        scene.scoresync_hardware_mode   = True
        scene.scoresync_master_mode     = "FL"
        scene.scoresync_duplex_mode     = "OFF"
        scene.scoresync_use_manual_bpm  = True
        if scene.scoresync_manual_bpm < 20.0:
            scene.scoresync_manual_bpm  = 120.0
        self.report({'INFO'}, "Hardware Mode applied — DAW is master, duplex off, manual BPM on")
        print("[ScoreSync] Hardware Mode applied")
        return {'FINISHED'}


class SCORESYNC_OT_fl_mode_apply(bpy.types.Operator):
    """Restore DAW Mode (undo Hardware Mode)."""
    bl_idname = "scoresync.fl_mode_apply"
    bl_label  = "Apply DAW Mode"
    bl_description = "Show DAW-specific UI and restore Auto master mode"

    def execute(self, context):
        scene = context.scene
        scene.scoresync_hardware_mode  = False
        scene.scoresync_master_mode    = "AUTO"
        scene.scoresync_duplex_mode    = "ASSIST"
        scene.scoresync_use_manual_bpm = False
        self.report({'INFO'}, "DAW Mode restored")
        return {'FINISHED'}
