"""
ScoreSync v2 — ops_mapping.py
MIDI → Blender property mapping layer.

Architecture
------------
Each mapping is a CollectionProperty item on scene.scoresync_mappings:
  label       : human-readable name
  enabled     : bool
  id_type     : "OBJECT" | "SCENE" | "CAMERA" | "MATERIAL" | "WORLD"
  id_name     : datablock name (e.g. "Cube") or __ACTIVE__ / __SCENE__
  data_path   : RNA path relative to that block (e.g. "location.x")
  midi_type   : "CC" | "NOTE_ON"
  trigger_mode: "TOGGLE" | "MOMENTARY"  (NOTE_ON only)
  channel     : 0-15
  midi_num    : CC number or note number (0-127)
  value_min   : float — MIDI 0   maps to this
  value_max   : float — MIDI 127 maps to this

Learn mode
----------
  DEV_MAP.learning = True
  Next CC or Note On → stored in DEV_MAP.pending_*
  capture_dirty flag → main timer auto-assigns to the selected slot

Apply loop
----------
  scoresync_timer (ops_connection.py) calls apply_mappings_tick(scene).
  Returns True when a property was written so caller can tag_redraw().

NOTE_ON behaviour
-----------------
  TOGGLE   (default for booleans) — each press flips bool; for floats alternates
           between value_max / value_min.
  MOMENTARY                       — press sets value_max, release sets value_min.
  Both modes only fire on value change (prev_raw guard) to avoid repeated writes.
"""

import bpy
import json
import os
import time


# ── Learn state ───────────────────────────────────────────────────────────────
class _MappingLearnState:
    learning       = False
    pending_type   = ""      # "CC" | "NOTE_ON"
    pending_ch     = 0
    pending_num    = 0
    pending_val    = 0
    pending_ts     = 0.0
    capture_dirty  = False   # set by MIDI thread; consumed by main timer
    target_idx     = -1      # slot to auto-assign on next capture
    last_val       = {}      # (type, ch, num) -> latest raw value 0-127
    prev_raw       = {}      # (type, ch, num) -> raw seen on last apply tick
    toggle_state   = {}      # (type, ch, num) -> bool  (TOGGLE mode state)

DEV_MAP = _MappingLearnState()


