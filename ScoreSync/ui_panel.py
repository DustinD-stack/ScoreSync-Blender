"""
ScoreSync v2 — ui_panel.py
View3D N-panel (sidebar → ScoreSync tab).

Organised as collapsible sub-panels:
  SCORESYNC_PT_main          Header: LED, status, mode switcher
  SCORESYNC_PT_connection    Setup wizard + port config
  SCORESYNC_PT_transport     DAW↔Blender transport + BPM
  SCORESYNC_PT_master        Master mode + duplex / scrub settings
  SCORESYNC_PT_mapping       MIDI mapping layer
  SCORESYNC_PT_sampler       Visual sampler (pad banks)
  SCORESYNC_PT_fx_v3d        FX rack
  SCORESYNC_PT_utilities     Markers + musical helpers
  SCORESYNC_PT_diagnostics   Diagnostics, presets, tools

Shared draw helpers (_draw_mapping, _draw_sampler, _draw_fx_rack) are
imported by ui_vse.py and ui_node.py for context-appropriate panels.
"""

import bpy
import time


# ── Tiny helpers ──────────────────────────────────────────────────────────────

def _hw(scene):
    return getattr(scene, "scoresync_hardware_mode", False)


# ── Shared draw helpers (also imported by ui_vse / ui_node) ──────────────────

def _draw_mapping(layout, scene, compact=False):
    """MIDI Mapping section.  compact=True hides the inspector."""
    from .ops_mapping import DEV_MAP, _midi_to_value

    # Learn controls
    row = layout.row(align=True)
    if DEV_MAP.learning:
        row.alert = True
        row.operator("scoresync.mapping_learn_cancel", icon='X',   text="Cancel Learn")
    else:
        row.operator("scoresync.mapping_learn_start",  icon='REC', text="Learn MIDI")

    status = getattr(scene, "scoresync_mapping_learn_status", "")
    if status:
        layout.label(text=status, icon='INFO')

    # Preset quick-add row
    row = layout.row(align=True)
    row.label(text="Presets:", icon='PRESET_NEW')
    for pid, lbl in (("CAMERA","Camera"), ("ACTIVE_OBJECT","Object"), ("SCENE","Scene")):
        op = row.operator("scoresync.mapping_apply_preset", text=lbl)
        op.preset = pid

    # Mapping list
    mappings       = getattr(scene, "scoresync_mappings", [])
    active_map_idx = getattr(scene, "scoresync_mapping_index", 0)

    if not mappings:
        layout.label(text="No mappings yet — click Learn or a preset.", icon='INFO')

    for i, m in enumerate(mappings):
        is_sel = (i == active_map_idx)
        row = layout.row(align=True)
        row.prop(m, "enabled", text="")
        op = row.operator("scoresync.mapping_select",
                          text=f"{m.label}  {m.midi_type} ch{m.channel} #{m.midi_num}",
                          depress=is_sel, emboss=is_sel)
        op.index = i
        op2 = row.operator("scoresync.mapping_assign", text="", icon='EYEDROPPER')
        op2.index = i
        op3 = row.operator("scoresync.mapping_remove", text="", icon='X')
        op3.index = i

    # Inspector (full view only)
    if not compact and mappings and active_map_idx < len(mappings):
        m    = mappings[active_map_idx]
        insp = layout.box()
        insp.label(text=f"Edit: {m.label}", icon='PROPERTIES')
        insp.prop(m, "label",   text="Name")
        insp.prop(m, "enabled", text="Enabled")
        row = insp.row(align=True)
        row.prop(m, "midi_type", text="")
        row.prop(m, "channel",   text="Ch")
        row.prop(m, "midi_num",  text="Num")
        op = insp.operator("scoresync.mapping_assign",
                           text="← Assign Learned", icon='EYEDROPPER')
        op.index = active_map_idx
        insp.separator(factor=0.4)
        insp.prop(m, "id_type",   text="Type")
        insp.prop(m, "id_name",   text="Datablock")
        insp.prop(m, "data_path", text="Path")
        row = insp.row(align=True)
        row.prop(m, "value_min", text="Min")
        row.prop(m, "value_max", text="Max")
        key = (m.midi_type, m.channel, m.midi_num)
        raw = DEV_MAP.last_val.get(key)
        if raw is not None:
            insp.label(
                text=f"Live: raw {raw}  →  {_midi_to_value(raw, m.value_min, m.value_max):.4f}",
                icon='DECORATE_ANIMATE',
            )

    row = layout.row(align=True)
    row.operator("scoresync.mapping_add",    icon='ADD',    text="Add")
    row.operator("scoresync.mapping_export", icon='EXPORT', text="Export")
    row.operator("scoresync.mapping_import", icon='IMPORT', text="Import")


