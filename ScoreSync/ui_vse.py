"""
ScoreSync v2 — ui_vse.py
Video Sequence Editor (VSE) N-panel sidebar → ScoreSync tab.

Panels:
  SCORESYNC_PT_vse_main       Header: LED, status, quick transport
  SCORESYNC_PT_vse_strip      Active Strip FX inspector (direct sliders)
  SCORESYNC_PT_vse_fx         FX Rack (VSE channel slots only)
  SCORESYNC_PT_vse_sampler    Sampler pad grid (VSE-output focus)

The strip inspector lets you manually tweak opacity/brightness/saturation/
tint on the selected strip in real time — no MIDI required — while the FX
Rack panel shows any MIDI-driven slots targeting the same channel alongside.
"""

import bpy
import time
from .ui_panel import _draw_fx_rack, _draw_sampler


# ── VSE helpers ───────────────────────────────────────────────────────────────

def _active_strip(context):
    seq = context.scene.sequence_editor
    return seq.active_strip if seq else None


def _get_mod(strip, mod_type):
    for m in strip.modifiers:
        if m.type == mod_type:
            return m
    return None


def _slots_for_channel(scene, channel):
    """Return FX slots targeting a specific VSE channel number."""
    _VSE_TYPES = {"OPACITY","COLOR_MULT","SATURATION","BRIGHTNESS","CONTRAST",
                  "TINT_R","TINT_G","TINT_B"}
    result = []
    for i, slot in enumerate(getattr(scene, "scoresync_fx_slots", [])):
        if (slot.fx_type in _VSE_TYPES
                and slot.target_mode == "VSE_CHANNEL"
                and slot.target_name == str(channel)):
            result.append((i, slot))
    return result


# ════════════════════════════════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_vse_main(bpy.types.Panel):
    bl_label       = "ScoreSync"
    bl_idname      = "SCORESYNC_PT_vse_main"
    bl_space_type  = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"

    def draw(self, context):
        layout = self.layout
        scene  = context.scene

        # LED + status
        led    = getattr(scene, "scoresync_led_text", "🔴 idle")
        status = getattr(scene, "scoresync_status",   "Not connected")
        row = layout.row(align=True)
        row.label(text=led)
        row.label(text=status)

        # Quick transport
        row = layout.row(align=True)
        row.operator("scoresync.tx_play",  icon='PLAY',  text="Play")
        row.operator("scoresync.tx_stop",  icon='PAUSE', text="Stop")
        row.operator("scoresync.tx_locate_to_timeline", icon='TIME', text="Locate")

        # ScoreSync Editor button
        layout.separator(factor=0.2)
        col = layout.column(align=True)
        col.scale_y = 1.5
        col.operator("scoresync.open_editor", icon='NLA', text="Open ScoreSync Editor")

        # Quick editor jump
        layout.separator(factor=0.2)
        row = layout.row(align=True)
        op_v3d = row.operator("scoresync.open_area", icon='VIEW3D',
                              text="→ 3D View")
        op_v3d.editor_type = 'VIEW_3D'
        op_node = row.operator("scoresync.open_area", icon='NODE',
                               text="→ Shader Editor")
        op_node.editor_type = 'NODE_EDITOR'


