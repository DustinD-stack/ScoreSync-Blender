"""
ScoreSync v2 — ops_mapping.py
MIDI → Blender property mapping layer.

Architecture
------------
Each mapping is a dict stored in scene.scoresync_mappings (CollectionProperty):
  {
    id_type   : "OBJECT" | "SCENE" | "CAMERA" | "MATERIAL" | "WORLD" | "NODE" ...
    id_name   : name of the datablock (e.g. "Cube", "Scene")
    data_path : rna path relative to that block (e.g. "location.x")
    midi_type : "CC" | "NOTE_ON"
    channel   : 0-15
    midi_num  : CC number or note number (0-127)
    value_min : float — incoming MIDI 0   maps to this
    value_max : float — incoming MIDI 127 maps to this
    label     : human-readable name
    enabled   : bool
  }

Learn mode
----------
  DEV_MAP.learning = True
  Next incoming CC or Note On → stored in DEV_MAP.pending_*
  User then clicks "Assign to property" (eyedropper via rna_path_button)
  → mapping created

Apply loop
----------
Runs inside scoresync_timer (ops_connection.py calls apply_mappings_tick(scene)).
For each mapping, if a new value arrived, resolve the datablock and set it.
"""

import bpy
import json
import os
import time

# ── Learn state (module-level, not per-scene) ─────────────────────────────────
class _MappingLearnState:
    learning       = False
    pending_type   = ""      # "CC" | "NOTE_ON"
    pending_ch     = 0
    pending_num    = 0
    pending_val    = 0
    pending_ts     = 0.0
    capture_dirty  = False   # True once MIDI thread writes a capture
    target_idx     = -1      # mapping index to auto-assign when capture arrives
    last_val       = {}      # (type, ch, num) -> last raw value (0-127)
    prev_raw       = {}      # (type, ch, num) -> raw value seen on last apply tick

DEV_MAP = _MappingLearnState()


