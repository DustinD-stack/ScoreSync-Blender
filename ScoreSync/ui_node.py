"""
ScoreSync v2 — ui_node.py
Node Editor sidebar → ScoreSync tab.
Only visible when editing a Shader (material) node tree.

Panels:
  SCORESYNC_PT_node_main    Header + setup chain button
  SCORESYNC_PT_node_fx      Material FX slots (MAT_* types only)
  SCORESYNC_PT_node_mapping MIDI mapping (compact)
"""

import bpy
from .ui_panel import _draw_fx_rack, _draw_mapping


# ── Poll helper ───────────────────────────────────────────────────────────────

def _is_shader_editor(context):
    sd = getattr(context, "space_data", None)
    return (sd is not None
            and sd.type == 'NODE_EDITOR'
            and sd.tree_type == 'ShaderNodeTree')


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
        return _is_shader_editor(context)

    def draw(self, context):
        layout = self.layout
        scene  = context.scene
        mat    = _active_material(context)

        # LED
        led = getattr(scene, "scoresync_led_text", "🔴 idle")
        layout.label(text=led)

        # Active material badge
        if mat:
            row = layout.row(align=True)
            row.label(text=mat.name, icon='MATERIAL')
            row.label(text="active material")
        else:
            layout.label(text="No material on active object.", icon='INFO')
            return

        layout.separator(factor=0.3)

        # Node chain setup
        box = layout.box()
        box.label(text="FX Node Chain", icon='NODETREE')

        # Check whether ScoreSync nodes already exist in this material
        has_hsv = has_bc = False
        if mat and mat.use_nodes:
            for n in mat.node_tree.nodes:
                if n.type == 'HUE_SAT'       and 'ScoreSync' in n.name: has_hsv = True
                if n.type == 'BRIGHTCONTRAST' and 'ScoreSync' in n.name: has_bc  = True

        if has_hsv and has_bc:
            box.label(text="✓ ScoreSync HSV + BC nodes present", icon='CHECKMARK')
        else:
            if not has_hsv:
                box.label(text="Missing: ScoreSync HSV node", icon='ERROR')
            if not has_bc:
                box.label(text="Missing: ScoreSync BC node",  icon='ERROR')
            box.operator("scoresync.fx_setup_material", icon='NODE_MATERIAL',
                         text="Setup Material FX Chain")

        # Show node current values if they exist
        if mat and mat.use_nodes and has_hsv:
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

        if mat and mat.use_nodes and has_bc:
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

        # Principled Alpha / Emission quick controls
        if mat and mat.use_nodes:
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
# MATERIAL FX SLOTS
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
        return _is_shader_editor(context)

    def draw(self, context):
        layout = self.layout
        scene  = context.scene
        mat    = _active_material(context)

        if mat:
            layout.label(
                text=f"Driving: {mat.name}",
                icon='MATERIAL',
            )
        layout.label(
            text="Add MAT_ type slots to control this material via MIDI.",
            icon='INFO',
        )
        _draw_fx_rack(layout, scene, slot_filter='MAT', compact=False)


# ════════════════════════════════════════════════════════════════════════════
# MIDI MAPPING (compact, for quick property-path lookup while in node editor)
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
        return _is_shader_editor(context)

    def draw(self, context):
        _draw_mapping(self.layout, context.scene, compact=True)


# ── Registration list ─────────────────────────────────────────────────────────

node_panel_classes = (
    SCORESYNC_PT_node_main,
    SCORESYNC_PT_node_fx,
    SCORESYNC_PT_node_mapping,
)
