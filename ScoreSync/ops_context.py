"""
ScoreSync v2 — ops_context.py
Right-click context menu integration.

Appends "ScoreSync: Learn MIDI for This" to Blender's universal property
right-click menu (WM_MT_button_context).  Works on any numeric slider,
toggle, colour channel, or enum in ANY editor — modifiers, shader nodes,
render settings, physics, compositor, etc.

Flow
----
1. User right-clicks any property → menu appears with ScoreSync entry
2. ScoreSync reads context.button_pointer + context.button_prop to get the
   exact datablock and RNA path automatically
3. A new mapping slot is created for that property
4. Learn mode starts — user touches any MIDI control to bind it
5. Mapping is active immediately; no ScoreSync Editor needed
"""

import bpy


# ── ID type resolution ────────────────────────────────────────────────────────

_ID_TYPE_MAP = (
    (bpy.types.Object,   "OBJECT"),
    (bpy.types.Scene,    "SCENE"),
    (bpy.types.Material, "MATERIAL"),
    (bpy.types.World,    "WORLD"),
    (bpy.types.Camera,   "OBJECT"),   # cameras are Objects in the mapping layer
)

def _resolve_id(ptr):
    """Return (id_type_str, id_name, data_path_from_id) or None."""
    try:
        id_data = ptr.id_data
    except Exception:
        return None

    id_type = "OBJECT"  # fallback
    for blender_type, type_str in _ID_TYPE_MAP:
        if isinstance(id_data, blender_type):
            id_type = type_str
            break

    return id_data, id_type


# ── Operator ──────────────────────────────────────────────────────────────────

class SCORESYNC_OT_context_learn(bpy.types.Operator):
    """Assign a MIDI control to this property — ScoreSync will listen for the next touch"""
    bl_idname  = "scoresync.context_learn"
    bl_label   = "ScoreSync: Learn MIDI for This"
    bl_options = {'REGISTER', 'UNDO'}

    # Stored at invoke time while context.button_* is still valid
    _id_type  : bpy.props.StringProperty(options={'HIDDEN'})
    _id_name  : bpy.props.StringProperty(options={'HIDDEN'})
    _data_path: bpy.props.StringProperty(options={'HIDDEN'})
    _label    : bpy.props.StringProperty(options={'HIDDEN'})
    _vmin     : bpy.props.FloatProperty(options={'HIDDEN'})
    _vmax     : bpy.props.FloatProperty(options={'HIDDEN'})

    def invoke(self, context, event):
        ptr  = getattr(context, "button_pointer", None)
        prop = getattr(context, "button_prop",    None)

        if ptr is None or prop is None:
            self.report({'WARNING'}, "ScoreSync: no property detected — right-click a slider or toggle")
            return {'CANCELLED'}

        result = _resolve_id(ptr)
        if result is None:
            self.report({'WARNING'}, "ScoreSync: property is not part of a datablock")
            return {'CANCELLED'}

        id_data, id_type = result
        self._id_type = id_type
        self._id_name = id_data.name

        # Full RNA path relative to the ID datablock
        try:
            struct_path = ptr.path_from_id()
            pid         = prop.identifier
            self._data_path = f"{struct_path}.{pid}" if struct_path else pid
        except Exception:
            self._data_path = prop.identifier

        # Human label
        self._label = prop.name or prop.identifier

        # Auto-fill value range from RNA soft limits
        try:
            self._vmin = float(getattr(prop, "soft_min", 0.0))
            self._vmax = float(getattr(prop, "soft_max", 1.0))
            # Clamp absurd ranges to something sensible
            if self._vmin <= -1e9:
                self._vmin = 0.0
            if self._vmax >= 1e9:
                self._vmax = 1.0
        except Exception:
            self._vmin, self._vmax = 0.0, 1.0

        return self.execute(context)

    def execute(self, context):
        from .ops_mapping import DEV_MAP

        scene    = context.scene
        mappings = getattr(scene, "scoresync_mappings", None)
        if mappings is None:
            self.report({'ERROR'}, "ScoreSync not ready — connect first")
            return {'CANCELLED'}

        # Create a new mapping slot pre-filled with the target property
        m           = mappings.add()
        m.label     = self._label
        m.id_type   = self._id_type
        m.id_name   = self._id_name
        m.data_path = self._data_path
        m.value_min = self._vmin
        m.value_max = self._vmax
        m.enabled   = True

        idx = len(mappings) - 1
        scene.scoresync_mapping_index = idx

        # Arm learn mode
        DEV_MAP.learning      = True
        DEV_MAP.capture_dirty = False
        DEV_MAP.target_idx    = idx
        scene.scoresync_mapping_learn_status = (
            f"Listening… touch any MIDI control to bind → {self._label}"
        )

        # Open universal MIDI scanner so ANY connected device is heard
        try:
            from .ops_connection import start_learn_scan
            start_learn_scan()
        except Exception:
            pass

        self.report(
            {'INFO'},
            f"ScoreSync: touch a pad/knob to bind MIDI → '{self._label}'"
        )
        return {'FINISHED'}


# ── Menu injection ────────────────────────────────────────────────────────────

def _draw_context_menu(self, context):
    """Appended to WM_MT_button_context — shows on every right-clicked property."""
    ptr  = getattr(context, "button_pointer", None)
    prop = getattr(context, "button_prop",    None)

    # Only show for driveable types (float, int, bool, enum)
    if ptr is None or prop is None:
        return
    if prop.type not in ('FLOAT', 'INT', 'BOOLEAN', 'ENUM'):
        return

    self.layout.separator()
    self.layout.operator(
        "scoresync.context_learn",
        icon='REC',
        text="ScoreSync: Learn MIDI for This",
    )


# ── Registration helpers (called from __init__.py) ────────────────────────────

context_classes = (
    SCORESYNC_OT_context_learn,
)

def register_context_menu():
    bpy.types.WM_MT_button_context.append(_draw_context_menu)

def unregister_context_menu():
    bpy.types.WM_MT_button_context.remove(_draw_context_menu)
