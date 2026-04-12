"""
ScoreSync v2 — ops_context.py
Right-click context menu integration.

Property widgets (sliders, toggles, number fields)
---------------------------------------------------
  context.button_pointer + context.button_prop are set → "Learn MIDI for This"
  creates a MIDI mapping slot auto-filled from the RNA property.
  Works anywhere in Blender: shader nodes, render settings, modifiers, etc.
  Right-click the Current Frame field in the timeline → adds a Scrub Frame
  mapping; switch its Encoder Mode to Relative for a rotary encoder.

Operator buttons (Play, Stop, Fire Pad, Select Pad, …)
------------------------------------------------------
  context.button_operator is set instead of button_prop.
  ScoreSync detects which operator was right-clicked and offers the
  appropriate transport-bind or pad-learn action.

  Supported:
    scoresync.tx_play           → Learn MIDI for Play
    scoresync.tx_stop           → Learn MIDI for Stop
    screen.marker_jump(next=T)  → handled via Next/Prev Marker transport bind
    scoresync.sampler_fire_pad  → Learn MIDI Trigger for Pad
    scoresync.sampler_select_pad→ Learn MIDI Note for Pad
"""

import bpy


# ── ID type resolution ────────────────────────────────────────────────────────

_ID_TYPE_MAP = (
    (bpy.types.Object,   "OBJECT"),
    (bpy.types.Scene,    "SCENE"),
    (bpy.types.Material, "MATERIAL"),
    (bpy.types.World,    "WORLD"),
    (bpy.types.Camera,   "OBJECT"),
)

def _resolve_id(ptr):
    """Return (id_data, id_type_str) or None."""
    try:
        id_data = ptr.id_data
    except Exception:
        return None
    id_type = "OBJECT"
    for blender_type, type_str in _ID_TYPE_MAP:
        if isinstance(id_data, blender_type):
            id_type = type_str
            break
    return id_data, id_type


# ── Operator struct name → transport target ───────────────────────────────────
# Maps the Python class name of an operator (type(button_operator).__name__)
# to the corresponding TransportMidiBind target id and menu label.

_TP_BUTTON_MAP = {
    "SCORESYNC_OT_play":             ("PLAY",        "Learn MIDI for Play"),
    "SCORESYNC_OT_stop":             ("STOP",        "Learn MIDI for Stop"),
    "SCORESYNC_OT_jump_next_marker": ("NEXT_MARKER", "Learn MIDI for Next Marker"),
    "SCORESYNC_OT_jump_prev_marker": ("PREV_MARKER", "Learn MIDI for Prev Marker"),
}


# ── Property learn operator ───────────────────────────────────────────────────

class SCORESYNC_OT_context_learn(bpy.types.Operator):
    """Assign a MIDI control to this property — ScoreSync listens for the next touch"""
    bl_idname  = "scoresync.context_learn"
    bl_label   = "ScoreSync: Learn MIDI for This"
    bl_options = {'REGISTER', 'UNDO'}

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

        try:
            struct_path    = ptr.path_from_id()
            pid            = prop.identifier
            self._data_path = f"{struct_path}.{pid}" if struct_path else pid
        except Exception:
            self._data_path = prop.identifier

        self._label = prop.name or prop.identifier

        try:
            self._vmin = float(getattr(prop, "soft_min", 0.0))
            self._vmax = float(getattr(prop, "soft_max", 1.0))
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

        DEV_MAP.learning      = True
        DEV_MAP.capture_dirty = False
        DEV_MAP.target_idx    = idx
        scene.scoresync_mapping_learn_status = (
            f"Listening… touch any MIDI control to bind → {self._label}"
        )

        try:
            from .ops_connection import start_learn_scan
            start_learn_scan()
        except Exception:
            pass

        self.report({'INFO'}, f"ScoreSync: touch a control to bind → '{self._label}'")
        return {'FINISHED'}


# ── Pad learn via right-click ─────────────────────────────────────────────────

class SCORESYNC_OT_context_learn_pad(bpy.types.Operator):
    """Learn the MIDI note that triggers or selects this sampler pad"""
    bl_idname   = "scoresync.context_learn_pad"
    bl_label    = "ScoreSync: Learn MIDI for Pad"
    bl_options  = {'REGISTER'}

    bank_index: bpy.props.IntProperty(default=0, options={'HIDDEN'})
    pad_index : bpy.props.IntProperty(default=0, options={'HIDDEN'})

    def execute(self, context):
        try:
            from .ops_sampler import DEV_PAD_LEARN
        except Exception as e:
            self.report({'ERROR'}, f"ScoreSync sampler not ready: {e}")
            return {'CANCELLED'}

        DEV_PAD_LEARN.learning      = True
        DEV_PAD_LEARN.bank_idx      = self.bank_index
        DEV_PAD_LEARN.pad_idx       = self.pad_index
        DEV_PAD_LEARN.capture_dirty = False
        context.scene.scoresync_sampler_learn_status = (
            f"Listening for Pad {self.pad_index+1} (Bank {self.bank_index+1})… "
            f"press any key or pad on your controller"
        )

        try:
            from .ops_connection import start_learn_scan
            start_learn_scan()
        except Exception:
            pass

        self.report({'INFO'},
                    f"Pad learn: touch any pad/key to bind → pad {self.pad_index+1}")
        return {'FINISHED'}


