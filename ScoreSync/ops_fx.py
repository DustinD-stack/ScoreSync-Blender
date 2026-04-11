"""
ScoreSync v2 — ops_fx.py
Visual FX Rack: MIDI-driven shader and VSE strip effects.

Each FX slot binds a MIDI control to a visual parameter:
  VSE strips  — opacity, brightness multiplier, saturation,
                bright/contrast (modifier), RGB tint (modifier)
  Materials   — opacity (Principled Alpha), emission strength,
                hue/saturation/value (HueSaturation node),
                brightness/contrast (BrightContrast node)

Trigger modes:
  CC          — knob / slider, raw 0-127 mapped to value range
  MOMENTARY   — note held = value_max, released = value_min
  TOGGLE      — each note-on flips between value_min / value_max
  FLASH       — note-on → value_max, decays to value_min over decay_ms

Learn:
  SCORESYNC_OT_fx_learn_start sets DEV_FX.learning_slot = slot_index.
  ingest_midi_for_mapping (called from listener thread) detects this and
  stores a pending_learn dict. apply_fx_tick() applies it on the main thread.

Setup helper:
  SCORESYNC_OT_fx_setup_material inserts labeled ScoreSync HSV + BrightContrast
  nodes between the Image Texture and Principled BSDF so MAT_* FX types work
  immediately.
"""

import bpy
import time


# ── Enum constants ────────────────────────────────────────────────────────────

FX_TYPES = [
    # VSE direct strip properties
    ("OPACITY",    "Opacity",      "Strip blend_alpha — fade in/out (0=transparent, 1=opaque)"),
    ("COLOR_MULT", "Bright Mult",  "Strip color_multiply (0=black, 1=normal, 2=bright)"),
    ("SATURATION", "Saturation",   "Strip color_saturation (0=grey, 1=normal, 2=vivid)"),
    # VSE modifier-based
    ("BRIGHTNESS", "Brightness",   "BRIGHT_CONTRAST modifier — bright offset"),
    ("CONTRAST",   "Contrast",     "BRIGHT_CONTRAST modifier — contrast"),
    ("TINT_R",     "Tint R",       "COLOR_BALANCE gain — red channel"),
    ("TINT_G",     "Tint G",       "COLOR_BALANCE gain — green channel"),
    ("TINT_B",     "Tint B",       "COLOR_BALANCE gain — blue channel"),
    # Material node-based
    ("MAT_OPACITY",  "Mat Opacity",    "Principled BSDF Alpha (use Setup Material first)"),
    ("MAT_EMISSION", "Mat Emission",   "Principled BSDF Emission Strength"),
    ("MAT_HUE",      "Mat Hue",        "ScoreSync HSV node — hue (0=unchanged at 0.5)"),
    ("MAT_SAT",      "Mat Saturation", "ScoreSync HSV node — saturation"),
    ("MAT_VALUE",    "Mat Value",      "ScoreSync HSV node — value / brightness"),
    ("MAT_BRIGHT",   "Mat Brightness", "ScoreSync BC node — bright offset"),
    ("MAT_CONTRAST", "Mat Contrast",   "ScoreSync BC node — contrast"),
]

FX_TARGET_MODES = [
    ("VSE_CHANNEL", "VSE Channel",     "Drive the strip currently on this VSE channel"),
    ("OBJECT_MAT",  "Object Material", "Drive a named object's active material"),
    ("ACTIVE_MAT",  "Active Mat",      "Drive the active object's material"),
]

FX_TRIGGER_MODES = [
    ("CC",        "CC / Continuous", "Knob or slider — CC value maps linearly to the output range"),
    ("MOMENTARY", "Momentary",       "Note On = value_max while held, Note Off = value_min"),
    ("TOGGLE",    "Toggle",          "Each Note On flips between value_min and value_max"),
    ("FLASH",     "Flash",           "Note On snaps to value_max then decays to value_min over decay_ms"),
]

_MAT_FX_TYPES = {
    "MAT_OPACITY", "MAT_EMISSION", "MAT_HUE", "MAT_SAT",
    "MAT_VALUE", "MAT_BRIGHT", "MAT_CONTRAST",
}


# ── Runtime FX state ──────────────────────────────────────────────────────────

