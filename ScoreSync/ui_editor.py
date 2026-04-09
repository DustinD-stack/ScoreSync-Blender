"""
ScoreSync v2 — ui_editor.py
Unified ScoreSync Editor — large tabbed popup dialog.

Opens via the "Open ScoreSync Editor" button in any ScoreSync N-panel.
Width defaults to 960 px; Blender lets you drag the dialog edges to resize.
Close with OK, Escape, or the X button.
"""

import bpy
import bpy.utils.previews


# ── Persist last-used tab between opens ───────────────────────────────────────

_ACTIVE_TAB = ["SAMPLER"]


# ── Preview collection for pad thumbnails ─────────────────────────────────────

_pcoll = None

def _ensure_pcoll():
    global _pcoll
    if _pcoll is None:
        _pcoll = bpy.utils.previews.new()
    return _pcoll

def _free_pcoll():
    global _pcoll
    if _pcoll is not None:
        bpy.utils.previews.remove(_pcoll)
        _pcoll = None

def _pad_icon_id(sample: dict) -> int:
    """Return a Blender icon_id for the sample thumbnail, or 0 if unavailable."""
    if not sample:
        return 0
    import os
    pcoll     = _ensure_pcoll()
    sid       = sample.get("id", "")
    src       = sample.get("source_path", "")
    src_type  = sample.get("source_type", "")

    if not sid or not src:
        return 0

    # Return cached icon if already loaded
    if sid in pcoll:
        return pcoll[sid].icon_id

    if not os.path.exists(src):
        return 0

    try:
        load_type = "IMAGE" if src_type == "IMAGE_SEQUENCE" else "MOVIE"
        preview = pcoll.load(sid, src, load_type)
        return preview.icon_id
    except Exception:
        return 0


# ── Sampler draw (two-column) ─────────────────────────────────────────────────