def _draw_sampler(layout, scene, compact=False):
    """Visual Sampler section.  compact=True hides the pad inspector."""
    banks           = getattr(scene, "scoresync_banks",      [])
    active_bank_idx = getattr(scene, "scoresync_active_bank", 0)
    active_pad_idx  = getattr(scene, "scoresync_active_pad",  0)

    # Bank tabs
    if banks:
        row = layout.row(align=True)
        for i, bank in enumerate(banks):
            op = row.operator("scoresync.sampler_set_active_bank",
                              text=bank.name, depress=(i == active_bank_idx))
            op.index = i
    else:
        layout.label(text="No banks — click Add Bank.", icon='INFO')

    row = layout.row(align=True)
    row.operator("scoresync.sampler_add_bank",    icon='ADD',   text="Add Bank")
    row.operator("scoresync.sampler_remove_bank", icon='TRASH', text="Remove")

    # Pad grid
    if banks and active_bank_idx < len(banks):
        bank      = banks[active_bank_idx]
        pads      = bank.pads
        pad_count = len(pads)
        if pad_count:
            col = layout.column(align=True)
            for row_i in range(0, pad_count, 4):
                pad_row = col.row(align=True)
                for col_i in range(4):
                    idx = row_i + col_i
                    if idx >= pad_count:
                        pad_row.label(text="")
                        continue
                    pad    = pads[idx]
                    is_sel = (idx == active_pad_idx)
                    sub    = pad_row.column(align=True)
                    op_sel = sub.operator("scoresync.sampler_select_pad",
                                         text=pad.label or f"P{idx+1}",
                                         depress=is_sel, emboss=True)
                    op_sel.index = idx
                    op_fire = sub.operator("scoresync.sampler_fire_pad",
                                           text="", icon='PLAY')
                    op_fire.bank_index = active_bank_idx
                    op_fire.pad_index  = idx
                    op_fire.velocity   = 100

        # Pad inspector (full view only)
        if not compact and pad_count and active_pad_idx < pad_count:
            pad  = pads[active_pad_idx]
            insp = layout.box()
            insp.label(text=f"Pad {active_pad_idx+1}: {pad.label or '(unlabelled)'}",
                       icon='PROPERTIES')
            insp.prop(pad, "label",   text="Name")
            insp.prop(pad, "enabled", text="Enabled")
            row = insp.row(align=True)
            row.prop(pad, "note",    text="Note")
            row.prop(pad, "channel", text="Ch")
            insp.prop(pad, "output_mode", text="Output")
            if pad.output_mode in ("VSE", "BOTH"):
                insp.prop(pad, "vse_channel", text="VSE Channel")
            if pad.output_mode in ("MAT", "BOTH"):
                insp.prop(pad, "mat_target", text="Object")
            insp.prop(pad, "velocity_to_alpha", text="Velocity → Alpha")
            insp.prop(pad, "color", text="Color")

            from .ops_sampler import DEV_SAMPLER
            sample = DEV_SAMPLER.cache.get(pad.sample_id) if pad.sample_id else None
            if sample:
                insp.label(
                    text=f"{sample.get('label','?')}  "
                         f"({sample.get('frame_start')}→{sample.get('frame_end')})",
                    icon='SEQUENCE',
                )
            elif pad.sample_id:
                insp.label(text=f"ID {pad.sample_id} (not in cache)", icon='ERROR')
            else:
                insp.label(text="No sample assigned", icon='INFO')

            row = insp.row(align=True)
            op_l = row.operator("scoresync.sampler_load_file",
                                icon='FILEBROWSER', text="Load File")
            op_l.pad_index = active_pad_idx
            op_s = row.operator("scoresync.sampler_sample_from_timeline",
                                icon='RENDER_STILL', text="Sample Timeline")
            op_s.pad_index = active_pad_idx

    # PC → Bank switch
    row = layout.row(align=True)
    row.prop(scene, "scoresync_sampler_pc_switch", text="PC → Bank Switch")
    sub = row.row()
    sub.enabled = getattr(scene, "scoresync_sampler_pc_switch", False)
    sub.prop(scene, "scoresync_sampler_pc_channel", text="Ch")

    # Cache / IO
    row = layout.row(align=True)
    row.operator("scoresync.sampler_reload_cache", icon='FILE_REFRESH', text="Reload Cache")
    row.operator("scoresync.sampler_export_bank",  icon='EXPORT',       text="Export Bank")
    row.operator("scoresync.sampler_import_bank",  icon='IMPORT',       text="Import Bank")