# ── Preset templates ──────────────────────────────────────────────────────────
MAPPING_PRESETS = {
    "CAMERA": [
        {"label": "Cam X",         "id_type": "OBJECT", "id_name": "Camera",     "data_path": "location.x",       "value_min": -10.0, "value_max": 10.0},
        {"label": "Cam Y",         "id_type": "OBJECT", "id_name": "Camera",     "data_path": "location.y",       "value_min": -10.0, "value_max": 10.0},
        {"label": "Cam Z",         "id_type": "OBJECT", "id_name": "Camera",     "data_path": "location.z",       "value_min":   0.0, "value_max": 20.0},
        {"label": "Cam Rot X",     "id_type": "OBJECT", "id_name": "Camera",     "data_path": "rotation_euler.x", "value_min":  -1.57,"value_max":  1.57},
        {"label": "Cam Rot Z",     "id_type": "OBJECT", "id_name": "Camera",     "data_path": "rotation_euler.z", "value_min":  -3.14,"value_max":  3.14},
        {"label": "Cam FOV",       "id_type": "OBJECT", "id_name": "Camera",     "data_path": "data.angle",       "value_min":   0.2, "value_max":  1.8},
    ],
    "ACTIVE_OBJECT": [
        {"label": "Obj X",         "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "location.x",       "value_min": -10.0, "value_max": 10.0},
        {"label": "Obj Y",         "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "location.y",       "value_min": -10.0, "value_max": 10.0},
        {"label": "Obj Z",         "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "location.z",       "value_min": -10.0, "value_max": 10.0},
        {"label": "Obj Scale",     "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "scale.x",          "value_min":   0.0, "value_max":  5.0},
        {"label": "Obj Rot Z",     "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "rotation_euler.z", "value_min":   0.0, "value_max":  6.28},
    ],
    "SCENE": [
        {"label": "Frame",         "id_type": "SCENE",  "id_name": "__SCENE__",  "data_path": "frame_current",    "value_min":   0.0, "value_max": 250.0},
        {"label": "Timeline Start","id_type": "SCENE",  "id_name": "__SCENE__",  "data_path": "frame_start",      "value_min":   0.0, "value_max": 250.0},
    ],
    "TRANSPORT": [
        # Knob/encoder → timeline position.  Use encoder_mode=RELATIVE for rotary encoders.
        {"label": "Scrub Frame",   "id_type": "SCENE",  "id_name": "__SCENE__",  "data_path": "frame_current",    "value_min":   0.0, "value_max": 500.0},
        {"label": "Manual BPM",    "id_type": "SCENE",  "id_name": "__SCENE__",  "data_path": "scoresync_manual_bpm", "value_min": 60.0, "value_max": 200.0},
        {"label": "Frame Start",   "id_type": "SCENE",  "id_name": "__SCENE__",  "data_path": "frame_start",      "value_min":   0.0, "value_max": 250.0},
        {"label": "Frame End",     "id_type": "SCENE",  "id_name": "__SCENE__",  "data_path": "frame_end",        "value_min":   1.0, "value_max": 500.0},
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
    """Return the Blender datablock or None. Handles __ACTIVE__ / __SCENE__."""
    if id_name == "__ACTIVE__":
        return getattr(context or bpy.context, "active_object", None)
    if id_name == "__SCENE__":
        return getattr(context or bpy.context, "scene", None)
    col_fn = _ID_COLLECTIONS.get(id_type)
    if col_fn is None:
        return None
    try:
        return col_fn().get(id_name)
    except Exception:
        return None


def _resolve_prop_parent(block, data_path: str):
    """
    Split data_path into (parent_object, attr_name).
    Returns (None, None) on failure.
    Example: block, "location.x" → (block.location, "x")
    """
    try:
        parts = data_path.rsplit(".", 1)
        if len(parts) == 2:
            return block.path_resolve(parts[0]), parts[1]
        return block, parts[0]
    except Exception:
        return None, None


def _rna_type(block, data_path: str):
    """Return RNA property type string ('BOOLEAN', 'INT', 'FLOAT', …) or None."""
    parent, attr = _resolve_prop_parent(block, data_path)
    if parent is None or not attr or "[" in attr:
        return None
    try:
        prop = parent.bl_rna.properties.get(attr)
        return prop.type if prop else None
    except Exception:
        return None


def _set_property(block, data_path: str, value: float) -> bool:
    """
    Set block.<data_path> = value.
    Handles dotted paths, indexed paths (location[0]), booleans, and ints.
    Returns True on success.
    """
    try:
        parent, attr = _resolve_prop_parent(block, data_path)
        if parent is None:
            return False

        # Indexed: e.g. default_value[3]  or  location[0]
        if "[" in attr and not attr.startswith("["):
            name, idx_str = attr.split("[", 1)
            getattr(parent, name)[int(idx_str.rstrip("]"))] = value
            return True

        try:
            rna_prop = parent.bl_rna.properties.get(attr)
            rna_type  = rna_prop.type if rna_prop else None
        except Exception:
            rna_type = None

        if rna_type == 'BOOLEAN':
            setattr(parent, attr, value >= 0.5)
        elif rna_type == 'INT':
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


# ── Apply tick (called from scoresync_timer) ──────────────────────────────────
def apply_mappings_tick(scene) -> bool:
    """
    Apply pending MIDI values to mapped properties.
    Returns True if any property was written (caller should tag_redraw).
    """
    dirty = False

    # Auto-assign after learn capture
    if DEV_MAP.capture_dirty and DEV_MAP.pending_type:
        DEV_MAP.capture_dirty = False
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
            scene.scoresync_mapping_learn_status = (
                f"Captured  {DEV_MAP.pending_type} ch{DEV_MAP.pending_ch+1} "
                f"#{DEV_MAP.pending_num}  — select a mapping then click ← Assign"
            )
        DEV_MAP.target_idx = -1
        dirty = True

    mappings = getattr(scene, "scoresync_mappings", None)
    if not mappings:
        return dirty

    for m in mappings:
        if not m.enabled:
            continue

        key = (m.midi_type, m.channel, m.midi_num)
        raw = DEV_MAP.last_val.get(key)
        if raw is None:
            continue

        prev = DEV_MAP.prev_raw.get(key)
        if raw == prev:
            continue  # unchanged since last tick
        DEV_MAP.prev_raw[key] = raw

        block = _resolve_datablock(m.id_type, m.id_name)
        if block is None:
            continue

        if m.midi_type == "NOTE_ON":
            dirty |= _apply_note_on_mapping(m, block, key, raw, prev)
        elif getattr(m, "encoder_mode", "ABSOLUTE") == "RELATIVE":
            dirty |= _apply_encoder(m, block, key, raw)
        else:
            # CC absolute → continuous linear map
            if _set_property(block, m.data_path, _midi_to_value(raw, m.value_min, m.value_max)):
                dirty = True

    return dirty


def _apply_note_on_mapping(m, block, key, raw: int, prev) -> bool:
    """
    Handle a NOTE_ON mapping update. Returns True if the property was written.

    TOGGLE   — rising edge (0→nonzero) flips state each press.
               boolean props  : toggles the actual RNA bool.
               float/int props: alternates between value_max and value_min.
    MOMENTARY— press = value_max, release = value_min (no state tracking).
    """
    mode = getattr(m, "trigger_mode", "TOGGLE")

    if mode == "MOMENTARY":
        if raw > 0:
            return _set_property(block, m.data_path, m.value_max)
        else:
            ptype = _rna_type(block, m.data_path)
            if ptype != 'BOOLEAN':
                return _set_property(block, m.data_path, m.value_min)
        return False

    # TOGGLE — only act on rising edge
    if raw == 0:
        return False  # note-off: no action in toggle mode

    # Rising edge check (prev was 0 or None)
    if prev is not None and prev > 0:
        return False  # still held, not a new press

    ptype = _rna_type(block, m.data_path)

    if ptype == 'BOOLEAN':
        # Flip the actual RNA bool
        parent, attr = _resolve_prop_parent(block, m.data_path)
        if parent is not None:
            try:
                setattr(parent, attr, not getattr(parent, attr, False))
                return True
            except Exception as e:
                print(f"[ScoreSync] toggle bool failed ({m.data_path}): {e}")
    else:
        # Float/int: alternate between value_max and value_min using toggle_state
        state = DEV_MAP.toggle_state.get(key, False)
        DEV_MAP.toggle_state[key] = not state
        return _set_property(block, m.data_path, m.value_max if not state else m.value_min)

    return False


def _apply_encoder(m, block, key: tuple, raw: int) -> bool:
    """
    Relative encoder handling.
    Most encoders use offset-binary: center=64, >64=CW (+), <64=CCW (-).
    Each message is a step, not an absolute position.

    After applying, reset last_val to 64 (center) so the same delta
    doesn't re-fire on the next timer tick.
    """
    if raw == 64:
        return False  # no movement

    # Dead-zone ±1 around center to ignore jitter
    if 63 <= raw <= 65:
        return False

    range_size = m.value_max - m.value_min
    if range_size == 0:
        return False

    step_pct = max(0.001, getattr(m, "encoder_step", 1.0) / 100.0)

    # Offset from center: +1…+63 (CW), -1…-64 (CCW)
    offset = raw - 64
    # Scale: full-speed turn (offset ±63) = 1× step, slow nudge = fraction
    delta = (offset / 63.0) * step_pct * range_size

    parent, attr = _resolve_prop_parent(block, m.data_path)
    if parent is None:
        return False

    try:
        current = float(getattr(parent, attr, m.value_min))
        new_val = max(m.value_min, min(m.value_max, current + delta))
        if _set_property(block, m.data_path, new_val):
            # Reset to center so same raw doesn't re-fire next tick
            DEV_MAP.last_val[key] = 64
            DEV_MAP.prev_raw[key] = 64
            return True
    except Exception as e:
        print(f"[ScoreSync] encoder failed ({m.data_path}): {e}")
    return False


def ingest_midi_for_mapping(midi_type: str, channel: int, num: int, val: int):
    """
    Called from listener thread. Stores latest raw value; captures learn event.
    Dict assignment is atomic in CPython — no lock needed for last_val.
    """
    key = (midi_type, channel, num)
    DEV_MAP.last_val[key] = val

    if DEV_MAP.learning:
        DEV_MAP.pending_type  = midi_type
        DEV_MAP.pending_ch    = channel
        DEV_MAP.pending_num   = num
        DEV_MAP.pending_val   = val
        DEV_MAP.pending_ts    = time.time()
        DEV_MAP.capture_dirty = True
        DEV_MAP.learning      = False  # one capture, then stop


# ── Property group ────────────────────────────────────────────────────────────
class ScoreSyncMapping(bpy.types.PropertyGroup):
    label    : bpy.props.StringProperty(name="Label", default="Mapping")
    enabled  : bpy.props.BoolProperty(name="Enabled", default=True)
    id_type  : bpy.props.EnumProperty(
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
    id_name  : bpy.props.StringProperty(name="Datablock Name", default="")
    data_path: bpy.props.StringProperty(name="Property Path",  default="location.x")
    midi_type: bpy.props.EnumProperty(
        name="MIDI Type",
        items=[("CC", "CC", "Control Change"), ("NOTE_ON", "Note On", "")],
        default="CC",
    )
    trigger_mode: bpy.props.EnumProperty(
        name="Trigger Mode",
        description="How NOTE_ON events drive this property",
        items=[
            ("TOGGLE",    "Toggle",    "Each press alternates between min/max (or flips bool)"),
            ("MOMENTARY", "Momentary", "Held = value_max, released = value_min"),
        ],
        default="TOGGLE",
    )
    encoder_mode: bpy.props.EnumProperty(
        name="Encoder Mode",
        description="CC input interpretation — use Relative for rotary encoders",
        items=[
            ("ABSOLUTE", "Knob (Absolute)",  "0–127 maps linearly to min–max"),
            ("RELATIVE", "Encoder (Relative)", "Each tick nudges the value; 65–127 = CW, 0–63 = CCW"),
        ],
        default="ABSOLUTE",
    )
    channel  : bpy.props.IntProperty(name="Channel",  default=0, min=0,   max=15)
    midi_num : bpy.props.IntProperty(name="CC / Note", default=0, min=0,  max=127)
    value_min: bpy.props.FloatProperty(name="Min", default=0.0)
    value_max: bpy.props.FloatProperty(name="Max", default=1.0)
    encoder_step: bpy.props.FloatProperty(
        name="Step %",
        description="How much of the value range each encoder tick moves (percent)",
        default=1.0, min=0.1, max=20.0,
        subtype='PERCENTAGE',
    )


# ── Operators ─────────────────────────────────────────────────────────────────
class SCORESYNC_OT_mapping_learn_start(bpy.types.Operator):
    bl_idname   = "scoresync.mapping_learn_start"
    bl_label    = "Learn MIDI"
    bl_description = "Touch any control — ScoreSync captures the next CC or Note"

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
    """Manually assign the last captured MIDI event to a mapping slot."""
    bl_idname = "scoresync.mapping_assign"
    bl_label  = "Assign Learned MIDI to Slot"

    index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        if not DEV_MAP.pending_type:
            self.report({'WARNING'}, "No MIDI event captured yet — click Learn first.")
            return {'CANCELLED'}
        scene    = context.scene
        mappings = scene.scoresync_mappings
        if not (0 <= self.index < len(mappings)):
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
        idx   = self.index if self.index >= 0 else scene.scoresync_mapping_index
        if 0 <= idx < len(scene.scoresync_mappings):
            scene.scoresync_mappings.remove(idx)
            scene.scoresync_mapping_index = max(0, idx - 1)
        return {'FINISHED'}


class SCORESYNC_OT_mapping_apply_preset(bpy.types.Operator):
    bl_idname   = "scoresync.mapping_apply_preset"
    bl_label    = "Apply Mapping Preset"
    bl_description = "Add preset mappings for Camera, Active Object, or Scene"

    preset: bpy.props.EnumProperty(
        name="Preset",
        items=[
            ("CAMERA",        "Camera",        "Camera transform + FOV"),
            ("ACTIVE_OBJECT", "Active Object", "Active object transform"),
            ("SCENE",         "Scene",         "Frame / timeline"),
            ("TRANSPORT",     "Transport",     "Scrub frame, BPM, timeline start/end via knob/encoder"),
        ],
        default="CAMERA",
    )

    def execute(self, context):
        scene    = context.scene
        template = MAPPING_PRESETS.get(self.preset, [])
        used_ccs = {m.midi_num for m in scene.scoresync_mappings if m.midi_type == "CC"}
        next_cc  = 1
        for t in template:
            while next_cc in used_ccs:
                next_cc += 1
            m           = scene.scoresync_mappings.add()
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
    bl_idname   = "scoresync.mapping_export"
    bl_label    = "Export Mappings"
    bl_description = "Save all MIDI mappings to a JSON file"

    filepath   : bpy.props.StringProperty(subtype="FILE_PATH")
    filename   : bpy.props.StringProperty(default="scoresync_mappings.json")
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        self.filename = "scoresync_mappings.json"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        data = [
            {
                "label":        m.label,
                "enabled":      m.enabled,
                "id_type":      m.id_type,
                "id_name":      m.id_name,
                "data_path":    m.data_path,
                "midi_type":    m.midi_type,
                "trigger_mode": m.trigger_mode,
                "channel":      m.channel,
                "midi_num":     m.midi_num,
                "value_min":    m.value_min,
                "value_max":    m.value_max,
            }
            for m in context.scene.scoresync_mappings
        ]
        dst = bpy.path.abspath(self.filepath)
        if not dst.endswith(".json"):
            dst = os.path.join(dst, self.filename)
        try:
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                json.dump({"version": 2, "mappings": data}, f, indent=2)
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {e}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Exported {len(data)} mappings to {dst}")
        return {'FINISHED'}


class SCORESYNC_OT_mapping_import(bpy.types.Operator):
    bl_idname   = "scoresync.mapping_import"
    bl_label    = "Import Mappings"
    bl_description = "Load MIDI mappings from a JSON file (appends to existing)"

    filepath   : bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        src = bpy.path.abspath(self.filepath)
        try:
            with open(src, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {e}")
            return {'CANCELLED'}

        rows = doc.get("mappings", [])
        for row in rows:
            m              = context.scene.scoresync_mappings.add()
            m.label        = row.get("label",        "Imported")
            m.enabled      = row.get("enabled",      True)
            m.id_type      = row.get("id_type",      "OBJECT")
            m.id_name      = row.get("id_name",      "")
            m.data_path    = row.get("data_path",    "location.x")
            m.midi_type    = row.get("midi_type",    "CC")
            m.trigger_mode = row.get("trigger_mode", "TOGGLE")
            m.channel      = row.get("channel",      0)
            m.midi_num     = row.get("midi_num",     0)
            m.value_min    = row.get("value_min",    0.0)
            m.value_max    = row.get("value_max",    1.0)

        self.report({'INFO'}, f"Imported {len(rows)} mappings from {os.path.basename(src)}")
        return {'FINISHED'}


class SCORESYNC_OT_mapping_clear_binding(bpy.types.Operator):
    """Clear the MIDI binding from this slot (keeps the target property)."""
    bl_idname  = "scoresync.mapping_clear_binding"
    bl_label   = "Reset MIDI Binding"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        scene    = context.scene
        mappings = getattr(scene, "scoresync_mappings", None)
        idx      = self.index if self.index >= 0 else getattr(scene, "scoresync_mapping_index", -1)
        if not mappings or not (0 <= idx < len(mappings)):
            return {'CANCELLED'}
        m           = mappings[idx]
        m.midi_type = "CC"
        m.channel   = 0
        m.midi_num  = 0
        # Clear any accumulated toggle state for this slot
        DEV_MAP.toggle_state.pop((m.midi_type, m.channel, m.midi_num), None)
        scene.scoresync_mapping_learn_status = f"Binding cleared for \"{m.label}\""
        self.report({'INFO'}, f"MIDI binding cleared: {m.label}")
        return {'FINISHED'}


# ── Registration ──────────────────────────────────────────────────────────────
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