class _FXState:
    learning_slot  = -1      # slot index being trained (-1 = not learning)
    pending_learn  = None    # {"slot": int, "type": str, "ch": int, "num": int}
    flash_state    = {}      # {slot_idx: {"start_ts": float, "duration_s": float}}
    toggle_state   = {}      # {slot_idx: bool}

DEV_FX = _FXState()


# ── VSE apply helpers ─────────────────────────────────────────────────────────

def _find_vse_strip(scene, channel: int):
    """First strip on `channel` that spans scene.frame_current."""
    if not scene.sequence_editor:
        return None
    frame = scene.frame_current
    for s in scene.sequence_editor.sequences_all:
        if s.channel == channel and s.frame_final_start <= frame < s.frame_final_end:
            return s
    return None


def _get_or_add_vse_modifier(strip, mod_type: str):
    for m in strip.modifiers:
        if m.type == mod_type:
            return m
    return strip.modifiers.new(name=f"ScoreSync {mod_type}", type=mod_type)


def _apply_vse_fx(scene, slot, value: float):
    try:
        ch = int(slot.target_name or "1")
    except ValueError:
        return
    strip = _find_vse_strip(scene, ch)
    if strip is None:
        return
    ft = slot.fx_type
    try:
        if ft == "OPACITY":
            strip.blend_alpha = max(0.0, min(1.0, value))
            if strip.blend_type not in ("ALPHA_OVER", "OVER_DROP"):
                strip.blend_type = "ALPHA_OVER"
        elif ft == "COLOR_MULT":
            strip.color_multiply = max(0.0, min(2.0, value))
        elif ft == "SATURATION":
            strip.color_saturation = max(0.0, min(2.0, value))
        elif ft in ("BRIGHTNESS", "CONTRAST"):
            m = _get_or_add_vse_modifier(strip, "BRIGHT_CONTRAST")
            if ft == "BRIGHTNESS":
                m.bright   = value
            else:
                m.contrast = value
        elif ft in ("TINT_R", "TINT_G", "TINT_B"):
            m = _get_or_add_vse_modifier(strip, "COLOR_BALANCE")
            gain = list(m.color_balance.gain)
            idx = {"TINT_R": 0, "TINT_G": 1, "TINT_B": 2}[ft]
            gain[idx] = max(0.0, value)
            m.color_balance.gain = tuple(gain)
    except Exception as e:
        print(f"[ScoreSync FX] VSE apply failed ({ft}): {e}")


# ── Material apply helpers ────────────────────────────────────────────────────

def _resolve_mat(slot):
    if slot.target_mode == "ACTIVE_MAT":
        obj = getattr(bpy.context, "active_object", None)
    else:
        obj = bpy.data.objects.get(slot.target_name)
    if obj is None or not obj.material_slots:
        return None
    return obj.active_material


def _apply_mat_fx(scene, slot, value: float):
    mat = _resolve_mat(slot)
    if mat is None or not mat.use_nodes:
        return
    tree = mat.node_tree
    ft   = slot.fx_type
    try:
        if ft == "MAT_OPACITY":
            p = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if p:
                p.inputs["Alpha"].default_value = max(0.0, min(1.0, value))
        elif ft == "MAT_EMISSION":
            p = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if p and "Emission Strength" in p.inputs:
                p.inputs["Emission Strength"].default_value = max(0.0, value)
        elif ft in ("MAT_HUE", "MAT_SAT", "MAT_VALUE"):
            hsv = next(
                (n for n in tree.nodes if n.type == "HUE_SAT" and "ScoreSync" in n.name),
                next((n for n in tree.nodes if n.type == "HUE_SAT"), None),
            )
            if hsv:
                if ft == "MAT_HUE":
                    hsv.inputs["Hue"].default_value        = max(0.0, min(1.0, value))
                elif ft == "MAT_SAT":
                    hsv.inputs["Saturation"].default_value = max(0.0, min(2.0, value))
                else:
                    hsv.inputs["Value"].default_value      = max(0.0, min(2.0, value))
        elif ft in ("MAT_BRIGHT", "MAT_CONTRAST"):
            bc = next(
                (n for n in tree.nodes if n.type == "BRIGHTCONTRAST" and "ScoreSync" in n.name),
                next((n for n in tree.nodes if n.type == "BRIGHTCONTRAST"), None),
            )
            if bc:
                if ft == "MAT_BRIGHT":
                    bc.inputs["Bright"].default_value   = value
                else:
                    bc.inputs["Contrast"].default_value = value
    except Exception as e:
        print(f"[ScoreSync FX] Mat apply failed ({ft}): {e}")