def _draw_fx_rack(layout, scene, slot_filter=None, compact=False):
    """
    FX Rack section.
    slot_filter: None=all, 'VSE'=VSE types only, 'MAT'=material types only.
    compact=True hides the inspector.
    """
    from .ops_fx import DEV_FX
    from .ops_mapping import DEV_MAP

    _VSE_TYPES = {"OPACITY","COLOR_MULT","SATURATION","BRIGHTNESS","CONTRAST",
                  "TINT_R","TINT_G","TINT_B"}
    _MAT_TYPES = {"MAT_OPACITY","MAT_EMISSION","MAT_HUE","MAT_SAT",
                  "MAT_VALUE","MAT_BRIGHT","MAT_CONTRAST"}

    # Learn banner
    learn_status = getattr(scene, "scoresync_fx_learn_status", "")
    if DEV_FX.learning_slot >= 0:
        row = layout.row(align=True)
        row.alert = True
        row.label(text=learn_status or "Waiting for MIDI…", icon='REC')
        row.operator("scoresync.fx_learn_cancel", text="", icon='X')
    elif learn_status:
        layout.label(text=learn_status, icon='INFO')

    # Material / strip setup shortcuts
    if slot_filter in (None, 'MAT'):
        layout.operator("scoresync.fx_setup_material", icon='NODE_MATERIAL',
                        text="Setup Material FX Chain")
    if slot_filter in (None, 'VSE'):
        layout.operator("scoresync.vse_setup_strip", icon='SHADERFX',
                        text="Setup Strip FX Modifiers")

    # Slot list
    fx_slots  = getattr(scene, "scoresync_fx_slots", [])
    active_fx = getattr(scene, "scoresync_fx_index", 0)

    visible = [
        (i, slot) for i, slot in enumerate(fx_slots)
        if slot_filter is None
        or (slot_filter == 'VSE' and slot.fx_type in _VSE_TYPES)
        or (slot_filter == 'MAT' and slot.fx_type in _MAT_TYPES)
    ]

    if not visible:
        layout.label(
            text="No FX slots yet — click Add FX Slot.",
            icon='INFO',
        )

    for i, slot in visible:
        is_sel = (i == active_fx)
        live   = getattr(slot, "current_value", 0.0)
        vmin   = slot.value_min
        vmax   = slot.value_max
        rng    = (vmax - vmin) or 1.0
        pct    = max(0.0, min(1.0, (live - vmin) / rng))
        bar    = "█" * int(pct * 8) + "░" * (8 - int(pct * 8))

        row = layout.row(align=True)
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

    layout.operator("scoresync.fx_add_slot", icon='ADD', text="Add FX Slot")

    # Inspector (full view only)
    if not compact and fx_slots and active_fx < len(fx_slots):
        slot = fx_slots[active_fx]
        if (slot_filter is None
                or (slot_filter == 'VSE' and slot.fx_type in _VSE_TYPES)
                or (slot_filter == 'MAT' and slot.fx_type in _MAT_TYPES)):
            insp = layout.box()
            insp.label(text=f"Edit: {slot.label}", icon='PROPERTIES')
            insp.prop(slot, "label",       text="Name")
            insp.prop(slot, "enabled",     text="Enabled")
            insp.prop(slot, "fx_type",     text="FX Type")
            insp.separator(factor=0.4)
            insp.prop(slot, "target_mode", text="Target")
            if slot.target_mode == "VSE_CHANNEL":
                insp.prop(slot, "target_name", text="VSE Ch #")
            elif slot.target_mode == "OBJECT_MAT":
                insp.prop(slot, "target_name", text="Object")
            insp.separator(factor=0.4)
            insp.label(text="MIDI Binding:", icon='DRIVER')
            row = insp.row(align=True)
            row.prop(slot, "midi_type",    text="")
            row.prop(slot, "midi_channel", text="Ch")
            row.prop(slot, "midi_num",     text="Num")
            insp.prop(slot, "trigger_mode", text="Trigger")
            if slot.trigger_mode == "FLASH":
                insp.prop(slot, "decay_ms", text="Decay (ms)")
            insp.separator(factor=0.4)
            row = insp.row(align=True)
            row.prop(slot, "value_min", text="Min")
            row.prop(slot, "value_max", text="Max")
            key = (slot.midi_type, slot.midi_channel, slot.midi_num)
            raw = DEV_MAP.last_val.get(key)
            if raw is not None:
                insp.label(
                    text=f"Live MIDI: {raw}  →  {slot.current_value:.4f}",
                    icon='DECORATE_ANIMATE',
                )


