"""
ScoreSync v2 — ui_node.py
Shader / Node Editor N-panel sidebar → ScoreSync tab.
Only visible when editing a Shader (material) node tree.

Panels:
  SCORESYNC_PT_node_main        Header: LED, status, editor jumps
  SCORESYNC_PT_node_transport   Quick transport controls
  SCORESYNC_PT_node_chain       FX node chain setup + live value sliders
  SCORESYNC_PT_node_fx          Material FX slots (MAT_* types only)
  SCORESYNC_PT_node_sampler     Sampler pads (accessible from Shader Editor)
  SCORESYNC_PT_node_mapping     Full MIDI mapping inspector
"""

import bpy
from .ui_panel import _draw_fx_rack, _draw_mapping, _draw_sampler


# ── Poll helper ───────────────────────────────────────────────────────────────

def _is_node_editor(context):
    """Show ScoreSync tab whenever any Node Editor is open."""
    sd = getattr(context, "space_data", None)
    return sd is not None and sd.type == 'NODE_EDITOR'


def _is_shader_editor(context):
    sd = getattr(context, "space_data", None)
    return (sd is not None
            and sd.type == 'NODE_EDITOR'
            and getattr(sd, 'tree_type', '') == 'ShaderNodeTree')


def _active_material(context):
    """Return active material from the active object, or None."""
    obj = getattr(context, "active_object", None)
    if obj and obj.material_slots:
        return obj.active_material
    return None


# ════════════════════════════════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_node_main(bpy.types.Panel):
    bl_label       = "ScoreSync"
    bl_idname      = "SCORESYNC_PT_node_main"
    bl_space_type  = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"

    @classmethod
    def poll(cls, context):
        return _is_node_editor(context)

    def draw(self, context):
        layout = self.layout
        scene  = context.scene

        # LED + status
        led    = getattr(scene, "scoresync_led_text", "🔴 idle")
        status = getattr(scene, "scoresync_status",   "Not connected")
        row = layout.row(align=True)
        row.label(text=led)
        row.label(text=status)

        # Active material badge
        mat = _active_material(context)
        if mat:
            row = layout.row(align=True)
            row.label(text=mat.name, icon='MATERIAL')
        else:
            layout.label(text="No material on active object.", icon='INFO')

        # Quick editor jump
        row = layout.row(align=True)
        op_v3d = row.operator("scoresync.open_area", icon='VIEW3D',  text="→ 3D View")
        op_v3d.editor_type = 'VIEW_3D'
        op_vse = row.operator("scoresync.open_area", icon='SEQUENCE', text="→ Video Editor")
        op_vse.editor_type = 'SEQUENCE_EDITOR'


# ════════════════════════════════════════════════════════════════════════════
# TRANSPORT (quick controls — no need to leave the Shader Editor)
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_node_transport(bpy.types.Panel):
    bl_label       = "Transport"
    bl_idname      = "SCORESYNC_PT_node_transport"
    bl_space_type  = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_node_main"
    bl_options     = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return _is_node_editor(context)

    def draw(self, context):
        layout = self.layout
        scene  = context.scene

        row = layout.row(align=True)
        row.operator("scoresync.tx_play",  icon='PLAY',  text="Play")
        row.operator("scoresync.tx_stop",  icon='PAUSE', text="Stop")
        row.operator("scoresync.tx_locate_to_timeline", icon='TIME', text="Locate")

        layout.separator(factor=0.3)
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(scene, "scoresync_follow_clock",   text="Follow Clock")
        row.prop(scene, "scoresync_reset_on_start", text="Reset on Start")
        row = col.row(align=True)
        row.prop(scene, "scoresync_use_manual_bpm", text="Manual BPM")
        sub = row.row()
        sub.enabled = scene.scoresync_use_manual_bpm
        sub.prop(scene, "scoresync_manual_bpm", text="")
        if not scene.scoresync_use_manual_bpm:
            col.label(text=f"Auto BPM: {scene.scoresync_bpm_estimate:.2f}")