# ── Main apply tick (called from scoresync_timer) ─────────────────────────────

def apply_fx_tick(scene):
    """Apply MIDI-driven values to all enabled FX slots. Call from main timer."""
    # Apply any pending learn result (was captured in listener thread)
    if DEV_FX.pending_learn is not None:
        p = DEV_FX.pending_learn
        DEV_FX.pending_learn = None
        slots = getattr(scene, "scoresync_fx_slots", None)
        if slots and 0 <= p["slot"] < len(slots):
            s = slots[p["slot"]]
            s.midi_type    = p["type"]
            s.midi_channel = p["ch"]
            s.midi_num     = p["num"]
            scene.scoresync_fx_learn_status = (
                f"Slot {p['slot']+1}: {p['type']} ch{p['ch']} #{p['num']}"
            )

    try:
        from .ops_mapping import DEV_MAP
    except Exception:
        return

    slots = getattr(scene, "scoresync_fx_slots", None)
    if not slots:
        return

    now = time.time()

    for i, slot in enumerate(slots):
        if not slot.enabled:
            continue

        tmode = slot.trigger_mode
        key   = (slot.midi_type, slot.midi_channel, slot.midi_num)

        if tmode == "CC":
            raw = DEV_MAP.last_val.get(key)
            if raw is None:
                continue
            t     = max(0, min(127, raw)) / 127.0
            value = slot.value_min + t * (slot.value_max - slot.value_min)

        elif tmode == "FLASH":
            fs = DEV_FX.flash_state.get(i)
            if fs is None:
                value = slot.value_min
            else:
                elapsed = now - fs["start_ts"]
                dur     = fs["duration_s"]
                if elapsed >= dur:
                    value = slot.value_min
                    del DEV_FX.flash_state[i]
                else:
                    # linear decay max → min
                    t     = 1.0 - (elapsed / dur)
                    value = slot.value_min + t * (slot.value_max - slot.value_min)

        elif tmode in ("MOMENTARY", "TOGGLE"):
            on    = DEV_FX.toggle_state.get(i, False)
            value = slot.value_max if on else slot.value_min

        else:
            continue

        slot.current_value = value

        if slot.fx_type in _MAT_FX_TYPES:
            _apply_mat_fx(scene, slot, value)
        else:
            _apply_vse_fx(scene, slot, value)


# ── Note event handlers (called from main-thread _apply_incoming) ─────────────

def handle_note_on_fx(channel: int, note: int, velocity: int, scene=None):
    sc = scene or (bpy.context.scene if bpy.context else None)
    if sc is None:
        return
    slots = getattr(sc, "scoresync_fx_slots", None)
    if not slots:
        return
    for i, slot in enumerate(slots):
        if not slot.enabled or slot.midi_type != "NOTE_ON":
            continue
        if slot.midi_channel != channel or slot.midi_num != note:
            continue
        tmode = slot.trigger_mode
        if tmode == "MOMENTARY":
            DEV_FX.toggle_state[i] = True
        elif tmode == "TOGGLE":
            DEV_FX.toggle_state[i] = not DEV_FX.toggle_state.get(i, False)
        elif tmode == "FLASH":
            DEV_FX.flash_state[i] = {
                "start_ts":   time.time(),
                "duration_s": max(0.01, slot.decay_ms / 1000.0),
            }
            DEV_FX.toggle_state[i] = True


def handle_note_off_fx(channel: int, note: int, scene=None):
    sc = scene or (bpy.context.scene if bpy.context else None)
    if sc is None:
        return
    slots = getattr(sc, "scoresync_fx_slots", None)
    if not slots:
        return
    for i, slot in enumerate(slots):
        if not slot.enabled or slot.midi_type != "NOTE_ON":
            continue
        if slot.midi_channel != channel or slot.midi_num != note:
            continue
        if slot.trigger_mode == "MOMENTARY":
            DEV_FX.toggle_state[i] = False


# ── Learn capture (called from ingest_midi_for_mapping — listener thread) ─────

