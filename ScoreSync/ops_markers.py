import bpy
from .ops_connection import DEV

# ---------- helpers ----------
def _sorted_markers(scene):
    return sorted(scene.timeline_markers, key=lambda m: m.frame)

def _count_prefix(scene, prefix: str) -> int:
    prefix = prefix.strip().lower()
    n = 0
    for m in scene.timeline_markers:
        if m.name.strip().lower().startswith(prefix):
            n += 1
    return n

def _frame_to_bar_beat(scene, frame: int):
    """Approximate bar/beat using current BPM estimate and DEV.frame_origin as bar 1 beat 1."""
    fps = max(1, int(scene.render.fps))
    bpm = float(getattr(scene, "scoresync_bpm_estimate", 0.0)) or 120.0
    beats_per_bar = max(1, int(getattr(scene, "scoresync_time_sig_n", 4)))

    # time from origin (clamped at 0)
    base = int(getattr(DEV, "frame_origin", 0))
    delta_frames = max(0, frame - base)
    seconds = delta_frames / fps
    total_beats = seconds * (bpm / 60.0)

    # bar is 1-based, beat is 1-based
    bar_idx = int(total_beats // beats_per_bar) + 1
    beat_in_bar = int(total_beats % beats_per_bar) + 1
    return bar_idx, beat_in_bar

# ---------- operators ----------
class SCORESYNC_OT_drop_preset_marker(bpy.types.Operator):
    """Drop a timeline marker with the selected preset name"""
    bl_idname = "scoresync.drop_preset_marker"
    bl_label = "Drop Preset Marker"

    def execute(self, context):
        scene = context.scene
        preset = scene.scoresync_marker_preset
        pretty = {
            "INTRO": "Intro", "VERSE": "Verse", "HOOK": "Hook",
            "BRIDGE": "Bridge", "BREAK": "Break", "DROP": "Drop", "OUTRO": "Outro"
        }.get(preset, preset.title())
        # increment based on existing count
        idx = _count_prefix(scene, pretty) + 1
        name = f"{pretty} {idx:02d}"
        try:
            scene.timeline_markers.new(name=name, frame=scene.frame_current)
            self.report({'INFO'}, f"Marker: {name}")
        except Exception as e:
            self.report({'WARNING'}, f"Could not add marker: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

class SCORESYNC_OT_jump_prev_marker(bpy.types.Operator):
    """Jump to previous timeline marker"""
    bl_idname = "scoresync.jump_prev_marker"
    bl_label = "Prev Marker"

    def execute(self, context):
        scene = context.scene
        cur = scene.frame_current
        prevs = [m for m in _sorted_markers(scene) if m.frame < cur]
        if not prevs:
            self.report({'INFO'}, "No previous marker")
            return {'CANCELLED'}
        scene.frame_current = prevs[-1].frame
        return {'FINISHED'}

class SCORESYNC_OT_jump_next_marker(bpy.types.Operator):
    """Jump to next timeline marker"""
    bl_idname = "scoresync.jump_next_marker"
    bl_label = "Next Marker"

    def execute(self, context):
        scene = context.scene
        cur = scene.frame_current
        nexts = [m for m in _sorted_markers(scene) if m.frame > cur]
        if not nexts:
            self.report({'INFO'}, "No next marker")
            return {'CANCELLED'}
        scene.frame_current = nexts[0].frame
        return {'FINISHED'}

class SCORESYNC_OT_rename_markers_bar_beat(bpy.types.Operator):
    """Rename all markers to Bar/Beat based on BPM estimate and current time-base"""
    bl_idname = "scoresync.rename_markers_bar_beat"
    bl_label = "Rename Markers → Bar:Beat"

    def execute(self, context):
        scene = context.scene
        if not scene.timeline_markers:
            self.report({'INFO'}, "No markers to rename")
            return {'CANCELLED'}

        for m in scene.timeline_markers:
            b, beat = _frame_to_bar_beat(scene, int(m.frame))
            m.name = f"Bar {b:03d} • Beat {beat}"
        self.report({'INFO'}, "Markers renamed to Bar/Beat (est.)")
        return {'FINISHED'}