# ════════════════════════════════════════════════════════════════════════════
# FX NODE CHAIN SETUP + LIVE SLIDERS
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_node_chain(bpy.types.Panel):
    bl_label       = "Material FX Chain"
    bl_idname      = "SCORESYNC_PT_node_chain"
    bl_space_type  = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_node_main"

    @classmethod
    def poll(cls, context):
        return _is_node_editor(context)

    def draw(self, context):
        layout = self.layout
        mat    = _active_material(context)

        if not _is_shader_editor(context):
            layout.label(text="Open a Shader / Material node tree to use FX.", icon='INFO')
            return

        if not mat:
            layout.label(text="No material on active object.", icon='INFO')
            return

        # Check whether ScoreSync nodes already exist in this material
        has_hsv = has_bc = False
        if mat.use_nodes:
            for n in mat.node_tree.nodes:
                if n.type == 'HUE_SAT'       and 'ScoreSync' in n.name: has_hsv = True
                if n.type == 'BRIGHTCONTRAST' and 'ScoreSync' in n.name: has_bc  = True

        box = layout.box()
        box.label(text="FX Node Chain", icon='NODETREE')

        if has_hsv and has_bc:
            box.label(text="✓ ScoreSync nodes present", icon='CHECKMARK')
        else:
            if not has_hsv:
                box.label(text="Missing: ScoreSync HSV node", icon='ERROR')
            if not has_bc:
                box.label(text="Missing: ScoreSync BC node",  icon='ERROR')
            box.operator("scoresync.fx_setup_material", icon='NODE_MATERIAL',
                         text="Setup Material FX Chain")

        # Live HSV sliders
        if mat.use_nodes and has_hsv:
            hsv = next(
                (n for n in mat.node_tree.nodes
                 if n.type == 'HUE_SAT' and 'ScoreSync' in n.name), None
            )
            if hsv:
                layout.separator(factor=0.3)
                col = layout.column(align=True)
                col.label(text="HSV Node Values:", icon='COLOR')
                col.prop(hsv.inputs["Hue"],        "default_value", text="Hue")
                col.prop(hsv.inputs["Saturation"], "default_value", text="Saturation")
                col.prop(hsv.inputs["Value"],      "default_value", text="Value")

        # Live BC sliders
        if mat.use_nodes and has_bc:
            bc = next(
                (n for n in mat.node_tree.nodes
                 if n.type == 'BRIGHTCONTRAST' and 'ScoreSync' in n.name), None
            )
            if bc:
                layout.separator(factor=0.3)
                col = layout.column(align=True)
                col.label(text="Bright/Contrast Node Values:", icon='SHADERFX')
                col.prop(bc.inputs["Bright"],   "default_value", text="Brightness")
                col.prop(bc.inputs["Contrast"], "default_value", text="Contrast")

        # Principled BSDF quick controls
        if mat.use_nodes:
            princ = next(
                (n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None
            )
            if princ:
                layout.separator(factor=0.3)
                col = layout.column(align=True)
                col.label(text="Principled BSDF:", icon='MATERIAL')
                col.prop(princ.inputs["Alpha"],             "default_value", text="Opacity")
                if "Emission Strength" in princ.inputs:
                    col.prop(princ.inputs["Emission Strength"], "default_value", text="Emission")


# ════════════════════════════════════════════════════════════════════════════
# MATERIAL FX SLOTS (MIDI-driven)
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_node_fx(bpy.types.Panel):
    bl_label       = "Material FX (MIDI)"
    bl_idname      = "SCORESYNC_PT_node_fx"
    bl_space_type  = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_node_main"
    bl_options     = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return _is_node_editor(context)

    def draw(self, context):
        layout = self.layout
        scene  = context.scene
        mat    = _active_material(context)

        if not _is_shader_editor(context):
            layout.label(text="Open a Shader node tree to use Material FX.", icon='INFO')
            return

        if mat:
            layout.label(text=f"Driving: {mat.name}", icon='MATERIAL')
        layout.label(
            text="Add MAT_ type slots to control this material via MIDI.",
            icon='INFO',
        )
        _draw_fx_rack(layout, scene, slot_filter='MAT', compact=False)


# ════════════════════════════════════════════════════════════════════════════
# SAMPLER PADS (accessible without leaving Shader Editor)
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_node_sampler(bpy.types.Panel):
    bl_label       = "Sampler Pads"
    bl_idname      = "SCORESYNC_PT_node_sampler"
    bl_space_type  = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_node_main"
    bl_options     = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return _is_node_editor(context)

    def draw(self, context):
        layout = self.layout
        scene  = context.scene

        layout.label(
            text="Trigger clips or swap textures via MIDI pads.",
            icon='INFO',
        )
        _draw_sampler(layout, scene, compact=False)


# ════════════════════════════════════════════════════════════════════════════
# MIDI MAPPING (full inspector)
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_node_mapping(bpy.types.Panel):
    bl_label       = "MIDI Mapping"
    bl_idname      = "SCORESYNC_PT_node_mapping"
    bl_space_type  = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_node_main"
    bl_options     = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return _is_node_editor(context)

    def draw(self, context):
        _draw_mapping(self.layout, context.scene, compact=False)


# ── Registration list ─────────────────────────────────────────────────────────

node_panel_classes = (
    SCORESYNC_PT_node_main,
    SCORESYNC_PT_node_transport,
    SCORESYNC_PT_node_chain,
    SCORESYNC_PT_node_fx,
    SCORESYNC_PT_node_sampler,
    SCORESYNC_PT_node_mapping,
)