def capture_fx_learn(midi_type: str, channel: int, num: int):
    """
    Thread-safe. If a slot is waiting for learn, store the result in pending_learn.
    Called inside ingest_midi_for_mapping on every CC / Note On.
    """
    if DEV_FX.learning_slot < 0:
        return
    DEV_FX.pending_learn = {
        "slot": DEV_FX.learning_slot,
        "type": midi_type,
        "ch":   channel,
        "num":  num,
    }
    DEV_FX.learning_slot = -1
    try:
        from .ops_connection import stop_learn_scan
        stop_learn_scan()
    except Exception:
        pass


# ── Material setup operator ───────────────────────────────────────────────────

def _setup_material_fx_chain(mat):
    """
    Insert ScoreSync HSV and BrightContrast nodes between the Image Texture
    and the Principled BSDF in the given material.
    Returns (hsv_node, bc_node, principled_node).
    """
    if not mat.use_nodes:
        mat.use_nodes = True
    tree = mat.node_tree

    # Locate key nodes
    output = next((n for n in tree.nodes if n.type == "OUTPUT_MATERIAL"), None)
    if output is None:
        output          = tree.nodes.new("ShaderNodeOutputMaterial")
        output.location = (700, 0)

    princ = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if princ is None:
        princ          = tree.nodes.new("ShaderNodeBsdfPrincipled")
        princ.location = (400, 0)
        tree.links.new(princ.outputs["BSDF"], output.inputs["Surface"])

    tex = next((n for n in tree.nodes if n.type == "TEX_IMAGE"), None)

    # Check for existing ScoreSync nodes
    hsv = next(
        (n for n in tree.nodes if n.type == "HUE_SAT" and "ScoreSync" in n.name), None
    )
    bc  = next(
        (n for n in tree.nodes if n.type == "BRIGHTCONTRAST" and "ScoreSync" in n.name), None
    )

    if hsv is None:
        hsv           = tree.nodes.new("ShaderNodeHueSaturation")
        hsv.name      = "ScoreSync HSV"
        hsv.label     = "ScoreSync: Hue / Sat / Value"
        hsv.location  = (-50, 300)
        hsv.inputs["Hue"].default_value        = 0.5
        hsv.inputs["Saturation"].default_value = 1.0
        hsv.inputs["Value"].default_value      = 1.0

    if bc is None:
        bc          = tree.nodes.new("ShaderNodeBrightContrast")
        bc.name     = "ScoreSync BC"
        bc.label    = "ScoreSync: Bright / Contrast"
        bc.location = (200, 300)
        bc.inputs["Bright"].default_value   = 0.0
        bc.inputs["Contrast"].default_value = 0.0

    # Rewire: tex → hsv → bc → principled Base Color
    if tex:
        for lnk in list(tree.links):
            if lnk.from_node == tex and lnk.to_node == princ:
                tree.links.remove(lnk)
        tree.links.new(tex.outputs["Color"], hsv.inputs["Color"])

    tree.links.new(hsv.outputs["Color"], bc.inputs["Color"])
    tree.links.new(bc.outputs["Color"],  princ.inputs["Base Color"])

    return hsv, bc, princ


class SCORESYNC_OT_fx_setup_material(bpy.types.Operator):
    bl_idname    = "scoresync.fx_setup_material"
    bl_label     = "Setup Material FX Chain"
    bl_description = (
        "Insert ScoreSync Hue/Sat/Value and Bright/Contrast nodes into the active "
        "object's material so Mat FX types work immediately"
    )

    def execute(self, context):
        obj = context.active_object
        if obj is None or not obj.material_slots:
            self.report({'WARNING'}, "No active object with a material.")
            return {'CANCELLED'}
        mat = obj.active_material
        if mat is None:
            self.report({'WARNING'}, "Active material slot is empty.")
            return {'CANCELLED'}
        _setup_material_fx_chain(mat)
        self.report({'INFO'}, f"FX chain set up in '{mat.name}'")
        return {'FINISHED'}


# ── Property group ────────────────────────────────────────────────────────────