# ── Preset templates ──────────────────────────────────────────────────────────
MAPPING_PRESETS = {
    "CAMERA": [
        {"label": "Cam X",        "id_type": "OBJECT", "id_name": "Camera", "data_path": "location.x",      "value_min": -10.0, "value_max": 10.0},
        {"label": "Cam Y",        "id_type": "OBJECT", "id_name": "Camera", "data_path": "location.y",      "value_min": -10.0, "value_max": 10.0},
        {"label": "Cam Z",        "id_type": "OBJECT", "id_name": "Camera", "data_path": "location.z",      "value_min": 0.0,   "value_max": 20.0},
        {"label": "Cam Rot X",    "id_type": "OBJECT", "id_name": "Camera", "data_path": "rotation_euler.x","value_min": -1.57, "value_max": 1.57},
        {"label": "Cam Rot Z",    "id_type": "OBJECT", "id_name": "Camera", "data_path": "rotation_euler.z","value_min": -3.14, "value_max": 3.14},
        {"label": "Cam FOV",      "id_type": "OBJECT", "id_name": "Camera", "data_path": "data.angle",      "value_min": 0.2,   "value_max": 1.8},
    ],
    "ACTIVE_OBJECT": [
        {"label": "Obj X",        "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "location.x",       "value_min": -10.0, "value_max": 10.0},
        {"label": "Obj Y",        "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "location.y",       "value_min": -10.0, "value_max": 10.0},
        {"label": "Obj Z",        "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "location.z",       "value_min": -10.0, "value_max": 10.0},
        {"label": "Obj Scale",    "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "scale.x",          "value_min": 0.0,   "value_max": 5.0},
        {"label": "Obj Rot Z",    "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "rotation_euler.z", "value_min": 0.0,   "value_max": 6.28},
    ],
    "SCENE": [
        {"label": "Frame",        "id_type": "SCENE",  "id_name": "__SCENE__",  "data_path": "frame_current",    "value_min": 0.0,   "value_max": 250.0},
        {"label": "Timeline Start","id_type":"SCENE",  "id_name": "__SCENE__",  "data_path": "frame_start",      "value_min": 0.0,   "value_max": 250.0},
    ],
}


# ── Data-path resolver ────────────────────────────────────────────────────────
_ID_COLLECTIONS = {
    "OBJECT":   lambda: bpy.data.objects,
    "SCENE":    lambda: bpy.data.scenes,
    "CAMERA":   lambda: bpy.data.cameras,
    "MATERIAL": lambda: bpy.data.materials,
    "WORLD":    lambda: bpy.data.worlds,
    "MESH":     lambda: bpy.data.meshes,
    "LIGHT":    lambda: bpy.data.lights,
}

def _resolve_datablock(id_type: str, id_name: str, context=None):
    """Return the Blender datablock or None. Handles __ACTIVE__ and __SCENE__."""
    if id_name == "__ACTIVE__":
        ctx = context or bpy.context
        return getattr(ctx, "active_object", None)
    if id_name == "__SCENE__":
        ctx = context or bpy.context
        return getattr(ctx, "scene", None)
    col_fn = _ID_COLLECTIONS.get(id_type)
    if col_fn is None:
        return None
    try:
        return col_fn().get(id_name)
    except Exception:
        return None


def _set_property(block, data_path: str, value: float) -> bool:
    """
    Set block.data_path = value, handling dotted paths, indexed paths,
    and boolean RNA properties (float >= 0.5 → True).
    Returns True on success.
    """
    try:
        parts = data_path.rsplit(".", 1)
        if len(parts) == 2:
            parent = block.path_resolve(parts[0])
            attr   = parts[1]
        else:
            parent = block
            attr   = parts[0]

        # Indexed: e.g. default_value[3]  or  location[0]
        if "[" in attr and not attr.startswith("["):
            name, idx_str = attr.split("[", 1)
            idx = int(idx_str.rstrip("]"))
            obj = getattr(parent, name)
            obj[idx] = value
            return True

        # Detect RNA type to handle booleans correctly
        try:
            rna_prop = parent.bl_rna.properties.get(attr)
        except Exception:
            rna_prop = None

        if rna_prop and rna_prop.type == 'BOOLEAN':
            setattr(parent, attr, value >= 0.5)
        elif rna_prop and rna_prop.type == 'INT':
            setattr(parent, attr, int(round(value)))
        else:
            setattr(parent, attr, value)
        return True
    except Exception as e:
        print(f"[ScoreSync] _set_property failed ({data_path}): {e}")
        return False


def _midi_to_value(raw: int, v_min: float, v_max: float) -> float:
    t = max(0, min(127, raw)) / 127.0
    return v_min + t * (v_max - v_min)


def _toggle_if_bool(block, data_path: str) -> bool:
    """
    If data_path resolves to a boolean RNA property, toggle it.
    For non-boolean paths, does nothing (caller falls through to _set_property).
    Returns True if a toggle was applied.
    """
    try:
        parts = data_path.rsplit(".", 1)
        if len(parts) == 2:
            parent = block.path_resolve(parts[0])
            attr   = parts[1]
        else:
            parent = block
            attr   = parts[0]

        try:
            rna_prop = parent.bl_rna.properties.get(attr)
        except Exception:
            rna_prop = None

        if rna_prop and rna_prop.type == 'BOOLEAN':
            setattr(parent, attr, not getattr(parent, attr, False))
            return True
    except Exception as e:
        print(f"[ScoreSync] _toggle_if_bool failed ({data_path}): {e}")
    return False


# ── Apply tick (called from scoresync_timer) ──────────────────────────────────
def apply_mappings_tick(scene):
    """Apply any pending MIDI values to mapped properties. Call from main timer."""

    # ── Auto-assign after learn capture ──────────────────────────────────────
    if DEV_MAP.capture_dirty and DEV_MAP.pending_type:
        DEV_MAP.capture_dirty = False
        # Scan keeps running — controller must stay live for value delivery
        mappings = getattr(scene, "scoresync_mappings", None)
        idx = DEV_MAP.target_idx
        if mappings and 0 <= idx < len(mappings):
            m = mappings[idx]
            m.midi_type = DEV_MAP.pending_type
            m.channel   = DEV_MAP.pending_ch
            m.midi_num  = DEV_MAP.pending_num
            scene.scoresync_mapping_learn_status = (
                f"Bound  {DEV_MAP.pending_type} ch{DEV_MAP.pending_ch+1} "
                f"#{DEV_MAP.pending_num}  →  {m.label}"
            )
        else:
            # No mapping selected — still show what was captured
            scene.scoresync_mapping_learn_status = (
                f"Captured  {DEV_MAP.pending_type} ch{DEV_MAP.pending_ch+1} "
                f"#{DEV_MAP.pending_num}  — select a mapping then click ← Assign"
            )
        DEV_MAP.target_idx = -1

    mappings = getattr(scene, "scoresync_mappings", None)
    if mappings is None:
        return
    for m in mappings:
        if not m.enabled:
            continue
        key = (m.midi_type, m.channel, m.midi_num)
        raw = DEV_MAP.last_val.get(key)
        if raw is None:
            continue

        prev = DEV_MAP.prev_raw.get(key)
        if raw == prev:
            continue  # no change since last tick — nothing to do
        DEV_MAP.prev_raw[key] = raw

        block = _resolve_datablock(m.id_type, m.id_name)
        if block is None:
            continue

        # NOTE_ON button → boolean: TOGGLE on rising edge only
        if m.midi_type == "NOTE_ON":
            if raw > 0:
                # Rising edge — try boolean toggle first
                if not _toggle_if_bool(block, m.data_path):
                    # Non-boolean: set to value_max on press
                    _set_property(block, m.data_path, m.value_max)
            else:
                # Note off — for non-boolean paths set to value_min (momentary)
                try:
                    parts = m.data_path.rsplit(".", 1)
                    parent = block.path_resolve(parts[0]) if len(parts) == 2 else block
                    attr   = parts[1] if len(parts) == 2 else parts[0]
                    rna_prop = parent.bl_rna.properties.get(attr)
                    if rna_prop and rna_prop.type == 'BOOLEAN':
                        pass  # booleans are toggled on press, don't reset on release
                    else:
                        _set_property(block, m.data_path, m.value_min)
                except Exception:
                    pass
            continue

        # CC → continuous map
        value = _midi_to_value(raw, m.value_min, m.value_max)
        _set_property(block, m.data_path, value)


def ingest_midi_for_mapping(midi_type: str, channel: int, num: int, val: int):
    """
    Called from the listener thread (via _enqueue path in ops_connection).
    Stores the latest raw value and, if in learn mode, captures the event.
    Thread-safe for writes to DEV_MAP.last_val (dict assignment is atomic in CPython).
    """
    key = (midi_type, channel, num)
    DEV_MAP.last_val[key] = val

    if DEV_MAP.learning:
        DEV_MAP.pending_type  = midi_type
        DEV_MAP.pending_ch    = channel
        DEV_MAP.pending_num   = num
        DEV_MAP.pending_val   = val
        DEV_MAP.pending_ts    = time.time()
        DEV_MAP.capture_dirty = True   # signal main thread to auto-assign
        DEV_MAP.learning      = False  # capture one event then stop


# ── Collection item property group ───────────────────────────────────────────
class ScoreSyncMapping(bpy.types.PropertyGroup):
    label     : bpy.props.StringProperty(name="Label", default="Mapping")
    enabled   : bpy.props.BoolProperty(name="Enabled", default=True)
    id_type   : bpy.props.EnumProperty(
        name="ID Type",
        items=[
            ("OBJECT",   "Object",   ""),
            ("SCENE",    "Scene",    ""),
            ("CAMERA",   "Camera",   ""),
            ("MATERIAL", "Material", ""),
            ("WORLD",    "World",    ""),
        ],
        default="OBJECT",
    )
    id_name   : bpy.props.StringProperty(name="Datablock Name", default="")
    data_path : bpy.props.StringProperty(name="Property Path",  default="location.x")
    midi_type : bpy.props.EnumProperty(
        name="MIDI Type",
        items=[("CC", "CC", "Control Change"), ("NOTE_ON", "Note On", "")],
        default="CC",
    )
    channel   : bpy.props.IntProperty(name="Channel", default=0, min=0, max=15)
    midi_num  : bpy.props.IntProperty(name="CC / Note", default=0, min=0, max=127)
    value_min : bpy.props.FloatProperty(name="Min", default=0.0)
    value_max : bpy.props.FloatProperty(name="Max", default=1.0)


# ── Operators ─────────────────────────────────────────────────────────────────
class SCORESYNC_OT_mapping_learn_start(bpy.types.Operator):
    bl_idname = "scoresync.mapping_learn_start"
    bl_label  = "Learn MIDI"
    bl_description = "Move a control on your device — ScoreSync will capture the next CC or Note"

    def execute(self, context):
        DEV_MAP.learning      = True
        DEV_MAP.capture_dirty = False
        DEV_MAP.target_idx    = getattr(context.scene, "scoresync_mapping_index", -1)
        context.scene.scoresync_mapping_learn_status = "Listening… touch any control on your device"
        self.report({'INFO'}, "Learn mode ON — touch a pad, knob, or button")
        try:
            from .ops_connection import start_learn_scan
            start_learn_scan()
        except Exception:
            pass
        return {'FINISHED'}


class SCORESYNC_OT_mapping_learn_cancel(bpy.types.Operator):
    bl_idname = "scoresync.mapping_learn_cancel"
    bl_label  = "Cancel Learn"

    def execute(self, context):
        DEV_MAP.learning = False
        context.scene.scoresync_mapping_learn_status = ""
        return {'FINISHED'}


class SCORESYNC_OT_mapping_assign(bpy.types.Operator):
    """Assign the last learned MIDI event to the selected mapping slot."""
    bl_idname = "scoresync.mapping_assign"
    bl_label  = "Assign Learned MIDI to Slot"

    index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        scene = context.scene
        if not DEV_MAP.pending_type:
            self.report({'WARNING'}, "No MIDI event learned yet. Click Learn first.")
            return {'CANCELLED'}
        mappings = scene.scoresync_mappings
        if self.index < 0 or self.index >= len(mappings):
            self.report({'WARNING'}, "Invalid mapping slot index.")
            return {'CANCELLED'}
        m = mappings[self.index]
        m.midi_type = DEV_MAP.pending_type
        m.channel   = DEV_MAP.pending_ch
        m.midi_num  = DEV_MAP.pending_num
        scene.scoresync_mapping_learn_status = (
            f"Assigned: {m.midi_type} ch={m.channel} num={m.midi_num}"
        )
        self.report({'INFO'}, f"Mapped {m.midi_type} {m.midi_num} → slot {self.index}")
        return {'FINISHED'}


class SCORESYNC_OT_mapping_select(bpy.types.Operator):
    """Select a mapping row for editing in the inspector."""
    bl_idname = "scoresync.mapping_select"
    bl_label  = "Select Mapping"

    index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        context.scene.scoresync_mapping_index = self.index
        return {'FINISHED'}


class SCORESYNC_OT_mapping_add(bpy.types.Operator):
    bl_idname = "scoresync.mapping_add"
    bl_label  = "Add Mapping"

    def execute(self, context):
        m = context.scene.scoresync_mappings.add()
        m.label = f"Mapping {len(context.scene.scoresync_mappings)}"
        context.scene.scoresync_mapping_index = len(context.scene.scoresync_mappings) - 1
        return {'FINISHED'}


class SCORESYNC_OT_mapping_remove(bpy.types.Operator):
    bl_idname = "scoresync.mapping_remove"
    bl_label  = "Remove Mapping"

    index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        scene = context.scene
        idx = self.index if self.index >= 0 else scene.scoresync_mapping_index
        if 0 <= idx < len(scene.scoresync_mappings):
            scene.scoresync_mappings.remove(idx)
            scene.scoresync_mapping_index = max(0, idx - 1)
        return {'FINISHED'}


class SCORESYNC_OT_mapping_apply_preset(bpy.types.Operator):
    bl_idname  = "scoresync.mapping_apply_preset"
    bl_label   = "Apply Mapping Preset"
    bl_description = "Add preset mappings for Camera, Active Object, or Scene"

    preset: bpy.props.EnumProperty(
        name="Preset",
        items=[
            ("CAMERA",        "Camera",        "Camera transform + FOV"),
            ("ACTIVE_OBJECT", "Active Object", "Active object transform"),
            ("SCENE",         "Scene",         "Frame / timeline"),
        ],
        default="CAMERA",
    )

    def execute(self, context):
        scene = context.scene
        template = MAPPING_PRESETS.get(self.preset, [])
        # Find the next free CC starting from 1
        used_ccs = {m.midi_num for m in scene.scoresync_mappings if m.midi_type == "CC"}
        next_cc = 1
        for t in template:
            while next_cc in used_ccs:
                next_cc += 1
            m = scene.scoresync_mappings.add()
            m.label     = t["label"]
            m.id_type   = t["id_type"]
            m.id_name   = t["id_name"]
            m.data_path = t["data_path"]
            m.value_min = t["value_min"]
            m.value_max = t["value_max"]
            m.midi_type = "CC"
            m.midi_num  = next_cc
            used_ccs.add(next_cc)
            next_cc += 1
        self.report({'INFO'}, f"Added {len(template)} mappings from preset '{self.preset}'")
        return {'FINISHED'}


class SCORESYNC_OT_mapping_export(bpy.types.Operator):
    bl_idname  = "scoresync.mapping_export"
    bl_label   = "Export Mappings"
    bl_description = "Save all MIDI mappings to a JSON file"

    filepath   : bpy.props.StringProperty(subtype="FILE_PATH")
    filename   : bpy.props.StringProperty(default="scoresync_mappings.json")
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        self.filename = "scoresync_mappings.json"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        scene = context.scene
        data = []
        for m in scene.scoresync_mappings:
            data.append({
                "label":     m.label,
                "enabled":   m.enabled,
                "id_type":   m.id_type,
                "id_name":   m.id_name,
                "data_path": m.data_path,
                "midi_type": m.midi_type,
                "channel":   m.channel,
                "midi_num":  m.midi_num,
                "value_min": m.value_min,
                "value_max": m.value_max,
            })
        dst = bpy.path.abspath(self.filepath)
        if not dst.endswith(".json"):
            dst = os.path.join(dst, self.filename)
        try:
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "mappings": data}, f, indent=2)
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {e}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Exported {len(data)} mappings to {dst}")
        return {'FINISHED'}


class SCORESYNC_OT_mapping_import(bpy.types.Operator):
    bl_idname  = "scoresync.mapping_import"
    bl_label   = "Import Mappings"
    bl_description = "Load MIDI mappings from a JSON file (appends to existing)"

    filepath   : bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        scene = context.scene
        src = bpy.path.abspath(self.filepath)
        try:
            with open(src, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {e}")
            return {'CANCELLED'}

        rows = doc.get("mappings", [])
        for row in rows:
            m = scene.scoresync_mappings.add()
            m.label     = row.get("label",     "Imported")
            m.enabled   = row.get("enabled",   True)
            m.id_type   = row.get("id_type",   "OBJECT")
            m.id_name   = row.get("id_name",   "")
            m.data_path = row.get("data_path", "location.x")
            m.midi_type = row.get("midi_type", "CC")
            m.channel   = row.get("channel",   0)
            m.midi_num  = row.get("midi_num",  0)
            m.value_min = row.get("value_min", 0.0)
            m.value_max = row.get("value_max", 1.0)

        self.report({'INFO'}, f"Imported {len(rows)} mappings from {os.path.basename(src)}")
        return {'FINISHED'}


class SCORESYNC_OT_mapping_clear_binding(bpy.types.Operator):
    """Clear the MIDI binding from this mapping slot (keeps the target property)"""
    bl_idname  = "scoresync.mapping_clear_binding"
    bl_label   = "Reset MIDI Binding"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        scene    = context.scene
        mappings = getattr(scene, "scoresync_mappings", None)
        idx      = self.index if self.index >= 0 else getattr(scene, "scoresync_mapping_index", -1)
        if not mappings or idx < 0 or idx >= len(mappings):
            return {'CANCELLED'}
        m           = mappings[idx]
        m.midi_type = "CC"
        m.channel   = 0
        m.midi_num  = 0
        scene.scoresync_mapping_learn_status = f"Binding cleared for \"{m.label}\""
        self.report({'INFO'}, f"MIDI binding cleared: {m.label}")
        return {'FINISHED'}


# ── Registration list (imported by __init__.py) ───────────────────────────────
mapping_classes = (
    ScoreSyncMapping,
    SCORESYNC_OT_mapping_learn_start,
    SCORESYNC_OT_mapping_learn_cancel,
    SCORESYNC_OT_mapping_clear_binding,
    SCORESYNC_OT_mapping_assign,
    SCORESYNC_OT_mapping_select,
    SCORESYNC_OT_mapping_add,
    SCORESYNC_OT_mapping_remove,
    SCORESYNC_OT_mapping_apply_preset,
    SCORESYNC_OT_mapping_export,
    SCORESYNC_OT_mapping_import,
)
