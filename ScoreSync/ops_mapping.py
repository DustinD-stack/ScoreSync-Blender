"""
ScoreSync v2.2 — ops_mapping.py
Universal MIDI Action Mapping System

target_mode values
------------------
  PROPERTY   — Drive any RNA property (CC continuous, NOTE toggle/momentary).
                Unchanged behaviour from v2.0 — all existing mappings keep working.
  OPERATOR   — Run any Blender operator on MIDI trigger (NOTE press / CC threshold).
  FUNCTION   — Call a built-in ScoreSync action from ACTION_REGISTRY.
  KEYFRAME   — Insert a keyframe for a property on trigger.
  TRANSPORT  — DAW transport / playback control.

MIDI types supported
--------------------
  CC, NOTE_ON, NOTE_OFF, PITCH_BEND (normalised 0-127), AFTERTOUCH,
  POLY_AT (per-note pressure), PROG_CHG

Thread safety
-------------
  ingest_midi_for_mapping()  — called from MIDI threads; only writes
      DEV_MAP.last_val / pending capture fields.  No bpy access.
  apply_mappings_tick()      — called from scoresync_timer() on the
      Blender main thread; all bpy writes, operator calls, keyframe
      inserts happen here.
"""

import bpy
import json
import os
import time


# ── Learn state ───────────────────────────────────────────────────────────────
class _MappingLearnState:
    learning       = False
    pending_type   = ""      # "CC" | "NOTE_ON" | …
    pending_ch     = 0
    pending_num    = 0
    pending_val    = 0
    pending_ts     = 0.0
    capture_dirty  = False   # set by MIDI thread; consumed by main timer
    target_idx     = -1      # slot to auto-assign on next capture
    last_val       = {}      # (type, ch, num) -> latest raw value 0-127
    prev_raw       = {}      # (type, ch, num) -> raw seen on last apply tick
    toggle_state   = {}      # (type, ch, num) -> bool  (TOGGLE mode state)
    encoder_accum  = {}      # ("CC", ch, num) -> accumulated offset (RELATIVE encoders)

DEV_MAP = _MappingLearnState()


# ── Curated path library ──────────────────────────────────────────────────────

_CURATED_PATHS = {
    "OBJECT": [
        ("location.x",                          "Location X"),
        ("location.y",                          "Location Y"),
        ("location.z",                          "Location Z"),
        ("rotation_euler.x",                    "Rotation X (Euler)"),
        ("rotation_euler.y",                    "Rotation Y (Euler)"),
        ("rotation_euler.z",                    "Rotation Z (Euler)"),
        ("scale.x",                             "Scale X"),
        ("scale.y",                             "Scale Y"),
        ("scale.z",                             "Scale Z"),
        ("hide_viewport",                       "Hide in Viewport"),
        ("hide_render",                         "Hide in Render"),
        ("data.angle",                          "Camera FOV"),
        ("data.lens",                           "Camera Focal Length"),
        ("data.clip_start",                     "Camera Clip Start"),
        ("data.clip_end",                       "Camera Clip End"),
        ("data.dof.focus_distance",             "DOF Focus Distance"),
        ("data.dof.aperture_fstop",             "DOF F-Stop"),
        ("data.energy",                         "Light Energy"),
        ("data.spot_size",                      "Spot Size"),
        ("data.spot_blend",                     "Spot Blend"),
        ("data.shadow_soft_size",               "Shadow Soft Size"),
        ("active_material.roughness",           "Active Mat Roughness"),
        ("active_material.metallic",            "Active Mat Metallic"),
        ("active_material.specular_intensity",  "Active Mat Specular"),
        ("active_material.alpha",               "Active Mat Alpha"),
    ],
    "SCENE": [
        ("frame_current",                       "Current Frame"),
        ("frame_start",                         "Frame Start"),
        ("frame_end",                           "Frame End"),
        ("scoresync_manual_bpm",                "ScoreSync Manual BPM"),
        ("render.resolution_x",                 "Render Width"),
        ("render.resolution_y",                 "Render Height"),
        ("render.resolution_percentage",        "Render Scale %"),
        ("eevee.bloom_intensity",               "EEVEE Bloom Intensity"),
        ("eevee.bloom_radius",                  "EEVEE Bloom Radius"),
        ("eevee.bokeh_max_size",                "EEVEE Bokeh Size"),
        ("eevee.use_bloom",                     "EEVEE Bloom On/Off"),
        ("eevee.volumetric_start",              "EEVEE Vol Start"),
        ("eevee.volumetric_end",                "EEVEE Vol End"),
        ("world.node_tree.nodes['Background'].inputs[1].default_value",
                                                "World Strength"),
    ],
    "MATERIAL": [
        ("roughness",                           "Roughness"),
        ("metallic",                            "Metallic"),
        ("specular_intensity",                  "Specular"),
        ("alpha",                               "Alpha"),
        ("node_tree.nodes['Principled BSDF'].inputs[7].default_value",
                                                "Principled Roughness"),
        ("node_tree.nodes['Principled BSDF'].inputs[6].default_value",
                                                "Principled Metallic"),
        ("node_tree.nodes['Principled BSDF'].inputs[19].default_value",
                                                "Principled Alpha"),
        ("node_tree.nodes['Principled BSDF'].inputs[0].default_value[0]",
                                                "Principled Base R"),
        ("node_tree.nodes['Principled BSDF'].inputs[0].default_value[1]",
                                                "Principled Base G"),
        ("node_tree.nodes['Principled BSDF'].inputs[0].default_value[2]",
                                                "Principled Base B"),
    ],
    "WORLD": [
        ("node_tree.nodes['Background'].inputs[1].default_value",
                                                "World Strength"),
        ("node_tree.nodes['Background'].inputs[0].default_value[0]",
                                                "World Color R"),
        ("node_tree.nodes['Background'].inputs[0].default_value[1]",
                                                "World Color G"),
        ("node_tree.nodes['Background'].inputs[0].default_value[2]",
                                                "World Color B"),
    ],
}


def _scan_rna_paths_for_block(block):
    results = []
    seen    = set()

    def _walk(obj, prefix, depth):
        if depth > 2 or obj is None:
            return
        try:
            rna_props = obj.bl_rna.properties
        except Exception:
            return
        for prop in rna_props:
            ident = prop.identifier
            if ident.startswith("_") or ident in ("rna_type", "bl_rna"):
                continue
            path = f"{prefix}.{ident}" if prefix else ident
            if path in seen:
                continue
            ptype = prop.type
            if ptype in ("FLOAT", "INT", "BOOLEAN"):
                is_arr = getattr(prop, "is_array", False)
                arr_len = getattr(prop, "array_length", 1)
                if not is_arr or arr_len == 0:
                    seen.add(path)
                    results.append((path, prop.name or ident))
                elif arr_len <= 4:
                    for i, c in enumerate(["X", "Y", "Z", "W"][:arr_len]):
                        sp = f"{path}[{i}]"
                        if sp not in seen:
                            seen.add(sp)
                            results.append((sp, f"{prop.name or ident} {c}"))
            elif ptype == "POINTER" and depth < 2:
                try:
                    sub = getattr(obj, ident, None)
                    if sub is not None and hasattr(sub, "bl_rna"):
                        _walk(sub, path, depth + 1)
                except Exception:
                    pass

    _walk(block, "", 0)
    return results