class ScoreSyncFXSlot(bpy.types.PropertyGroup):
    label         : bpy.props.StringProperty(name="Label", default="FX Slot")
    enabled       : bpy.props.BoolProperty(name="Enabled", default=True)
    fx_type       : bpy.props.EnumProperty(name="FX Type",    items=FX_TYPES,         default="OPACITY")
    target_mode   : bpy.props.EnumProperty(name="Target",     items=FX_TARGET_MODES,  default="VSE_CHANNEL")
    target_name   : bpy.props.StringProperty(name="Target",   default="1",
                        description="VSE channel number, or object name")
    trigger_mode  : bpy.props.EnumProperty(name="Trigger",    items=FX_TRIGGER_MODES, default="CC")
    decay_ms      : bpy.props.IntProperty(name="Decay (ms)", default=500, min=10, max=5000,
                        description="Flash decay time in milliseconds")
    midi_type     : bpy.props.EnumProperty(name="MIDI Type",
                        items=[("CC", "CC", "Control Change"), ("NOTE_ON", "Note", "Note On")],
                        default="CC")
    midi_channel  : bpy.props.IntProperty(name="Ch",  default=0, min=0, max=15)
    midi_num      : bpy.props.IntProperty(name="Num", default=0, min=0, max=127,
                        description="CC number or note number")
    value_min     : bpy.props.FloatProperty(name="Min", default=0.0, precision=3)
    value_max     : bpy.props.FloatProperty(name="Max", default=1.0, precision=3)
    current_value : bpy.props.FloatProperty(name="Live", default=0.0, min=0.0, max=1.0,
                        description="Current output value (read-only display)")


# ── Operators ─────────────────────────────────────────────────────────────────

class SCORESYNC_OT_fx_add_slot(bpy.types.Operator):
    bl_idname = "scoresync.fx_add_slot"
    bl_label  = "Add FX Slot"

    def execute(self, context):
        scene = context.scene
        slot       = scene.scoresync_fx_slots.add()
        slot.label = f"FX {len(scene.scoresync_fx_slots)}"
        scene.scoresync_fx_index = len(scene.scoresync_fx_slots) - 1
        return {'FINISHED'}


class SCORESYNC_OT_fx_remove_slot(bpy.types.Operator):
    bl_idname = "scoresync.fx_remove_slot"
    bl_label  = "Remove FX Slot"

    index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        scene = context.scene
        idx = self.index if self.index >= 0 else scene.scoresync_fx_index
        if 0 <= idx < len(scene.scoresync_fx_slots):
            scene.scoresync_fx_slots.remove(idx)
            scene.scoresync_fx_index = max(0, idx - 1)
            # Clear flash/toggle state for removed slot
            DEV_FX.flash_state.pop(idx, None)
            DEV_FX.toggle_state.pop(idx, None)
        return {'FINISHED'}


class SCORESYNC_OT_fx_select_slot(bpy.types.Operator):
    bl_idname = "scoresync.fx_select_slot"
    bl_label  = "Select FX Slot"

    index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        context.scene.scoresync_fx_index = self.index
        return {'FINISHED'}


class SCORESYNC_OT_fx_learn_start(bpy.types.Operator):
    bl_idname    = "scoresync.fx_learn_start"
    bl_label     = "Learn MIDI for FX Slot"
    bl_description = "Move a knob or hit a pad — ScoreSync captures the next CC or Note On"

    index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        DEV_FX.learning_slot = self.index
        context.scene.scoresync_fx_learn_status = f"Waiting… move a control for slot {self.index+1}"
        self.report({'INFO'}, f"FX Learn: waiting for MIDI on slot {self.index+1}")
        try:
            from .ops_connection import start_learn_scan
            start_learn_scan()
        except Exception:
            pass
        return {'FINISHED'}


class SCORESYNC_OT_fx_learn_cancel(bpy.types.Operator):
    bl_idname = "scoresync.fx_learn_cancel"
    bl_label  = "Cancel FX Learn"

    def execute(self, context):
        DEV_FX.learning_slot = -1
        context.scene.scoresync_fx_learn_status = ""
        try:
            from .ops_connection import stop_learn_scan
            stop_learn_scan()
        except Exception:
            pass
        return {'FINISHED'}