def _draw_sampler_editor(layout, scene):
    from .ops_sampler import DEV_SAMPLER

    banks           = getattr(scene, "scoresync_banks",      [])
    active_bank_idx = getattr(scene, "scoresync_active_bank", 0)
    active_pad_idx  = getattr(scene, "scoresync_active_pad",  0)

    top = layout.row(align=True)
    top.scale_y = 1.2
    for i, bank in enumerate(banks):
        op = top.operator("scoresync.sampler_set_active_bank",
                          text=bank.name, depress=(i == active_bank_idx))
        op.index = i
    top.separator()
    top.operator("scoresync.sampler_add_bank",    icon='ADD',   text="Add Bank")
    top.operator("scoresync.sampler_remove_bank", icon='TRASH', text="")

    if not banks:
        layout.separator(factor=0.5)
        layout.label(text="No banks yet — click Add Bank to get started.", icon='INFO')
        return

    layout.separator(factor=0.4)

    split = layout.split(factor=0.52)
    left  = split.column()
    right = split.column()

    if active_bank_idx < len(banks):
        bank      = banks[active_bank_idx]
        pads      = bank.pads
        pad_count = len(pads)

        if pad_count:
            # ── Big box pad grid using grid_flow ──────────────────────────
            grid = left.grid_flow(
                row_major=True, columns=4,
                even_columns=True, even_rows=True, align=True,
            )
            for idx in range(pad_count):
                pad    = pads[idx]
                is_sel = (idx == active_pad_idx)
                sample = DEV_SAMPLER.cache.get(pad.sample_id) if pad.sample_id else None

                label = pad.label or f"P{idx + 1}"
                if not pad.enabled:
                    label = f"[{label}]"

                icon_id = _pad_icon_id(sample)

                cell = grid.column(align=True)

                if icon_id:
                    # Thumbnail fills the pad body
                    cell.template_icon(icon_value=icon_id, scale=4.8)
                    # Thin bottom strip: name + fire
                    bot = cell.row(align=True)
                    bot.scale_y = 0.85
                    op_sel = bot.operator(
                        "scoresync.sampler_select_pad",
                        text=label, depress=is_sel, emboss=True,
                    )
                    op_sel.index = idx
                    op_f = bot.operator(
                        "scoresync.sampler_fire_pad",
                        text="", icon='PLAY',
                    )
                    op_f.bank_index = active_bank_idx
                    op_f.pad_index  = idx
                    op_f.velocity   = 100
                else:
                    # Empty pad — height matches a thumbnail pad
                    cell.scale_y = 4.8
                    op_sel = cell.operator(
                        "scoresync.sampler_select_pad",
                        text=label, depress=is_sel, emboss=True,
                    )
                    op_sel.index = idx

        left.separator(factor=0.6)
        row = left.row(align=True)
        row.prop(scene, "scoresync_sampler_pc_switch", text="PC → Bank Switch")
        sub = row.row()
        sub.enabled = getattr(scene, "scoresync_sampler_pc_switch", False)
        sub.prop(scene, "scoresync_sampler_pc_channel", text="Ch")

        row = left.row(align=True)
        row.operator("scoresync.sampler_reload_cache", icon='FILE_REFRESH', text="Reload Cache")
        row.operator("scoresync.sampler_export_bank",  icon='EXPORT',       text="Export Bank")
        row.operator("scoresync.sampler_import_bank",  icon='IMPORT',       text="Import Bank")

    if banks and active_bank_idx < len(banks):
        bank      = banks[active_bank_idx]
        pads      = bank.pads
        pad_count = len(pads)

        if pad_count and active_pad_idx < pad_count:
            pad    = pads[active_pad_idx]
            sample = DEV_SAMPLER.cache.get(pad.sample_id) if pad.sample_id else None
            box    = right.box()

            # Header row with pad title + reset button
            hdr = box.row(align=True)
            hdr.label(text=f"Pad {active_pad_idx + 1} — {pad.label or '(unlabelled)'}",
                      icon='PROPERTIES')
            op_rst = hdr.operator("scoresync.sampler_reset_pad",
                                  text="", icon='TRASH', emboss=False)
            op_rst.pad_index = active_pad_idx

            box.prop(pad, "label",   text="Name")
            box.prop(pad, "enabled", text="Enabled")
            box.separator(factor=0.4)

            row = box.row(align=True)
            row.prop(pad, "note",    text="Note")
            row.prop(pad, "channel", text="Ch")

            box.prop(pad, "output_mode", text="Output")
            if pad.output_mode in ("VSE", "BOTH"):
                box.prop(pad, "vse_channel", text="VSE Channel")
            if pad.output_mode in ("MAT", "BOTH"):
                box.prop(pad, "mat_target", text="Object")

            box.prop(pad, "velocity_to_alpha", text="Velocity → Alpha")
            box.prop(pad, "color", text="Colour")
            box.separator(factor=0.4)

            # Sample info + preview
            if sample:
                icon_id = _pad_icon_id(sample)
                if icon_id:
                    box.template_icon(icon_value=icon_id, scale=8.0)
                box.label(
                    text=f"{sample.get('label','?')}  "
                         f"({sample.get('frame_start')}→{sample.get('frame_end')})",
                    icon='SEQUENCE',
                )
            elif pad.sample_id:
                box.label(text=f"ID {pad.sample_id} (not in cache)", icon='ERROR')
            else:
                box.label(text="No sample assigned", icon='INFO')

            box.separator(factor=0.4)
            row = box.row(align=True)
            row.scale_y = 1.3
            op_l = row.operator("scoresync.sampler_load_file",
                                icon='FILEBROWSER', text="Load File")
            op_l.pad_index = active_pad_idx
            op_s = row.operator("scoresync.sampler_sample_from_timeline",
                                icon='RENDER_STILL', text="Sample Timeline")
            op_s.pad_index = active_pad_idx

            # Fire button
            row2 = box.row(align=True)
            row2.scale_y = 1.2
            op_f = row2.operator("scoresync.sampler_fire_pad",
                                 icon='PLAY', text="Fire Pad")
            op_f.bank_index = active_bank_idx
            op_f.pad_index  = active_pad_idx
            op_f.velocity   = 100
        else:
            right.label(text="Select a pad to edit.", icon='INFO')


# ── FX Rack draw (two-column) ─────────────────────────────────────────────────