def _build_path_enum_items(id_type: str, block):
    seen  = set()
    items = []

    def _add(path, label, cat):
        if path not in seen:
            seen.add(path)
            items.append((path, label, f"[{cat}]  {path}"))

    for path, label in _CURATED_PATHS.get(id_type, []):
        _add(path, label, "Common")

    if block is not None:
        for path, label in _scan_rna_paths_for_block(block):
            _add(path, label, "Scanned")

    return items or [("location.x", "Location X", "location.x")]


_path_enum_cache: list = [("location.x", "Location X", "location.x")]


def _path_enum_items(self, context):
    return _path_enum_cache


# ── Path picker operator ──────────────────────────────────────────────────────

class SCORESYNC_OT_pick_data_path(bpy.types.Operator):
    """Browse all available RNA paths for the selected datablock type"""
    bl_idname   = "scoresync.pick_data_path"
    bl_label    = "Pick Data Path"
    bl_options  = {'REGISTER', 'UNDO'}
    bl_property = "choice"

    mapping_index: bpy.props.IntProperty(default=-1, options={'HIDDEN'})

    choice: bpy.props.EnumProperty(
        name="Path",
        description="Select an RNA property path",
        items=_path_enum_items,
    )

    def invoke(self, context, event):
        global _path_enum_cache
        scene    = context.scene
        mappings = getattr(scene, "scoresync_mappings", None)
        idx      = self.mapping_index
        if mappings is None or idx < 0 or idx >= len(mappings):
            self.report({'WARNING'}, "ScoreSync: no mapping selected")
            return {'CANCELLED'}

        m     = mappings[idx]
        block = _resolve_datablock(m.id_type, m.id_name, context)
        _path_enum_cache = _build_path_enum_items(m.id_type, block)

        context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        scene    = context.scene
        mappings = getattr(scene, "scoresync_mappings", None)
        idx      = self.mapping_index
        if mappings is None or idx < 0 or idx >= len(mappings):
            return {'CANCELLED'}

        m           = mappings[idx]
        m.data_path = self.choice

        for path, label, _ in _path_enum_cache:
            if path == self.choice:
                if not m.label or m.label.startswith("Mapping "):
                    m.label = label
                break

        return {'FINISHED'}


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
        {"label": "Scrub Frame",   "id_type": "SCENE",  "id_name": "__SCENE__",  "data_path": "frame_current",    "value_min":   0.0, "value_max": 500.0},
        {"label": "Manual BPM",    "id_type": "SCENE",  "id_name": "__SCENE__",  "data_path": "scoresync_manual_bpm", "value_min": 60.0, "value_max": 200.0},
        {"label": "Frame Start",   "id_type": "SCENE",  "id_name": "__SCENE__",  "data_path": "frame_start",      "value_min":   0.0, "value_max": 250.0},
        {"label": "Frame End",     "id_type": "SCENE",  "id_name": "__SCENE__",  "data_path": "frame_end",        "value_min":   1.0, "value_max": 500.0},
    ],
    "TRANSPORT_BUTTONS": [
        {"label": "Play/Stop",     "target_mode": "TRANSPORT", "transport_action": "TOGGLE_PLAY",  "midi_type": "NOTE_ON", "value_min": 0.0, "value_max": 1.0},
        {"label": "Rewind",        "target_mode": "TRANSPORT", "transport_action": "REWIND_START", "midi_type": "NOTE_ON", "value_min": 0.0, "value_max": 1.0},
        {"label": "Next Marker",   "target_mode": "TRANSPORT", "transport_action": "NEXT_MARKER",  "midi_type": "NOTE_ON", "value_min": 0.0, "value_max": 1.0},
        {"label": "Prev Marker",   "target_mode": "TRANSPORT", "transport_action": "PREV_MARKER",  "midi_type": "NOTE_ON", "value_min": 0.0, "value_max": 1.0},
    ],
    "KEYFRAME_TOOLS": [
        {"label": "KF Loc X",   "target_mode": "KEYFRAME", "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "location.x",       "value_min": 0.0, "value_max": 1.0},
        {"label": "KF Loc Y",   "target_mode": "KEYFRAME", "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "location.y",       "value_min": 0.0, "value_max": 1.0},
        {"label": "KF Loc Z",   "target_mode": "KEYFRAME", "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "location.z",       "value_min": 0.0, "value_max": 1.0},
        {"label": "KF Rot Z",   "target_mode": "KEYFRAME", "id_type": "OBJECT", "id_name": "__ACTIVE__", "data_path": "rotation_euler.z", "value_min": 0.0, "value_max": 1.0},
    ],
    "OPERATOR_TOOLS": [
        {"label": "Add Cube",      "target_mode": "OPERATOR", "operator_idname": "mesh.primitive_cube_add",  "operator_props_json": '{"size": 2.0}',  "value_min": 0.0, "value_max": 1.0},
        {"label": "Delete Sel.",   "target_mode": "OPERATOR", "operator_idname": "object.delete",           "operator_props_json": '{}',             "value_min": 0.0, "value_max": 1.0},
        {"label": "Frame All",     "target_mode": "OPERATOR", "operator_idname": "view3d.view_all",         "operator_props_json": '{}',             "value_min": 0.0, "value_max": 1.0},
        {"label": "Save File",     "target_mode": "OPERATOR", "operator_idname": "wm.save_mainfile",        "operator_props_json": '{}',             "value_min": 0.0, "value_max": 1.0},
    ],
    "MATERIAL_CONTROLS": [
        {"label": "Roughness",   "id_type": "MATERIAL", "id_name": "",           "data_path": "roughness",        "value_min": 0.0, "value_max": 1.0},
        {"label": "Metallic",    "id_type": "MATERIAL", "id_name": "",           "data_path": "metallic",         "value_min": 0.0, "value_max": 1.0},
        {"label": "Alpha",       "id_type": "MATERIAL", "id_name": "",           "data_path": "alpha",            "value_min": 0.0, "value_max": 1.0},
    ],
    "LIGHT_CONTROLS": [
        {"label": "Light Energy", "id_type": "OBJECT", "id_name": "",           "data_path": "data.energy",       "value_min": 0.0, "value_max": 1000.0},
        {"label": "Spot Size",    "id_type": "OBJECT", "id_name": "",           "data_path": "data.spot_size",    "value_min": 0.1, "value_max": 3.14},
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
    Handles paths like 'location.x', 'data.angle', 'default_value[0]'.
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
    Handles dotted paths, indexed paths (location[0], default_value[2]),
    and pure-index attrs like [0] (when parent is already the array).
    Returns True on success.
    """
    try:
        parent, attr = _resolve_prop_parent(block, data_path)
        if parent is None:
            return False

        # Pure index attribute: attr == "[0]"  (parent IS the array)
        if attr.startswith("["):
            parent[int(attr.strip("[]"))] = value
            return True

        # Indexed inside a named attr: e.g. default_value[3]  or  location[0]
        if "[" in attr:
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


def get_property_value(block, data_path: str):
    """Get block.<data_path> value. Returns float or None on failure."""
    try:
        parent, attr = _resolve_prop_parent(block, data_path)
        if parent is None:
            return None
        if attr.startswith("["):
            return float(parent[int(attr.strip("[]"))])
        if "[" in attr:
            name, idx_str = attr.split("[", 1)
            return float(getattr(parent, name)[int(idx_str.rstrip("]"))])
        return float(getattr(parent, attr))
    except Exception:
        return None


def _midi_to_value(raw: int, v_min: float, v_max: float) -> float:
    t = max(0, min(127, raw)) / 127.0
    return v_min + t * (v_max - v_min)


# ── Action Registry (FUNCTION mode) ──────────────────────────────────────────

def _act_add_keyframe(ctx, scene, m, raw, value, **kw):
    obj = ctx.active_object
    if obj is None:
        raise RuntimeError("No active object")
    data_path = kw.get("data_path", m.data_path) or "location"
    obj.keyframe_insert(data_path=data_path, frame=scene.frame_current)


def _act_toggle_visibility(ctx, scene, m, raw, value, **kw):
    for obj in (ctx.selected_objects or []):
        obj.hide_viewport = not obj.hide_viewport


def _act_switch_next_camera(ctx, scene, m, raw, value, **kw):
    cams = [o for o in bpy.data.objects if o.type == 'CAMERA']
    if not cams:
        return
    active = scene.camera
    try:
        idx = cams.index(active)
    except ValueError:
        idx = -1
    scene.camera = cams[(idx + 1) % len(cams)]


def _act_render_preview(ctx, scene, m, raw, value, **kw):
    bpy.ops.render.opengl(animation=False)


def _act_reset_mappings_state(ctx, scene, m, raw, value, **kw):
    DEV_MAP.last_val.clear()
    DEV_MAP.prev_raw.clear()
    DEV_MAP.toggle_state.clear()
    DEV_MAP.encoder_accum.clear()


def _act_fire_sampler_pad(ctx, scene, m, raw, value, **kw):
    bank = int(kw.get("bank", 0))
    pad  = int(kw.get("pad",  0))
    try:
        bpy.ops.scoresync.sampler_fire_pad(bank_index=bank, pad_index=pad)
    except Exception:
        pass


def _act_fx_fire_slot(ctx, scene, m, raw, value, **kw):
    idx = int(kw.get("index", 0))
    try:
        bpy.ops.scoresync.fx_fire_slot(index=idx)
    except Exception:
        pass


ACTION_REGISTRY = {
    "scoresync.add_keyframe_current":       _act_add_keyframe,
    "scoresync.toggle_selected_visibility": _act_toggle_visibility,
    "scoresync.switch_next_camera":         _act_switch_next_camera,
    "scoresync.render_viewport_preview":    _act_render_preview,
    "scoresync.reset_mappings_state":       _act_reset_mappings_state,
    "scoresync.fire_sampler_pad":           _act_fire_sampler_pad,
    "scoresync.fx_fire_slot":               _act_fx_fire_slot,
}

ACTION_REGISTRY_ITEMS = [
    (k, k.split(".")[-1].replace("_", " ").title(), k)
    for k in sorted(ACTION_REGISTRY)
]


# ── Trigger checker ───────────────────────────────────────────────────────────

def _check_trigger(m, raw: int, prev) -> bool:
    """
    Returns True if the raw MIDI value should fire the action for mapping m.
    Uses m.fire_on (RISING / FALLING / BOTH / CHANGE) and m.cc_threshold.
    """
    fire_on   = getattr(m, "fire_on",       "RISING")
    midi_type = m.midi_type
    thresh    = int(getattr(m, "cc_threshold", 64))

    if midi_type in ("NOTE_ON", "POLY_AT"):
        rising  = (raw > 0)  and (prev is None or prev == 0)
        falling = (raw == 0) and (prev is not None and prev > 0)
    elif midi_type == "NOTE_OFF":
        rising  = (raw > 0)  and (prev is None or prev == 0)
        falling = False
    elif midi_type in ("CC", "PITCH_BEND", "AFTERTOUCH"):
        rising  = (raw >= thresh) and (prev is None or prev < thresh)
        falling = (raw < thresh)  and (prev is not None and prev >= thresh)
    elif midi_type == "PROG_CHG":
        return True   # every program change event fires
    else:
        rising  = raw != (prev if prev is not None else -1)
        falling = False

    if fire_on == "RISING":  return rising
    if fire_on == "FALLING": return falling
    if fire_on == "BOTH":    return rising or falling
    return raw != (prev if prev is not None else -1)   # CHANGE


# ── Custom Python executor ────────────────────────────────────────────────────

def _run_custom_python(m, code: str, raw: int, value: float, scene) -> bool:
    """Execute custom_python in a restricted namespace. Dev-mode only."""
    ns = {
        "bpy":     bpy,
        "context": bpy.context,
        "scene":   scene,
        "mapping": m,
        "raw":     raw,
        "value":   value,
    }
    try:
        exec(compile(code, "<scoresync_custom>", "exec"), ns)  # noqa: S102
        m.last_error = ""
        return True
    except Exception as e:
        m.last_error = str(e)[:80]
        print(f"[ScoreSync] Custom Python error in '{m.label}': {e}")
        return False


# ── Mode-specific apply functions ─────────────────────────────────────────────

def _apply_operator_mapping(m, raw: int, prev, scene) -> bool:
    if not _check_trigger(m, raw, prev):
        return False
    idname = (getattr(m, "operator_idname", "") or "").strip()
    if not idname:
        try: m.last_error = "No operator set"
        except Exception: pass
        return False
    try:
        props = json.loads(getattr(m, "operator_props_json", "{}") or "{}")
    except Exception:
        props = {}
    try:
        parts = idname.split(".", 1)
        if len(parts) != 2:
            try: m.last_error = f"Bad idname: {idname}"
            except Exception: pass
            return False
        cat, name = parts
        op_fn = getattr(getattr(bpy.ops, cat, None), name, None)
        if op_fn is None:
            try: m.last_error = f"Not found: {idname}"
            except Exception: pass
            return False
        op_fn(**props)
        try: m.last_error = ""
        except Exception: pass
        print(f"[ScoreSync MAP] {m.midi_type} ch{m.channel+1} #{m.midi_num} → OPERATOR {idname}")
        return True
    except Exception as e:
        msg = str(e)[:80]
        try: m.last_error = msg
        except Exception: pass
        print(f"[ScoreSync MAP] Operator {idname} error: {e}")
        return False


def _apply_function_mapping(m, raw: int, prev, scene) -> bool:
    if not _check_trigger(m, raw, prev):
        return False
    fn = ACTION_REGISTRY.get(getattr(m, "function_id", "") or "")
    if fn is None:
        try: m.last_error = f"Unknown: {getattr(m, 'function_id', '')}"
        except Exception: pass
        return False
    try:
        args = json.loads(getattr(m, "function_args_json", "{}") or "{}")
    except Exception:
        args = {}
    mapped = _midi_to_value(raw, m.value_min, m.value_max)
    try:
        fn(bpy.context, scene, m, raw, mapped, **args)
        try: m.last_error = ""
        except Exception: pass
        print(f"[ScoreSync MAP] {m.midi_type} ch{m.channel+1} #{m.midi_num} → FUNCTION {getattr(m,'function_id','?')}")
        return True
    except Exception as e:
        msg = str(e)[:80]
        try: m.last_error = msg
        except Exception: pass
        print(f"[ScoreSync MAP] Function {getattr(m,'function_id','')} error: {e}")
        return False


def _apply_keyframe_mapping(m, block, raw: int, prev, scene) -> bool:
    if not _check_trigger(m, raw, prev):
        return False
    if block is None:
        try: m.last_error = "Target block missing"
        except Exception: pass
        return False
    kf_mode  = getattr(m, "keyframe_frame_mode",  "CURRENT")
    val_mode = getattr(m, "keyframe_value_mode",   "CURRENT")
    frame = (int(_midi_to_value(raw, m.value_min, m.value_max))
             if kf_mode == "MIDI_TO_FRAME" else scene.frame_current)
    if val_mode == "MAPPED":
        _set_property(block, m.data_path, _midi_to_value(raw, m.value_min, m.value_max))
    try:
        block.keyframe_insert(data_path=m.data_path, frame=frame)
        try: m.last_error = ""
        except Exception: pass
        print(f"[ScoreSync MAP] Keyframe {m.data_path} @ frame {frame}")
        return True
    except Exception as e:
        try: m.last_error = str(e)[:80]
        except Exception: pass
        print(f"[ScoreSync MAP] Keyframe error ({m.data_path}): {e}")
        return False


def _apply_transport_mapping_entry(m, raw: int, prev, scene) -> bool:
    if not _check_trigger(m, raw, prev):
        return False
    action = getattr(m, "transport_action", "TOGGLE_PLAY")
    try:
        if action == "PLAY":
            bpy.ops.scoresync.tx_play()
        elif action == "STOP":
            bpy.ops.scoresync.tx_stop()
        elif action == "TOGGLE_PLAY":
            scr = getattr(bpy.context, "screen", None)
            if scr and scr.is_animation_playing:
                bpy.ops.screen.animation_play()
            else:
                bpy.ops.screen.animation_play()
        elif action == "REWIND_START":
            scene.frame_current = scene.frame_start
        elif action == "NEXT_MARKER":
            bpy.ops.screen.marker_jump(next=True)
        elif action == "PREV_MARKER":
            bpy.ops.screen.marker_jump(next=False)
        elif action == "LOCATE_CURRENT":
            try:
                from .ops_transport import _send_spp
                _send_spp(scene, scene.frame_current)
            except Exception:
                pass
        elif action == "SET_FRAME_FROM_CC":
            scene.frame_current = int(_midi_to_value(raw, m.value_min, m.value_max))
        try: m.last_error = ""
        except Exception: pass
        print(f"[ScoreSync MAP] {m.midi_type} ch{m.channel+1} #{m.midi_num} → TRANSPORT {action}")
        return True
    except Exception as e:
        try: m.last_error = str(e)[:80]
        except Exception: pass
        print(f"[ScoreSync MAP] Transport {action} error: {e}")
        return False


# ── Apply tick (called from scoresync_timer on main thread) ───────────────────

def apply_mappings_tick(scene) -> bool:
    """
    Apply pending MIDI values to mapped properties / actions.
    Returns True if anything changed (caller should tag_redraw).
    """
    dirty = False

    # ── Bank system ticks ─────────────────────────────────────────────────────
    global _bank_bindings_cache
    bindings = getattr(scene, "scoresync_bank_bindings", None)
    if bindings is not None:
        while len(bindings) < 4:
            bindings.add()
        _bank_bindings_cache = [
            (b.midi_type, b.channel, b.midi_num, i)
            for i, b in enumerate(bindings)
            if b.enabled
        ]

    if DEV_BANK.capture_dirty:
        DEV_BANK.capture_dirty = False
        if bindings and 0 <= DEV_BANK.learn_target < len(bindings):
            b            = bindings[DEV_BANK.learn_target]
            b.midi_type  = DEV_BANK.pending_type
            b.channel    = DEV_BANK.pending_ch
            b.midi_num   = DEV_BANK.pending_num
            b.enabled    = True
            lbl          = BANK_LABELS[DEV_BANK.learn_target]
            scene.scoresync_bank_learn_status = (
                f"Bank {lbl} → {b.midi_type} ch{b.channel+1} #{b.midi_num}"
            )
            dirty = True

    if DEV_BANK.pending_switch >= 0:
        scene.scoresync_active_mapping_bank = DEV_BANK.pending_switch
        DEV_BANK.pending_switch = -1
        dirty = True

    # ── Mapping learn capture ─────────────────────────────────────────────────
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

    active_bank = getattr(scene, "scoresync_active_mapping_bank", 0)
    debug       = getattr(scene, "scoresync_debug", False)

    for m in mappings:
        if not m.enabled:
            continue
        if getattr(m, "bank", 0) != active_bank:
            continue

        key         = (m.midi_type, m.channel, m.midi_num)
        target_mode = getattr(m, "target_mode", "PROPERTY")

        # Relative encoder — only for PROPERTY CC
        if (target_mode == "PROPERTY"
                and m.midi_type == "CC"
                and getattr(m, "encoder_mode", "ABSOLUTE") == "RELATIVE"):
            if key in DEV_MAP.encoder_accum:
                block = _resolve_datablock(m.id_type, m.id_name)
                if block is not None:
                    dirty |= _apply_encoder(m, block, key)
            continue

        raw = DEV_MAP.last_val.get(key)
        if raw is None:
            continue

        prev = DEV_MAP.prev_raw.get(key)
        if raw == prev:
            continue  # no change this tick
        DEV_MAP.prev_raw[key] = raw

        try:
            if target_mode == "PROPERTY":
                block = _resolve_datablock(m.id_type, m.id_name)
                if block is None:
                    continue
                if m.midi_type == "NOTE_ON":
                    if _apply_note_on_mapping(m, block, key, raw, prev):
                        dirty = True
                        if debug:
                            print(f"[ScoreSync MAP] NOTE ch{m.channel+1} #{m.midi_num} → PROPERTY {m.id_name}.{m.data_path}")
                else:
                    mapped = _midi_to_value(raw, m.value_min, m.value_max)
                    if _set_property(block, m.data_path, mapped):
                        dirty = True
                        if debug:
                            print(f"[ScoreSync MAP] {m.midi_type} ch{m.channel+1} #{m.midi_num} → PROPERTY {m.id_name}.{m.data_path} = {mapped:.3f}")

            elif target_mode == "OPERATOR":
                if _apply_operator_mapping(m, raw, prev, scene):
                    dirty = True

            elif target_mode == "FUNCTION":
                if _apply_function_mapping(m, raw, prev, scene):
                    dirty = True

            elif target_mode == "KEYFRAME":
                block = _resolve_datablock(m.id_type, m.id_name)
                if _apply_keyframe_mapping(m, block, raw, prev, scene):
                    dirty = True

            elif target_mode == "TRANSPORT":
                if _apply_transport_mapping_entry(m, raw, prev, scene):
                    dirty = True

            # Custom Python — requires developer opt-in
            py_code = getattr(m, "custom_python", "")
            if py_code and getattr(scene, "scoresync_allow_custom_python", False):
                if _run_custom_python(m, py_code, raw,
                                      _midi_to_value(raw, m.value_min, m.value_max), scene):
                    dirty = True

        except Exception as e:
            print(f"[ScoreSync MAP] Unhandled error in '{m.label}': {e}")
            try:
                m.last_error = str(e)[:80]
            except Exception:
                pass

    return dirty


# ── NOTE_ON property handler ──────────────────────────────────────────────────

def _apply_note_on_mapping(m, block, key, raw: int, prev) -> bool:
    mode = getattr(m, "trigger_mode", "TOGGLE")

    if mode == "MOMENTARY":
        if raw > 0:
            return _set_property(block, m.data_path, m.value_max)
        else:
            ptype = _rna_type(block, m.data_path)
            if ptype != 'BOOLEAN':
                return _set_property(block, m.data_path, m.value_min)
        return False

    if raw == 0:
        return False
    if prev is not None and prev > 0:
        return False  # still held

    ptype = _rna_type(block, m.data_path)
    if ptype == 'BOOLEAN':
        parent, attr = _resolve_prop_parent(block, m.data_path)
        if parent is not None:
            try:
                setattr(parent, attr, not getattr(parent, attr, False))
                return True
            except Exception as e:
                print(f"[ScoreSync] toggle bool failed ({m.data_path}): {e}")
    else:
        state = DEV_MAP.toggle_state.get(key, False)
        DEV_MAP.toggle_state[key] = not state
        return _set_property(block, m.data_path, m.value_max if not state else m.value_min)

    return False


# ── Relative encoder handler ──────────────────────────────────────────────────

def _apply_encoder(m, block, key: tuple) -> bool:
    """
    Relative encoder: consume accumulated offset, nudge the property.
    Handles both simple attrs (rotation_euler.z) and indexed paths (location[0]).
    """
    accum = DEV_MAP.encoder_accum.pop(key, 0.0)
    if accum == 0.0:
        return False

    range_size = m.value_max - m.value_min
    if range_size == 0:
        return False

    step_pct = max(0.001, getattr(m, "encoder_step", 1.0) / 100.0)
    delta    = (accum / 63.0) * step_pct * range_size

    parent, attr = _resolve_prop_parent(block, m.data_path)
    if parent is None:
        return False

    try:
        if attr.startswith("["):
            current = float(parent[int(attr.strip("[]"))])
        elif "[" in attr:
            name, idx_str = attr.split("[", 1)
            current = float(getattr(parent, name)[int(idx_str.rstrip("]"))])
        else:
            current = float(getattr(parent, attr, m.value_min))
        new_val = max(m.value_min, min(m.value_max, current + delta))
        return _set_property(block, m.data_path, new_val)
    except Exception as e:
        print(f"[ScoreSync] encoder failed ({m.data_path}): {e}")
    return False


# ── MIDI ingestion (called from listener / scan threads) ──────────────────────

def ingest_midi_for_mapping(midi_type: str, channel: int, num: int, val: int):
    """
    Store the latest raw value; capture learn event if active.
    Thread-safe: only writes dicts/simple fields, no bpy access.

    val ranges:
      CC / NOTE_ON / NOTE_OFF / POLY_AT / AFTERTOUCH / PROG_CHG : 0-127
      PITCH_BEND : 0-127 (normalised from -8192..8191 by the caller)
    """
    key = (midi_type, channel, num)
    DEV_MAP.last_val[key] = val

    if midi_type == "CC" and val != 64:
        DEV_MAP.encoder_accum[key] = DEV_MAP.encoder_accum.get(key, 0.0) + (val - 64)

    if DEV_MAP.learning:
        DEV_MAP.pending_type  = midi_type
        DEV_MAP.pending_ch    = channel
        DEV_MAP.pending_num   = num
        DEV_MAP.pending_val   = val
        DEV_MAP.pending_ts    = time.time()
        DEV_MAP.capture_dirty = True
        DEV_MAP.learning      = False


# ── ScoreSyncMapping property group ──────────────────────────────────────────

class ScoreSyncMapping(bpy.types.PropertyGroup):
    label    : bpy.props.StringProperty(name="Label", default="Mapping")
    enabled  : bpy.props.BoolProperty(name="Enabled", default=True)

    # ── Target mode (v2.2) ────────────────────────────────────────────────────
    target_mode: bpy.props.EnumProperty(
        name="Target Mode",
        description="What this mapping controls",
        items=[
            ("PROPERTY",  "Property",  "Drive an RNA property continuously or on trigger"),
            ("OPERATOR",  "Operator",  "Run any Blender operator on MIDI trigger"),
            ("FUNCTION",  "Function",  "Call a built-in ScoreSync action"),
            ("KEYFRAME",  "Keyframe",  "Insert a keyframe for a property on trigger"),
            ("TRANSPORT", "Transport", "DAW transport / playback control"),
        ],
        default="PROPERTY",
    )

    # ── MIDI source ───────────────────────────────────────────────────────────
    midi_type: bpy.props.EnumProperty(
        name="MIDI Type",
        items=[
            ("CC",         "CC",          "Control Change — knob / fader / slider"),
            ("NOTE_ON",    "Note On",     "Note press / pad hit"),
            ("NOTE_OFF",   "Note Off",    "Note release"),
            ("PITCH_BEND", "Pitch Bend",  "Pitch wheel (normalised 0-127)"),
            ("AFTERTOUCH", "Aftertouch",  "Channel pressure 0-127"),
            ("POLY_AT",    "Poly Touch",  "Per-note pressure; Num = note"),
            ("PROG_CHG",   "Program Chg", "Program change; Num = program"),
        ],
        default="CC",
    )
    channel  : bpy.props.IntProperty(name="Channel",  default=0, min=0, max=15)
    midi_num : bpy.props.IntProperty(name="CC / Note", default=0, min=0, max=127)

    # ── Trigger settings (non-PROPERTY modes) ─────────────────────────────────
    cc_threshold: bpy.props.IntProperty(
        name="CC Threshold",
        description="CC/PB/AT value that triggers the action (crossing upward fires RISING)",
        default=64, min=0, max=127,
    )
    fire_on: bpy.props.EnumProperty(
        name="Fire On",
        description="Which edge fires the action",
        items=[
            ("RISING",  "Rising Edge",  "Note press, or CC crossing threshold upward"),
            ("FALLING", "Falling Edge", "Note release, or CC dropping below threshold"),
            ("BOTH",    "Both Edges",   "Fire on press and release"),
            ("CHANGE",  "Any Change",   "Fire whenever value changes"),
        ],
        default="RISING",
    )

    # ── PROPERTY mode fields ──────────────────────────────────────────────────
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
    value_min: bpy.props.FloatProperty(name="Min", default=0.0)
    value_max: bpy.props.FloatProperty(name="Max", default=1.0)
    trigger_mode: bpy.props.EnumProperty(
        name="Trigger Mode",
        description="How NOTE_ON events drive this property (PROPERTY mode only)",
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
            ("ABSOLUTE", "Knob (Absolute)",    "0-127 maps linearly to min-max"),
            ("RELATIVE", "Encoder (Relative)", "Each tick nudges; 65-127=CW, 0-63=CCW"),
        ],
        default="ABSOLUTE",
    )
    encoder_step: bpy.props.FloatProperty(
        name="Step %",
        description="How much of the range each encoder tick moves (percent)",
        default=1.0, min=0.1, max=100.0, subtype='PERCENTAGE',
    )

    # ── OPERATOR mode fields ──────────────────────────────────────────────────
    operator_idname: bpy.props.StringProperty(
        name="Operator",
        description="Blender operator idname e.g.  object.delete  or  mesh.primitive_cube_add",
        default="",
    )
    operator_props_json: bpy.props.StringProperty(
        name="Props JSON",
        description='JSON dict of operator keyword args  e.g.  {"size": 2.0}',
        default="{}",
    )

    # ── FUNCTION mode fields ──────────────────────────────────────────────────
    function_id: bpy.props.StringProperty(
        name="Function",
        description="ScoreSync built-in action ID from ACTION_REGISTRY",
        default="",
    )
    function_args_json: bpy.props.StringProperty(
        name="Args JSON",
        description="JSON dict of extra arguments passed to the function",
        default="{}",
    )

    # ── TRANSPORT mode field ──────────────────────────────────────────────────
    transport_action: bpy.props.EnumProperty(
        name="Transport Action",
        items=[
            ("PLAY",             "Play",              ""),
            ("STOP",             "Stop",              ""),
            ("TOGGLE_PLAY",      "Toggle Play/Stop",  ""),
            ("REWIND_START",     "Rewind to Start",   ""),
            ("NEXT_MARKER",      "Next Marker",       ""),
            ("PREV_MARKER",      "Prev Marker",       ""),
            ("LOCATE_CURRENT",   "Locate to Frame",   "Send SPP for current frame"),
            ("SET_FRAME_FROM_CC","CC → Frame",        "CC value maps to timeline frame"),
        ],
        default="TOGGLE_PLAY",
    )

    # ── KEYFRAME mode fields ──────────────────────────────────────────────────
    keyframe_frame_mode: bpy.props.EnumProperty(
        name="Frame",
        items=[
            ("CURRENT",      "Current Frame",   "Insert at the current timeline frame"),
            ("MIDI_TO_FRAME","CC/Note → Frame", "Map MIDI value to a frame number"),
        ],
        default="CURRENT",
    )
    keyframe_value_mode: bpy.props.EnumProperty(
        name="Value",
        items=[
            ("CURRENT", "Keep Current Value", "Don't change the property before inserting"),
            ("MAPPED",  "Set Mapped Value",   "Set property to the CC-mapped value first"),
        ],
        default="CURRENT",
    )

    # ── Developer / custom Python ─────────────────────────────────────────────
    custom_python: bpy.props.StringProperty(
        name="Custom Python",
        description="One-line Python — only executed when Allow Custom Python is enabled in scene settings",
        default="",
    )

    # ── Diagnostics ───────────────────────────────────────────────────────────
    bank: bpy.props.IntProperty(
        name="Bank",
        description="Which mapping bank this slot belongs to (A=0 B=1 C=2 D=3)",
        default=0, min=0, max=3,
    )
    last_error: bpy.props.StringProperty(
        name="Last Error", default="", options={'HIDDEN'},
    )


# ── Bank system ───────────────────────────────────────────────────────────────

BANK_LABELS = ["A", "B", "C", "D"]
BANK_ICONS  = ["EVENT_A", "EVENT_B", "EVENT_C", "EVENT_D"]


class _BankState:
    learning       = False
    learn_target   = -1
    capture_dirty  = False
    pending_type   = ""
    pending_ch     = 0
    pending_num    = 0
    pending_switch = -1

DEV_BANK = _BankState()

_bank_bindings_cache: list = []


class BankSwitchBinding(bpy.types.PropertyGroup):
    """MIDI binding that switches the active mapping bank."""
    enabled  : bpy.props.BoolProperty(default=False)
    midi_type: bpy.props.EnumProperty(
        name="Type",
        items=[("CC", "CC", ""), ("NOTE_ON", "Note", "")],
        default="NOTE_ON",
    )
    channel  : bpy.props.IntProperty(name="Ch",  default=0, min=0, max=15)
    midi_num : bpy.props.IntProperty(name="Num", default=0, min=0, max=127)


def ingest_midi_for_bank_switch(midi_type: str, channel: int, num: int, val: int):
    """Called from MIDI threads. Handles bank-learn capture and queues bank switches."""
    if DEV_BANK.learning:
        if midi_type == "NOTE_ON" and val == 0:
            return
        DEV_BANK.pending_type  = midi_type
        DEV_BANK.pending_ch    = channel
        DEV_BANK.pending_num   = num
        DEV_BANK.capture_dirty = True
        DEV_BANK.learning      = False
        return

    for (btype, bch, bnum, bidx) in _bank_bindings_cache:
        if btype == midi_type and bch == channel and bnum == num:
            if midi_type == "NOTE_ON" and val == 0:
                continue
            DEV_BANK.pending_switch = bidx
            break


# ── Operators ─────────────────────────────────────────────────────────────────

class SCORESYNC_OT_mapping_learn_start(bpy.types.Operator):
    bl_idname      = "scoresync.mapping_learn_start"
    bl_label       = "Learn MIDI"
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
        scene = context.scene
        m     = scene.scoresync_mappings.add()
        idx   = len(scene.scoresync_mappings) - 1

        obj = getattr(context, "active_object", None)
        if obj is not None:
            m.id_type   = "OBJECT"
            m.id_name   = obj.name
            m.data_path = "location.x"
            m.label     = f"{obj.name} Location X"
            m.value_min = -10.0
            m.value_max = 10.0
        else:
            m.label = f"Mapping {idx + 1}"

        scene.scoresync_mapping_index = idx
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
    bl_idname      = "scoresync.mapping_apply_preset"
    bl_label       = "Apply Mapping Preset"
    bl_description = "Add preset mappings"

    preset: bpy.props.EnumProperty(
        name="Preset",
        items=[
            ("CAMERA",            "Camera",            "Camera transform + FOV"),
            ("ACTIVE_OBJECT",     "Active Object",     "Active object transform"),
            ("SCENE",             "Scene",             "Frame / timeline"),
            ("TRANSPORT",         "Transport Knobs",   "Scrub + BPM via knob/encoder"),
            ("TRANSPORT_BUTTONS", "Transport Buttons", "Play/Stop/Markers via pads"),
            ("KEYFRAME_TOOLS",    "Keyframe Tools",    "Insert keyframes via pads"),
            ("OPERATOR_TOOLS",    "Operator Tools",    "Common Blender ops via pads"),
            ("MATERIAL_CONTROLS", "Material Controls", "Roughness, metallic, alpha"),
            ("LIGHT_CONTROLS",    "Light Controls",    "Light energy and spot size"),
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

            m             = scene.scoresync_mappings.add()
            m.label       = t.get("label", "Mapping")
            m.id_type     = t.get("id_type",   "OBJECT")
            m.id_name     = t.get("id_name",   "")
            m.data_path   = t.get("data_path", "location.x")
            m.value_min   = float(t.get("value_min", 0.0))
            m.value_max   = float(t.get("value_max", 1.0))
            m.midi_type   = t.get("midi_type", "CC")
            m.midi_num    = next_cc
            m.target_mode = t.get("target_mode", "PROPERTY")

            if m.target_mode == "TRANSPORT":
                m.transport_action = t.get("transport_action", "TOGGLE_PLAY")
                m.fire_on          = "RISING"
            elif m.target_mode == "OPERATOR":
                m.operator_idname     = t.get("operator_idname",     "")
                m.operator_props_json = t.get("operator_props_json", "{}")
                m.fire_on             = "RISING"
            elif m.target_mode == "KEYFRAME":
                m.fire_on = "RISING"

            used_ccs.add(next_cc)
            next_cc += 1

        self.report({'INFO'}, f"Added {len(template)} mappings from preset '{self.preset}'")
        return {'FINISHED'}


class SCORESYNC_OT_mapping_test_action(bpy.types.Operator):
    """Fire this mapping's action immediately — test without a MIDI controller"""
    bl_idname  = "scoresync.mapping_test_action"
    bl_label   = "Test Action"
    bl_options = {'REGISTER'}

    index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        scene    = context.scene
        mappings = getattr(scene, "scoresync_mappings", None)
        idx      = self.index if self.index >= 0 else getattr(scene, "scoresync_mapping_index", -1)
        if not mappings or not (0 <= idx < len(mappings)):
            self.report({'WARNING'}, "No mapping selected")
            return {'CANCELLED'}

        m           = mappings[idx]
        target_mode = getattr(m, "target_mode", "PROPERTY")
        raw         = 127
        prev        = None

        try:
            if target_mode == "PROPERTY":
                block = _resolve_datablock(m.id_type, m.id_name, context)
                if block:
                    if m.midi_type == "NOTE_ON":
                        _apply_note_on_mapping(m, block, (m.midi_type, m.channel, m.midi_num), raw, prev)
                    else:
                        _set_property(block, m.data_path, _midi_to_value(raw, m.value_min, m.value_max))
            elif target_mode == "OPERATOR":
                _apply_operator_mapping(m, raw, prev, scene)
            elif target_mode == "FUNCTION":
                _apply_function_mapping(m, raw, prev, scene)
            elif target_mode == "KEYFRAME":
                block = _resolve_datablock(m.id_type, m.id_name, context)
                _apply_keyframe_mapping(m, block, raw, prev, scene)
            elif target_mode == "TRANSPORT":
                _apply_transport_mapping_entry(m, raw, prev, scene)

            err = getattr(m, "last_error", "")
            if err:
                self.report({'WARNING'}, f"Action error: {err}")
                return {'CANCELLED'}
            self.report({'INFO'}, f"Test fired: {m.label} ({target_mode})")
        except Exception as e:
            self.report({'ERROR'}, f"Test failed: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


class SCORESYNC_OT_mapping_export(bpy.types.Operator):
    bl_idname      = "scoresync.mapping_export"
    bl_label       = "Export Mappings"
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
                "label":               m.label,
                "enabled":             m.enabled,
                "target_mode":         getattr(m, "target_mode",          "PROPERTY"),
                "id_type":             m.id_type,
                "id_name":             m.id_name,
                "data_path":           m.data_path,
                "midi_type":           m.midi_type,
                "trigger_mode":        m.trigger_mode,
                "encoder_mode":        getattr(m, "encoder_mode",         "ABSOLUTE"),
                "encoder_step":        getattr(m, "encoder_step",         1.0),
                "channel":             m.channel,
                "midi_num":            m.midi_num,
                "value_min":           m.value_min,
                "value_max":           m.value_max,
                "bank":                getattr(m, "bank",                 0),
                "operator_idname":     getattr(m, "operator_idname",      ""),
                "operator_props_json": getattr(m, "operator_props_json",  "{}"),
                "function_id":         getattr(m, "function_id",          ""),
                "function_args_json":  getattr(m, "function_args_json",   "{}"),
                "transport_action":    getattr(m, "transport_action",     "TOGGLE_PLAY"),
                "keyframe_frame_mode": getattr(m, "keyframe_frame_mode",  "CURRENT"),
                "keyframe_value_mode": getattr(m, "keyframe_value_mode",  "CURRENT"),
                "cc_threshold":        getattr(m, "cc_threshold",         64),
                "fire_on":             getattr(m, "fire_on",              "RISING"),
            }
            for m in context.scene.scoresync_mappings
        ]
        dst = bpy.path.abspath(self.filepath)
        if not dst.endswith(".json"):
            dst = os.path.join(dst, self.filename)
        try:
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                json.dump({"version": 3, "mappings": data}, f, indent=2)
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {e}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Exported {len(data)} mappings to {dst}")
        return {'FINISHED'}


class SCORESYNC_OT_mapping_import(bpy.types.Operator):
    bl_idname      = "scoresync.mapping_import"
    bl_label       = "Import Mappings"
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
            m                    = context.scene.scoresync_mappings.add()
            m.label              = row.get("label",              "Imported")
            m.enabled            = row.get("enabled",            True)
            m.target_mode        = row.get("target_mode",        "PROPERTY")
            m.id_type            = row.get("id_type",            "OBJECT")
            m.id_name            = row.get("id_name",            "")
            m.data_path          = row.get("data_path",          "location.x")
            m.midi_type          = row.get("midi_type",          "CC")
            m.trigger_mode       = row.get("trigger_mode",       "TOGGLE")
            m.encoder_mode       = row.get("encoder_mode",       "ABSOLUTE")
            m.encoder_step       = row.get("encoder_step",       1.0)
            m.channel            = row.get("channel",            0)
            m.midi_num           = row.get("midi_num",           0)
            m.value_min          = row.get("value_min",          0.0)
            m.value_max          = row.get("value_max",          1.0)
            m.bank               = row.get("bank",               0)
            m.operator_idname    = row.get("operator_idname",    "")
            m.operator_props_json= row.get("operator_props_json","{}")
            m.function_id        = row.get("function_id",        "")
            m.function_args_json = row.get("function_args_json", "{}")
            m.transport_action   = row.get("transport_action",   "TOGGLE_PLAY")
            m.keyframe_frame_mode= row.get("keyframe_frame_mode","CURRENT")
            m.keyframe_value_mode= row.get("keyframe_value_mode","CURRENT")
            m.cc_threshold       = row.get("cc_threshold",       64)
            m.fire_on            = row.get("fire_on",            "RISING")

        self.report({'INFO'}, f"Imported {len(rows)} mappings from {os.path.basename(src)}")
        return {'FINISHED'}


class SCORESYNC_OT_mapping_clear_binding(bpy.types.Operator):
    """Clear the MIDI binding from this slot (keeps target property)."""
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
        DEV_MAP.toggle_state.pop((m.midi_type, m.channel, m.midi_num), None)
        scene.scoresync_mapping_learn_status = f"Binding cleared for \"{m.label}\""
        self.report({'INFO'}, f"MIDI binding cleared: {m.label}")
        return {'FINISHED'}


class SCORESYNC_OT_mapping_assign_function(bpy.types.Operator):
    """Set the function_id on a mapping to a built-in ScoreSync action."""
    bl_idname = "scoresync.mapping_assign_function"
    bl_label  = "Assign Function"

    mapping_index: bpy.props.IntProperty(default=-1)
    function_id:   bpy.props.StringProperty(default="")

    def execute(self, context):
        scene    = context.scene
        mappings = getattr(scene, "scoresync_mappings", None)
        idx      = self.mapping_index
        if not mappings or not (0 <= idx < len(mappings)):
            return {'CANCELLED'}
        mappings[idx].function_id = self.function_id
        return {'FINISHED'}


# ── Bank switch operators ─────────────────────────────────────────────────────

class SCORESYNC_OT_switch_mapping_bank(bpy.types.Operator):
    bl_idname = "scoresync.switch_mapping_bank"
    bl_label  = "Switch Mapping Bank"
    index: bpy.props.IntProperty(default=0, min=0, max=3)

    def execute(self, context):
        context.scene.scoresync_active_mapping_bank = self.index
        return {'FINISHED'}


class SCORESYNC_OT_bank_learn_start(bpy.types.Operator):
    bl_idname  = "scoresync.bank_learn_start"
    bl_label   = "Learn Bank Switch"
    bank_index : bpy.props.IntProperty(default=0, min=0, max=3)

    def execute(self, context):
        DEV_BANK.learning      = True
        DEV_BANK.learn_target  = self.bank_index
        DEV_BANK.capture_dirty = False
        context.scene.scoresync_bank_learn_status = (
            f"Listening for Bank {BANK_LABELS[self.bank_index]}… press any button"
        )
        try:
            from .ops_connection import start_learn_scan
            start_learn_scan()
        except Exception:
            pass
        self.report({'INFO'}, f"Bank learn: touch a button → Bank {BANK_LABELS[self.bank_index]}")
        return {'FINISHED'}


class SCORESYNC_OT_bank_learn_cancel(bpy.types.Operator):
    bl_idname = "scoresync.bank_learn_cancel"
    bl_label  = "Cancel Bank Learn"

    def execute(self, context):
        DEV_BANK.learning = False
        context.scene.scoresync_bank_learn_status = ""
        return {'FINISHED'}


class SCORESYNC_OT_bank_clear_binding(bpy.types.Operator):
    bl_idname  = "scoresync.bank_clear_binding"
    bl_label   = "Clear Bank Binding"
    bank_index : bpy.props.IntProperty(default=0, min=0, max=3)

    def execute(self, context):
        bindings = getattr(context.scene, "scoresync_bank_bindings", None)
        if bindings and 0 <= self.bank_index < len(bindings):
            bindings[self.bank_index].enabled = False
        return {'FINISHED'}


# ── Registration ──────────────────────────────────────────────────────────────

mapping_classes = (
    BankSwitchBinding,
    ScoreSyncMapping,
    SCORESYNC_OT_mapping_learn_start,
    SCORESYNC_OT_mapping_learn_cancel,
    SCORESYNC_OT_mapping_clear_binding,
    SCORESYNC_OT_mapping_assign,
    SCORESYNC_OT_mapping_select,
    SCORESYNC_OT_pick_data_path,
    SCORESYNC_OT_mapping_add,
    SCORESYNC_OT_mapping_remove,
    SCORESYNC_OT_mapping_apply_preset,
    SCORESYNC_OT_mapping_test_action,
    SCORESYNC_OT_mapping_assign_function,
    SCORESYNC_OT_mapping_export,
    SCORESYNC_OT_mapping_import,
    SCORESYNC_OT_switch_mapping_bank,
    SCORESYNC_OT_bank_learn_start,
    SCORESYNC_OT_bank_learn_cancel,
    SCORESYNC_OT_bank_clear_binding,
)