# ════════════════════════════════════════════════════════════════════════════
# HEADER — always visible
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_main(bpy.types.Panel):
    bl_label       = "ScoreSync"
    bl_idname      = "SCORESYNC_PT_main"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"

    def draw(self, context):
        layout = self.layout
        scene  = context.scene
        hw     = _hw(scene)

        # LED + status on one row
        led    = getattr(scene, "scoresync_led_text", "🔴 idle")
        status = getattr(scene, "scoresync_status",   "Not connected")
        row = layout.row(align=True)
        row.label(text=led)
        row.label(text=status)

        # Mode toggle
        row = layout.row(align=True)
        if hw:
            row.operator("scoresync.fl_mode_apply",
                         icon='SEQUENCE', text="← Switch to FL Mode")
        else:
            row.operator("scoresync.hardware_mode_apply",
                         icon='PACKAGE',  text="Hardware Mode →")


# ════════════════════════════════════════════════════════════════════════════
# CONNECTION & SETUP WIZARD
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_connection(bpy.types.Panel):
    bl_label       = "Connection"
    bl_idname      = "SCORESYNC_PT_connection"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_main"

    def draw(self, context):
        layout = self.layout
        scene  = context.scene
        hw     = _hw(scene)

        # Step 1 — install
        row = layout.row(align=True)
        row.label(text="1. Dependencies", icon='IMPORT')
        row.operator("scoresync.install_deps", text="Install")

        # Step 2 — ports
        layout.separator(factor=0.3)
        row = layout.row(align=True)
        row.label(text="2. Ports", icon='PLUGIN')
        row.operator("scoresync.refresh_ports", text="", icon='FILE_REFRESH')
        col = layout.column(align=True)
        col.prop(scene, "scoresync_input_port",  text="In  (F2B)")
        col.prop(scene, "scoresync_output_port", text="Out (B2F)")

        # Validation warnings
        in_n  = getattr(scene, "scoresync_input_port",  "NONE") or "NONE"
        out_n = getattr(scene, "scoresync_output_port", "NONE") or "NONE"
        if in_n != "NONE" and in_n == out_n:
            b = layout.box(); b.alert = True
            b.label(text="In = Out — feedback loop!", icon='ERROR')
        if "B2F" in in_n.upper() or "F2B" in out_n.upper():
            b = layout.box(); b.alert = True
            b.label(text="Ports look swapped — In=F2B, Out=B2F", icon='ERROR')
        if "F2B" in in_n.upper():
            b = layout.box()
            b.label(text="Reminder: disable F2B as FL MIDI input", icon='INFO')
        if in_n == "NONE" and out_n == "NONE":
            b = layout.box()
            b.label(text="No ports — create in loopMIDI:", icon='INFO')
            b.label(text="  ScoreSync_F2B  /  ScoreSync_B2F")

        # Step 3 — connect
        layout.separator(factor=0.3)
        row = layout.row(align=True)
        row.label(text="3. Connect", icon='PLAY')
        row = layout.row(align=True)
        row.operator("scoresync.connect",      icon='PLAY',         text="(Re)Connect")
        row.operator("scoresync.reconnect_now", text="",            icon='FILE_REFRESH')
        if not hw:
            row.operator("scoresync.check_fl_script", text="",     icon='QUESTION')

        if not hw:
            ok = (scene.scoresync_script_ok
                  and (time.time() - scene.scoresync_script_ok_ts) < 10.0)
            layout.label(
                text="FL Script: " + ("OK ✓" if ok else "not detected"),
                icon='CHECKMARK' if ok else 'X',
            )

        # Step 4 — master mode
        layout.separator(factor=0.3)
        col = layout.column(align=True)
        col.label(text="4. Master Mode", icon='DECORATE_ANIMATE')
        col.prop(scene, "scoresync_master_mode", text="")
        ms = getattr(scene, "scoresync_master_status", "")
        if ms:
            col.label(text=ms, icon='RADIOBUT_ON')

        # QoL
        layout.separator(factor=0.3)
        row = layout.row(align=True)
        row.prop(scene, "scoresync_latency_ms",    text="Latency (ms)")
        row.prop(scene, "scoresync_autoreconnect", text="Auto-reconnect")