def _draw_fx_editor(layout, scene):
    from .ops_fx import DEV_FX
    from .ops_mapping import DEV_MAP

    learn_status = getattr(scene, "scoresync_fx_learn_status", "")
    if DEV_FX.learning_slot >= 0:
        row = layout.row(align=True)
        row.alert = True
        row.label(text=learn_status or "Waiting for MIDI…", icon='REC')
        row.operator("scoresync.fx_learn_cancel", text="", icon='X')
    elif learn_status:
        layout.label(text=learn_status, icon='INFO')

    row = layout.row(align=True)
    row.operator("scoresync.fx_setup_material",  icon='NODE_MATERIAL', text="Setup Material FX Chain")
    row.operator("scoresync.vse_setup_strip",    icon='SHADERFX',      text="Setup Strip FX Modifiers")
    layout.separator(factor=0.4)

    fx_slots  = getattr(scene, "scoresync_fx_slots", [])
    active_fx = getattr(scene, "scoresync_fx_index", 0)

    split = layout.split(factor=0.50)
    left  = split.column()
    right = split.column()

    if not fx_slots:
        left.label(text="No FX slots yet — click Add FX Slot.", icon='INFO')
    else:
        for i, slot in enumerate(fx_slots):
            is_sel = (i == active_fx)
            live   = getattr(slot, "current_value", 0.0)
            vmin   = slot.value_min
            vmax   = slot.value_max
            rng    = (vmax - vmin) or 1.0
            pct    = max(0.0, min(1.0, (live - vmin) / rng))
            bar    = "█" * int(pct * 8) + "░" * (8 - int(pct * 8))

            row = left.row(align=True)
            row.prop(slot, "enabled", text="")
            op_sel = row.operator(
                "scoresync.fx_select_slot",
                text=f"{slot.label}  [{bar}] {live:.2f}",
                depress=is_sel, emboss=is_sel,
            )
            op_sel.index = i
            op_learn = row.operator("scoresync.fx_learn_start", text="", icon='REC')
            op_learn.index = i
            if slot.trigger_mode in ("MOMENTARY", "TOGGLE", "FLASH"):
                op_f = row.operator("scoresync.fx_fire_slot", text="", icon='PLAY')
                op_f.index = i
            op_rm = row.operator("scoresync.fx_remove_slot", text="", icon='X')
            op_rm.index = i

    left.separator(factor=0.5)
    left.operator("scoresync.fx_add_slot", icon='ADD', text="Add FX Slot")

    if fx_slots and active_fx < len(fx_slots):
        slot = fx_slots[active_fx]
        box  = right.box()
        box.label(text=f"Edit: {slot.label}", icon='PROPERTIES')
        box.prop(slot, "label",    text="Name")
        box.prop(slot, "enabled",  text="Enabled")
        box.prop(slot, "fx_type",  text="FX Type")
        box.separator(factor=0.4)

        box.label(text="Target:", icon='OBJECT_DATA')
        box.prop(slot, "target_mode", text="")
        if slot.target_mode == "VSE_CHANNEL":
            box.prop(slot, "target_name", text="VSE Ch #")
        elif slot.target_mode == "OBJECT_MAT":
            box.prop(slot, "target_name", text="Object")

        box.separator(factor=0.4)
        box.label(text="MIDI Binding:", icon='DRIVER')
        row = box.row(align=True)
        row.prop(slot, "midi_type",    text="")
        row.prop(slot, "midi_channel", text="Ch")
        row.prop(slot, "midi_num",     text="Num")
        box.prop(slot, "trigger_mode", text="Trigger")
        if slot.trigger_mode == "FLASH":
            box.prop(slot, "decay_ms", text="Decay (ms)")

        box.separator(factor=0.4)
        row = box.row(align=True)
        row.prop(slot, "value_min", text="Min")
        row.prop(slot, "value_max", text="Max")

        key = (slot.midi_type, slot.midi_channel, slot.midi_num)
        raw = DEV_MAP.last_val.get(key)
        if raw is not None:
            box.label(
                text=f"Live MIDI: {raw}  →  {slot.current_value:.4f}",
                icon='DECORATE_ANIMATE',
            )
    else:
        right.label(text="Select a slot to edit.", icon='INFO')


# ── MIDI Mapping draw (two-column) ────────────────────────────────────────────