# ── Transport learn via right-click ──────────────────────────────────────────

class SCORESYNC_OT_context_learn_transport(bpy.types.Operator):
    """Learn a MIDI button or knob for this transport action"""
    bl_idname   = "scoresync.context_learn_transport"
    bl_label    = "ScoreSync: Learn MIDI for Transport"
    bl_options  = {'REGISTER'}

    target: bpy.props.EnumProperty(
        name="Target",
        items=[
            ("PLAY",        "Play",        ""),
            ("STOP",        "Stop",        ""),
            ("NEXT_MARKER", "Next Marker", ""),
            ("PREV_MARKER", "Prev Marker", ""),
        ],
    )

    def execute(self, context):
        try:
            from .ops_transport import DEV_TP
        except Exception as e:
            self.report({'ERROR'}, f"ScoreSync transport not ready: {e}")
            return {'CANCELLED'}

        DEV_TP.learning      = True
        DEV_TP.target        = self.target
        DEV_TP.capture_dirty = False
        context.scene.scoresync_transport_learn_status = (
            f"Listening for {self.target}… touch any button or knob"
        )

        try:
            from .ops_connection import start_learn_scan
            start_learn_scan()
        except Exception:
            pass

        self.report({'INFO'}, f"Transport learn: {self.target} — touch a control")
        return {'FINISHED'}


# ── Menu injection ────────────────────────────────────────────────────────────

def _draw_context_menu(self, context):
    """
    Appended to WM_MT_button_context.

    Three cases:
      1. button_prop set     → property widget (slider/toggle): show property learn
      2. button_operator set → operator button: show pad or transport learn
      3. Neither             → nothing shown
    """
    ptr  = getattr(context, "button_pointer",  None)
    prop = getattr(context, "button_prop",     None)
    op   = getattr(context, "button_operator", None)
    layout = self.layout

    # ── Case 1: property widget ───────────────────────────────────────────────
    if ptr is not None and prop is not None:
        if prop.type not in ('FLOAT', 'INT', 'BOOLEAN', 'ENUM'):
            return
        layout.separator()
        layout.operator(
            "scoresync.context_learn",
            icon='REC',
            text="ScoreSync: Learn MIDI for This",
        )
        return

    # ── Case 2: operator button ───────────────────────────────────────────────
    if op is None:
        return

    op_type = type(op).__name__

    # Transport buttons (Play, Stop, marker jump)
    if op_type in _TP_BUTTON_MAP:
        target, label = _TP_BUTTON_MAP[op_type]
        layout.separator()
        item = layout.operator(
            "scoresync.context_learn_transport",
            icon='REC',
            text=f"ScoreSync: {label}",
        )
        item.target = target
        return

    # Sampler fire pad button
    if op_type == "SCORESYNC_OT_sampler_fire_pad":
        layout.separator()
        item = layout.operator(
            "scoresync.context_learn_pad",
            icon='REC',
            text="ScoreSync: Learn MIDI Trigger for this Pad",
        )
        item.bank_index = getattr(op, "bank_index", 0)
        item.pad_index  = getattr(op, "pad_index",  0)
        return

    # Sampler select pad button
    if op_type == "SCORESYNC_OT_sampler_select_pad":
        layout.separator()
        item = layout.operator(
            "scoresync.context_learn_pad",
            icon='REC',
            text="ScoreSync: Learn MIDI Note for this Pad",
        )
        item.bank_index = getattr(context.scene, "scoresync_active_bank", 0)
        item.pad_index  = getattr(op, "index", 0)
        return

    # Any other ScoreSync operator button — offer the full transport submenu
    if op_type.startswith("SCORESYNC_OT_"):
        layout.separator()
        layout.label(text="ScoreSync: Bind Transport →", icon='REC')
        for target_id, label in (
            ("PLAY",        "Play"),
            ("STOP",        "Stop"),
            ("NEXT_MARKER", "Next Marker"),
            ("PREV_MARKER", "Prev Marker"),
        ):
            item = layout.operator(
                "scoresync.context_learn_transport",
                icon='BLANK1',
                text=label,
            )
            item.target = target_id