# ════════════════════════════════════════════════════════════════════════════
# ACTIVE STRIP FX INSPECTOR
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_vse_strip(bpy.types.Panel):
    bl_label       = "Active Strip"
    bl_idname      = "SCORESYNC_PT_vse_strip"
    bl_space_type  = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_vse_main"

    def draw(self, context):
        layout = self.layout
        scene  = context.scene
        strip  = _active_strip(context)

        if strip is None:
            layout.label(text="Select a strip in the VSE.", icon='INFO')
            return

        # Strip badge
        box = layout.box()
        row = box.row(align=True)
        row.label(text=strip.name, icon='SEQUENCE')
        row.label(text=f"Ch {strip.channel}  "
                       f"[{strip.frame_final_start}–{strip.frame_final_end}]")

        # ── Direct strip properties ──────────────────────────────────────
        col = box.column(align=True)
        col.label(text="Blend", icon='IMAGE_ALPHA')

        # Opacity — only meaningful above channel 1 with ALPHA_OVER
        row = col.row(align=True)
        row.prop(strip, "blend_alpha",   text="Opacity")
        row.prop(strip, "blend_type",    text="")

        col.prop(strip, "color_multiply",   text="Bright Mult")
        col.prop(strip, "color_saturation", text="Saturation")

        # ── Modifier-based FX ────────────────────────────────────────────
        bc_mod   = _get_mod(strip, 'BRIGHT_CONTRAST')
        tint_mod = _get_mod(strip, 'COLOR_BALANCE')

        has_mods = bc_mod or tint_mod

        if has_mods:
            box.separator(factor=0.4)
            col = box.column(align=True)
            col.label(text="Modifiers", icon='SHADERFX')
            if bc_mod:
                row = col.row(align=True)
                row.prop(bc_mod, "bright",   text="Brightness")
                row.prop(bc_mod, "contrast", text="Contrast")
            if tint_mod:
                cb = tint_mod.color_balance
                col.label(text="Tint (Gain):")
                row = col.row(align=True)
                row.prop(cb, "gain", text="")  # RGB color picker

        # Setup button if modifiers missing
        if not has_mods:
            box.separator(factor=0.4)
            box.label(text="Add modifiers for Bright/Contrast & Tint:", icon='INFO')
            box.operator("scoresync.vse_setup_strip", icon='SHADERFX',
                         text="Setup Strip FX Modifiers")

        # ── MIDI FX slots targeting this channel ─────────────────────────
        slots = _slots_for_channel(scene, strip.channel)
        if slots:
            box.separator(factor=0.4)
            col = box.column(align=True)
            col.label(text="MIDI FX on this channel:", icon='DRIVER')
            for i, slot in slots:
                live = getattr(slot, "current_value", 0.0)
                vmin, vmax = slot.value_min, slot.value_max
                rng  = (vmax - vmin) or 1.0
                pct  = max(0.0, min(1.0, (live - vmin) / rng))
                bar  = "█" * int(pct * 8) + "░" * (8 - int(pct * 8))
                row  = col.row(align=True)
                row.label(
                    text=f"{slot.fx_type:<14} [{bar}] {live:.2f}",
                    icon='RADIOBUT_ON' if slot.enabled else 'RADIOBUT_OFF',
                )
                op = row.operator("scoresync.fx_select_slot", text="", icon='PROPERTIES')
                op.index = i
        else:
            box.separator(factor=0.4)
            row = box.row(align=True)
            row.label(text="No MIDI FX on this channel.", icon='INFO')
            # Quick-add common FX slots for this channel
            for fxt, lbl in (("OPACITY","+ Opacity"), ("BRIGHTNESS","+ Bright"),
                              ("SATURATION","+ Sat")):
                op = row.operator("scoresync.fx_add_for_channel", text=lbl)
                op.channel = strip.channel
                op.fx_type = fxt


# ════════════════════════════════════════════════════════════════════════════
# FX RACK (VSE channel slots only)
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_vse_fx(bpy.types.Panel):
    bl_label       = "FX Rack"
    bl_idname      = "SCORESYNC_PT_vse_fx"
    bl_space_type  = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_vse_main"
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        _draw_fx_rack(self.layout, context.scene, slot_filter='VSE', compact=False)


# ════════════════════════════════════════════════════════════════════════════
# SAMPLER PADS (VSE-output focus)
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_vse_sampler(bpy.types.Panel):
    bl_label       = "Sampler Pads"
    bl_idname      = "SCORESYNC_PT_vse_sampler"
    bl_space_type  = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_vse_main"
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene  = context.scene

        # Tip banner
        layout.label(
            text="Pads insert strips at the current frame.",
            icon='INFO',
        )
        _draw_sampler(layout, scene, compact=False)


# ════════════════════════════════════════════════════════════════════════════
# MIDI MAPPING (quick compact view for in-VSE workflow)
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_vse_mapping(bpy.types.Panel):
    bl_label       = "MIDI Mapping"
    bl_idname      = "SCORESYNC_PT_vse_mapping"
    bl_space_type  = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_vse_main"
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        from .ui_panel import _draw_mapping
        _draw_mapping(self.layout, context.scene, compact=False)


# ── Registration list ─────────────────────────────────────────────────────────

vse_panel_classes = (
    SCORESYNC_PT_vse_main,
    SCORESYNC_PT_vse_strip,
    SCORESYNC_PT_vse_fx,
    SCORESYNC_PT_vse_sampler,
    SCORESYNC_PT_vse_mapping,
)