def _draw_mapping_editor(layout, scene):
    from .ops_mapping import DEV_MAP, _midi_to_value

    top = layout.row(align=True)
    if DEV_MAP.learning:
        top.alert = True
        top.operator("scoresync.mapping_learn_cancel", icon='X', text="Cancel Learn")
    else:
        top.operator("scoresync.mapping_learn_start",  icon='REC', text="Learn MIDI")

    top.separator()
    top.label(text="Presets:")
    for pid, lbl in (("CAMERA", "Camera"), ("ACTIVE_OBJECT", "Object"), ("SCENE", "Scene")):
        op = top.operator("scoresync.mapping_apply_preset", text=lbl)
        op.preset = pid

    status = getattr(scene, "scoresync_mapping_learn_status", "")
    if status:
        layout.label(text=status, icon='INFO')

    layout.separator(factor=0.4)

    mappings       = getattr(scene, "scoresync_mappings", [])
    active_map_idx = getattr(scene, "scoresync_mapping_index", 0)

    split = layout.split(factor=0.52)
    left  = split.column()
    right = split.column()

    if not mappings:
        left.label(text="No mappings yet — click Learn or a preset.", icon='INFO')
    else:
        for i, m in enumerate(mappings):
            is_sel = (i == active_map_idx)
            row = left.row(align=True)
            row.prop(m, "enabled", text="")
            op = row.operator(
                "scoresync.mapping_select",
                text=f"{m.label}  {m.midi_type} ch{m.channel} #{m.midi_num}",
                depress=is_sel, emboss=is_sel,
            )
            op.index = i
            op2 = row.operator("scoresync.mapping_assign", text="", icon='EYEDROPPER')
            op2.index = i
            op3 = row.operator("scoresync.mapping_remove", text="", icon='X')
            op3.index = i

    left.separator(factor=0.5)
    row = left.row(align=True)
    row.operator("scoresync.mapping_add",    icon='ADD',    text="Add")
    row.operator("scoresync.mapping_export", icon='EXPORT', text="Export")
    row.operator("scoresync.mapping_import", icon='IMPORT', text="Import")

    if mappings and active_map_idx < len(mappings):
        m   = mappings[active_map_idx]
        box = right.box()
        box.label(text=f"Edit: {m.label}", icon='PROPERTIES')
        box.prop(m, "label",   text="Name")
        box.prop(m, "enabled", text="Enabled")

        box.separator(factor=0.4)
        box.label(text="MIDI Source:", icon='DRIVER')
        row = box.row(align=True)
        row.prop(m, "midi_type", text="")
        row.prop(m, "channel",   text="Ch")
        row.prop(m, "midi_num",  text="Num")
        op = box.operator("scoresync.mapping_assign",
                          text="← Assign from Learn", icon='EYEDROPPER')
        op.index = active_map_idx

        box.separator(factor=0.4)
        box.label(text="Blender Target:", icon='OBJECT_DATA')
        box.prop(m, "id_type",   text="Type")
        box.prop(m, "id_name",   text="Datablock")
        box.prop(m, "data_path", text="Path")

        box.separator(factor=0.4)
        row = box.row(align=True)
        row.prop(m, "value_min", text="Min")
        row.prop(m, "value_max", text="Max")

        key = (m.midi_type, m.channel, m.midi_num)
        raw = DEV_MAP.last_val.get(key)
        if raw is not None:
            box.label(
                text=f"Live: raw {raw}  →  {_midi_to_value(raw, m.value_min, m.value_max):.4f}",
                icon='DECORATE_ANIMATE',
            )
    else:
        right.label(text="Select a mapping to edit.", icon='INFO')


# ── Editor operator ───────────────────────────────────────────────────────────

class SCORESYNC_OT_open_editor(bpy.types.Operator):
    """Open the ScoreSync Editor — Sampler, FX Rack, and MIDI Mapping in one place"""
    bl_idname  = "scoresync.open_editor"
    bl_label   = "ScoreSync Editor"
    bl_options = {'REGISTER'}

    tab: bpy.props.EnumProperty(
        name="Tab",
        items=[
            ('SAMPLER', "Sampler",      "Visual Sampler pad banks and clip loader", 'NLA',    0),
            ('FX',      "FX Rack",      "Live MIDI-driven visual FX slots",         'SOUND',  1),
            ('MAPPING', "MIDI Mapping", "Map any MIDI control to any Blender property", 'DRIVER', 2),
        ],
        default='SAMPLER',
    )

    def invoke(self, context, event):
        self.tab = _ACTIVE_TAB[0]
        return context.window_manager.invoke_props_dialog(self, width=960)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = False

        row = layout.row(align=True)
        row.scale_y = 1.5
        row.prop(self, "tab", expand=True)
        layout.separator(factor=0.6)

        _ACTIVE_TAB[0] = self.tab

        scene = context.scene
        if self.tab == 'SAMPLER':
            _draw_sampler_editor(layout, scene)
        elif self.tab == 'FX':
            _draw_fx_editor(layout, scene)
        elif self.tab == 'MAPPING':
            _draw_mapping_editor(layout, scene)

    def execute(self, context):
        return {'FINISHED'}


# ── Registration ──────────────────────────────────────────────────────────────

editor_classes = (
    SCORESYNC_OT_open_editor,
)