# ── Timeline / Dopesheet / Sequencer scrub-learn ──────────────────────────────

class SCORESYNC_OT_context_learn_scrub(bpy.types.Operator):
    """
    Add a frame_current mapping pre-configured for rotary encoder scrubbing.
    Right-click the timeline ruler, dopesheet, or sequencer to use this.
    Set Encoder Mode to Relative for a detented rotary knob.
    """
    bl_idname  = "scoresync.context_learn_scrub"
    bl_label   = "ScoreSync: Learn MIDI Scrub (Encoder/Knob)"
    bl_options = {'REGISTER', 'UNDO'}

    frame_end: bpy.props.IntProperty(
        name="Frame End",
        description="Upper range for the scrub mapping",
        default=500,
        min=1,
    )

    def invoke(self, context, event):
        # Use the scene's actual frame end as the default upper bound
        self.frame_end = max(1, context.scene.frame_end)
        return self.execute(context)

    def execute(self, context):
        from .ops_mapping import DEV_MAP

        scene    = context.scene
        mappings = getattr(scene, "scoresync_mappings", None)
        if mappings is None:
            self.report({'ERROR'}, "ScoreSync not ready — connect first")
            return {'CANCELLED'}

        m             = mappings.add()
        m.label       = "Scrub Frame"
        m.id_type     = "SCENE"
        m.id_name     = "__SCENE__"
        m.data_path   = "frame_current"
        m.value_min   = float(scene.frame_start)
        m.value_max   = float(self.frame_end)
        m.midi_type   = "CC"
        m.encoder_mode = "RELATIVE"
        m.encoder_step = 1.0
        m.enabled     = True

        idx = len(mappings) - 1
        scene.scoresync_mapping_index = idx

        DEV_MAP.learning      = True
        DEV_MAP.capture_dirty = False
        DEV_MAP.target_idx    = idx
        scene.scoresync_mapping_learn_status = (
            "Listening… turn any rotary encoder to bind → Scrub Frame  "
            "(switch Encoder Mode to Relative for detented knobs)"
        )

        try:
            from .ops_connection import start_learn_scan
            start_learn_scan()
        except Exception:
            pass

        self.report({'INFO'},
                    "ScoreSync: turn a knob/encoder to bind it to Scrub Frame")
        return {'FINISHED'}


def _draw_timeline_menu(self, context):
    """Injected into the Timeline, Dopesheet, and Sequencer context menus."""
    layout = self.layout
    layout.separator()
    layout.label(text="ScoreSync", icon='REC')
    layout.operator(
        "scoresync.context_learn_scrub",
        icon='REC',
        text="Learn MIDI Scrub (Knob / Encoder)",
    )
    # Quick transport binds for convenience
    layout.separator()
    for target_id, label in (
        ("PLAY",        "Play"),
        ("STOP",        "Stop"),
        ("NEXT_MARKER", "Next Marker"),
        ("PREV_MARKER", "Prev Marker"),
    ):
        item = layout.operator(
            "scoresync.context_learn_transport",
            icon='BLANK1',
            text=f"Learn MIDI → {label}",
        )
        item.target = target_id


# ── Registration ──────────────────────────────────────────────────────────────

context_classes = (
    SCORESYNC_OT_context_learn,
    SCORESYNC_OT_context_learn_pad,
    SCORESYNC_OT_context_learn_transport,
    SCORESYNC_OT_context_learn_scrub,
)

# Timeline editor menus that receive the scrub/transport injection.
# Each is tried at register time; missing types are silently skipped so the
# addon still loads on Blender versions that lack a particular menu.
_TIMELINE_MENU_TYPES = (
    "TIME_MT_editor_menus",   # Timeline header menus (4.x)
    "TIME_MT_view",           # Timeline View menu
    "DOPESHEET_MT_editor_menus",
    "NLA_MT_editor_menus",
    "SEQUENCER_MT_editor_menus",
)


def register_context_menu():
    bpy.types.WM_MT_button_context.append(_draw_context_menu)
    for mt_name in _TIMELINE_MENU_TYPES:
        mt = getattr(bpy.types, mt_name, None)
        if mt is not None:
            mt.append(_draw_timeline_menu)


def unregister_context_menu():
    bpy.types.WM_MT_button_context.remove(_draw_context_menu)
    for mt_name in _TIMELINE_MENU_TYPES:
        mt = getattr(bpy.types, mt_name, None)
        if mt is not None:
            try:
                mt.remove(_draw_timeline_menu)
            except Exception:
                pass