# ════════════════════════════════════════════════════════════════════════════
# TRANSPORT
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_transport(bpy.types.Panel):
    bl_label       = "Transport"
    bl_idname      = "SCORESYNC_PT_transport"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_main"
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene  = context.scene

        # DAW → Blender
        col = layout.column(align=True)
        col.label(text="DAW → Blender", icon='SEQUENCE')
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

        layout.separator(factor=0.5)

        # Blender → DAW
        col = layout.column(align=True)
        col.label(text="Blender → DAW", icon='PLAY')
        row = col.row(align=True)
        row.operator("scoresync.tx_play",  icon='PLAY',  text="Play")
        row.operator("scoresync.tx_stop",  icon='PAUSE', text="Stop")
        col.operator("scoresync.tx_locate_to_timeline",
                     icon='TIME', text="Locate to Frame")


# ════════════════════════════════════════════════════════════════════════════
# MASTER / DUPLEX
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_master(bpy.types.Panel):
    bl_label       = "Master / Duplex"
    bl_idname      = "SCORESYNC_PT_master"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_main"
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene  = context.scene

        col = layout.column(align=True)
        col.prop(scene, "scoresync_master_mode",    text="Master")
        col.prop(scene, "scoresync_master_hold_ms", text="Hold (ms)")
        ms = getattr(scene, "scoresync_master_status", "")
        if ms:
            col.label(text=ms, icon='DECORATE_ANIMATE')

        layout.separator(factor=0.5)
        col = layout.column(align=True)
        col.label(text="Scrub Send (Duplex)", icon='ARROW_LEFTRIGHT')
        col.prop(scene, "scoresync_duplex_mode", text="Mode")
        row = col.row(align=True)
        row.prop(scene, "scoresync_duplex_rate_hz",     text="Hz")
        row.prop(scene, "scoresync_duplex_debounce_ms", text="Debounce")
        row = col.row(align=True)
        row.prop(scene, "scoresync_duplex_use_mtc")
        sub = row.row()
        sub.enabled = scene.scoresync_duplex_use_mtc
        sub.prop(scene, "scoresync_duplex_mtc_fps", text="")


# ════════════════════════════════════════════════════════════════════════════
# MIDI MAPPING
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_mapping(bpy.types.Panel):
    bl_label       = "MIDI Mapping"
    bl_idname      = "SCORESYNC_PT_mapping"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_main"
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        _draw_mapping(self.layout, context.scene)


# ════════════════════════════════════════════════════════════════════════════
# VISUAL SAMPLER
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_sampler(bpy.types.Panel):
    bl_label       = "Visual Sampler"
    bl_idname      = "SCORESYNC_PT_sampler"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_main"
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        _draw_sampler(self.layout, context.scene)