class SCORESYNC_OT_fx_clear_binding(bpy.types.Operator):
    """Clear the MIDI binding from this FX slot (keeps all other settings)"""
    bl_idname  = "scoresync.fx_clear_binding"
    bl_label   = "Reset MIDI Binding"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        scene    = context.scene
        slots    = getattr(scene, "scoresync_fx_slots", None)
        idx      = self.index if self.index >= 0 else getattr(scene, "scoresync_fx_index", -1)
        if not slots or idx < 0 or idx >= len(slots):
            return {'CANCELLED'}
        slot             = slots[idx]
        slot.midi_type   = "CC"
        slot.midi_channel = 0
        slot.midi_num    = 0
        scene.scoresync_fx_learn_status = f"Binding cleared for \"{slot.label}\""
        self.report({'INFO'}, f"MIDI binding cleared: {slot.label}")
        return {'FINISHED'}


class SCORESYNC_OT_fx_fire_slot(bpy.types.Operator):
    """Manually fire a note-type FX slot from the UI (test without hardware)."""
    bl_idname = "scoresync.fx_fire_slot"
    bl_label  = "Test Fire FX"

    index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        scene = context.scene
        slots = scene.scoresync_fx_slots
        if self.index >= len(slots):
            return {'CANCELLED'}
        slot = slots[self.index]
        handle_note_on_fx(slot.midi_channel, slot.midi_num, 100, scene)
        return {'FINISHED'}


class SCORESYNC_OT_vse_setup_strip(bpy.types.Operator):
    """Add BRIGHT_CONTRAST and COLOR_BALANCE modifiers to the active VSE strip."""
    bl_idname    = "scoresync.vse_setup_strip"
    bl_label     = "Setup Strip FX Modifiers"
    bl_description = (
        "Add Brightness/Contrast and Color Balance (Tint) modifiers to the "
        "selected strip so ScoreSync FX slots can drive them"
    )

    def execute(self, context):
        scene = context.scene
        seq   = scene.sequence_editor
        if seq is None:
            self.report({'WARNING'}, "No sequence editor in this scene.")
            return {'CANCELLED'}
        strip = seq.active_strip
        if strip is None:
            self.report({'WARNING'}, "No active strip selected.")
            return {'CANCELLED'}

        existing = {m.type for m in strip.modifiers}
        added = []
        if 'BRIGHT_CONTRAST' not in existing:
            m            = strip.modifiers.new(name="ScoreSync BC",   type='BRIGHT_CONTRAST')
            m.bright     = 0.0
            m.contrast   = 0.0
            added.append("Bright/Contrast")
        if 'COLOR_BALANCE' not in existing:
            strip.modifiers.new(name="ScoreSync Tint", type='COLOR_BALANCE')
            added.append("Color Balance")

        if added:
            self.report({'INFO'}, f"Added modifiers: {', '.join(added)} to '{strip.name}'")
        else:
            self.report({'INFO'}, f"'{strip.name}' already has both modifiers.")
        return {'FINISHED'}


class SCORESYNC_OT_fx_add_for_channel(bpy.types.Operator):
    """Quick-add an FX slot pre-wired to a specific VSE channel."""
    bl_idname    = "scoresync.fx_add_for_channel"
    bl_label     = "Add FX Slot for Channel"
    bl_description = "Create a new FX slot already targeting this VSE channel"

    channel : bpy.props.IntProperty(default=1)
    fx_type : bpy.props.StringProperty(default="OPACITY")

    def execute(self, context):
        scene      = context.scene
        slot       = scene.scoresync_fx_slots.add()
        slot.label = f"Ch{self.channel} {self.fx_type.title()}"
        slot.fx_type      = self.fx_type
        slot.target_mode  = "VSE_CHANNEL"
        slot.target_name  = str(self.channel)
        scene.scoresync_fx_index = len(scene.scoresync_fx_slots) - 1
        self.report({'INFO'}, f"Added FX slot for VSE channel {self.channel}")
        return {'FINISHED'}


# ── Registration ──────────────────────────────────────────────────────────────

fx_classes = (
    ScoreSyncFXSlot,
    SCORESYNC_OT_fx_setup_material,
    SCORESYNC_OT_fx_add_slot,
    SCORESYNC_OT_fx_remove_slot,
    SCORESYNC_OT_fx_select_slot,
    SCORESYNC_OT_fx_learn_start,
    SCORESYNC_OT_fx_learn_cancel,
    SCORESYNC_OT_fx_clear_binding,
    SCORESYNC_OT_fx_fire_slot,
    SCORESYNC_OT_vse_setup_strip,
    SCORESYNC_OT_fx_add_for_channel,
)