# ════════════════════════════════════════════════════════════════════════════
# FX RACK (View3D — all types)
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_fx_v3d(bpy.types.Panel):
    bl_label       = "FX Rack"
    bl_idname      = "SCORESYNC_PT_fx_v3d"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_main"
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        _draw_fx_rack(self.layout, context.scene)


# ════════════════════════════════════════════════════════════════════════════
# MARKERS & MUSICAL UTILITIES
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_utilities(bpy.types.Panel):
    bl_label       = "Markers & Musical"
    bl_idname      = "SCORESYNC_PT_utilities"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_main"
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene  = context.scene

        col = layout.column(align=True)
        col.label(text="Musical", icon='MUSIC')
        row = col.row(align=True)
        row.prop(scene, "scoresync_add_marker_every_bar", text="Bar Markers")
        row.prop(scene, "scoresync_time_sig_n", text="Beats/Bar")

        layout.separator(factor=0.5)
        col = layout.column(align=True)
        col.label(text="Markers", icon='MARKER_HLT')
        row = col.row(align=True)
        row.prop(scene, "scoresync_marker_preset", text="")
        row.operator("scoresync.drop_preset_marker", icon='MARKER_HLT', text="Drop")
        row = col.row(align=True)
        row.operator("scoresync.jump_prev_marker", icon='TRIA_LEFT',  text="Prev")
        row.operator("scoresync.jump_next_marker", icon='TRIA_RIGHT', text="Next")
        col.operator("scoresync.rename_markers_bar_beat",
                     icon='SORTSIZE', text="Rename → Bar:Beat")


# ════════════════════════════════════════════════════════════════════════════
# DIAGNOSTICS, PRESETS & TOOLS
# ════════════════════════════════════════════════════════════════════════════

class SCORESYNC_PT_diagnostics(bpy.types.Panel):
    bl_label       = "Diagnostics & Tools"
    bl_idname      = "SCORESYNC_PT_diagnostics"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "ScoreSync"
    bl_parent_id   = "SCORESYNC_PT_main"
    bl_options     = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene  = context.scene
        hw     = _hw(scene)

        # Presets
        col = layout.column(align=True)
        col.label(text="Quick Presets", icon='PRESET')
        row = col.row(align=True)
        for pid, lbl in (("FL_FOLLOW","FL Follow"),
                         ("BLENDER_ASSIST","Assist"),
                         ("AUTO_MASTER","Auto")):
            op = row.operator("scoresync.apply_preset", text=lbl)
            op.preset = pid

        layout.separator(factor=0.5)

        # Diagnostics
        col = layout.column(align=True)
        col.label(text="Diagnostics", icon='INFO')
        col.prop(scene, "scoresync_debug", text="Debug Logging")
        row = col.row(align=True)
        row.operator("scoresync.list_ports", icon='VIEWZOOM',         text="List Ports")
        row.operator("scoresync.send_test",  icon='OUTLINER_OB_LIGHT', text="Test CC")
        row = col.row(align=True)
        row.operator("scoresync.snapshot",   icon='TEXT',   text="Snapshot")
        row.operator("scoresync.export_log", icon='EXPORT', text="Export Log")

        layout.separator(factor=0.5)

        # Tools
        col = layout.column(align=True)
        col.label(text="Tools", icon='CONSOLE')
        if not hw:
            col.operator("scoresync.export_fl_script", icon='EXPORT',
                         text="Export FL Script")
        col.operator("scoresync.open_docs", icon='HELP', text="Open Docs")


# ── Registration list (all View3D panels) ─────────────────────────────────────

view3d_panel_classes = (
    SCORESYNC_PT_main,
    SCORESYNC_PT_connection,
    SCORESYNC_PT_transport,
    SCORESYNC_PT_master,
    SCORESYNC_PT_mapping,
    SCORESYNC_PT_sampler,
    SCORESYNC_PT_fx_v3d,
    SCORESYNC_PT_utilities,
    SCORESYNC_PT_diagnostics,
)
