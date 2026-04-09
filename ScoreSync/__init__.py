bl_info = {
    "name": "ScoreSync",
    "author": "Dustin Douglas",
    "version": (2, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D / VSE / Node Editor > Sidebar > ScoreSync",
    "description": "DAW/hardware sync, MIDI mapping, visual sampler, and FX rack for live performance.",
    "category": "System",
}

import bpy
import time

# ---- Imports ---------------------------------------------------------------
from .ui_panel import view3d_panel_classes
from .ui_editor import SCORESYNC_OT_open_editor, editor_classes

from .ui_vse import (
    SCORESYNC_PT_vse_main,
    SCORESYNC_PT_vse_strip,
    SCORESYNC_PT_vse_fx,
    SCORESYNC_PT_vse_sampler,
    SCORESYNC_PT_vse_mapping,
    vse_panel_classes,
)

from .ui_node import (
    SCORESYNC_PT_node_main,
    SCORESYNC_PT_node_fx,
    SCORESYNC_PT_node_mapping,
    node_panel_classes,
)

from .ops_connection import (
    items_midi_inputs,
    items_midi_outputs,
    SCORESYNC_OT_refresh_ports,
    SCORESYNC_OT_connect,
    SCORESYNC_OT_reconnect_now,  # v0.2.2
    scoresync_timer,             # optional: for explicit unregister
)

from .ops_diagnostics import (
    SCORESYNC_OT_list_ports,
    SCORESYNC_OT_send_test,
    SCORESYNC_OT_install_deps,
    SCORESYNC_OT_open_docs,
    SCORESYNC_OT_export_fl_script,
    SCORESYNC_OT_snapshot,
    SCORESYNC_OT_export_log,
    SCORESYNC_OT_apply_preset,
    SCORESYNC_OT_hardware_mode_apply,  # v2.0
    SCORESYNC_OT_fl_mode_apply,        # v2.0
)

from .ops_transport import (
    SCORESYNC_OT_play,
    SCORESYNC_OT_stop,
    SCORESYNC_OT_locate_to_timeline,
    SCORESYNC_OT_open_area,
)

from .ops_markers import (
    SCORESYNC_OT_drop_preset_marker,
    SCORESYNC_OT_jump_prev_marker,
    SCORESYNC_OT_jump_next_marker,
    SCORESYNC_OT_rename_markers_bar_beat,
)

from .ops_duplex import (  # v0.3.0
    SCORESYNC_OT_set_duplex_mode,
    scoresync_duplex_timer_register,
    scoresync_duplex_timer_unregister,
)
from .ops_health import SCORESYNC_OT_check_fl_script
from .prefs import ScoreSyncPreferences, get_prefs, get_last_ports

from .ops_mapping import (                         # v2.0 MIDI Mapping Layer
    ScoreSyncMapping,
    SCORESYNC_OT_mapping_learn_start,
    SCORESYNC_OT_mapping_learn_cancel,
    SCORESYNC_OT_mapping_assign,
    SCORESYNC_OT_mapping_select,
    SCORESYNC_OT_mapping_add,
    SCORESYNC_OT_mapping_remove,
    SCORESYNC_OT_mapping_apply_preset,
    SCORESYNC_OT_mapping_export,
    SCORESYNC_OT_mapping_import,
    apply_mappings_tick,
    ingest_midi_for_mapping,
    mapping_classes,
)

from .ops_sampler import (                         # v2.0 Visual Sampler
    SamplerPad,
    SamplerBank,
    SCORESYNC_OT_sampler_add_bank,
    SCORESYNC_OT_sampler_remove_bank,
    SCORESYNC_OT_sampler_select_pad,
    SCORESYNC_OT_sampler_set_active_bank,
    SCORESYNC_OT_sampler_sample_from_timeline,
    SCORESYNC_OT_sampler_load_file,
    SCORESYNC_OT_sampler_fire_pad,
    SCORESYNC_OT_sampler_export_bank,
    SCORESYNC_OT_sampler_import_bank,
    SCORESYNC_OT_sampler_reload_cache,
    ingest_note_for_sampler,
    ingest_pc_for_sampler,
    sampler_classes,
)

from .ops_fx import (                              # v2.0 FX Rack
    ScoreSyncFXSlot,
    SCORESYNC_OT_fx_setup_material,
    SCORESYNC_OT_fx_add_slot,
    SCORESYNC_OT_fx_remove_slot,
    SCORESYNC_OT_fx_select_slot,
    SCORESYNC_OT_fx_learn_start,
    SCORESYNC_OT_fx_learn_cancel,
    SCORESYNC_OT_fx_fire_slot,
    SCORESYNC_OT_vse_setup_strip,
    SCORESYNC_OT_fx_add_for_channel,
    apply_fx_tick,
    handle_note_on_fx,
    handle_note_off_fx,
    capture_fx_learn,
    fx_classes,
)



# ---- Properties ------------------------------------------------------------
def register_props():
    scene = bpy.types.Scene

    scene.scoresync_input_port = bpy.props.EnumProperty(
        name="MIDI In", description="DAW -> Blender", items=items_midi_inputs
    )
    scene.scoresync_output_port = bpy.props.EnumProperty(
        name="MIDI Out", description="Blender -> DAW", items=items_midi_outputs
    )

    scene.scoresync_status = bpy.props.StringProperty(
        name="Status", default="Not connected"
    )

    # QoL
    scene.scoresync_latency_ms = bpy.props.IntProperty(
        name="Latency (ms)", default=0, min=0, max=500,
        description="Delay handling of incoming transport to stabilize jitter"
    )
    scene.scoresync_autoreconnect = bpy.props.BoolProperty(
        name="Auto-reconnect", default=True,
        description="Try to re-open ports if they disappear"
    )
    scene.scoresync_follow_clock = bpy.props.BoolProperty(
        name="Follow MIDI Clock", default=True,
        description="When on, incoming MIDI Clock drives Blender’s frame"
    )
    scene.scoresync_reset_on_start = bpy.props.BoolProperty(
        name="Reset on Start", default=True,
        description="On MIDI Start, jump to frame 0 before playing"
    )

    # Musical utilities
    scene.scoresync_add_marker_every_bar = bpy.props.BoolProperty(
        name="Add marker every bar", default=False,
        description="Drop a Blender timeline marker at each bar boundary"
    )
    scene.scoresync_time_sig_n = bpy.props.IntProperty(
        name="Time Sig (beats/bar)", default=4, min=1, max=12
    )
    scene.scoresync_bpm_estimate = bpy.props.FloatProperty(
        name="BPM (est.)", default=0.0, precision=2
    )

    # Marker workflow (v0.2.1)
    scene.scoresync_marker_preset = bpy.props.EnumProperty(
        name="Marker Preset",
        items=[
            ("INTRO", "Intro", ""),
            ("VERSE", "Verse", ""),
            ("HOOK", "Hook/Chorus", ""),
            ("BRIDGE", "Bridge", ""),
            ("BREAK", "Break", ""),
            ("DROP", "Drop", ""),
            ("OUTRO", "Outro", ""),
        ],
        default="VERSE",
    )

    # Session LED (updated by timer)
    scene.scoresync_led_text = bpy.props.StringProperty(
        name="Sync LED", default="🔴 idle"
    )

    # Duplex Assist (v0.3.0)
    scene.scoresync_duplex_mode = bpy.props.EnumProperty(
        name="Duplex Mode",
        items=[
            ("OFF", "Off", "DAW → Blender only"),
            ("ASSIST", "Assist", "Blender can nudge DAW while you scrub or press buttons"),
            ("FORCE", "Force", "Always push (for testing)"),
        ],
        default="ASSIST",
    )
    scene.scoresync_duplex_rate_hz = bpy.props.IntProperty(
        name="Scrub send rate (Hz)", default=20, min=5, max=60,
        description="How often to send SPP bursts while scrubbing"
    )
    scene.scoresync_duplex_debounce_ms = bpy.props.IntProperty(
        name="Scrub debounce (ms)", default=140, min=40, max=500,
        description="After scrubbing stops, wait this long, then send final locate"
    )
    # v0.3.1 – MTC (optional while scrubbing)
    scene.scoresync_duplex_use_mtc = bpy.props.BoolProperty(
        name="Use MTC while scrubbing",
        default=False,
        description="When ON, send MTC Quarter-Frame bursts during scrubs (SPP is still used for final locate)"
    )
    scene.scoresync_duplex_mtc_fps = bpy.props.EnumProperty(
        name="MTC FPS",
        items=[
            ("24", "24 fps", ""),
            ("25", "25 fps", ""),
            ("30", "30 fps (non-drop)", ""),
        ],
        default="30",
        description="Timecode rate for MTC quarter-frame messages"
    )
    # FL script health
    scene.scoresync_script_ok = bpy.props.BoolProperty(name="FL Script OK", default=False)
    scene.scoresync_script_ok_ts = bpy.props.FloatProperty(name="FL Script OK TS", default=0.0)
    scene.scoresync_debug = bpy.props.BoolProperty(
        name="Debug",
        default=False,
        description="Print transport/clock debug to the System Console"
    )

    # Manual BPM override (v0.4.0)
    scene.scoresync_use_manual_bpm = bpy.props.BoolProperty(
        name="Manual BPM",
        default=False,
        description="Use the value below instead of the auto-detected BPM for SPP conversions",
    )
    scene.scoresync_manual_bpm = bpy.props.FloatProperty(
        name="BPM",
        default=120.0, min=20.0, max=999.0, precision=2,
        description="Manual BPM used for SPP ↔ frame conversion when Manual BPM is enabled",
    )

    # Auto master switching (v0.5.0)
    scene.scoresync_master_mode = bpy.props.EnumProperty(
        name="Master Mode",
        items=[
            ("AUTO",    "Auto",    "FL leads when playing; Blender leads when FL stopped and user scrubs"),
            ("FL",      "FL",      "FL Studio is always master — Blender only follows"),
            ("BLENDER", "Blender", "Blender is always master — pushes transport to FL"),
        ],
        default="AUTO",
        description="Which side controls transport",
    )
    scene.scoresync_master_hold_ms = bpy.props.IntProperty(
        name="Blender Hold (ms)",
        default=2000, min=200, max=10000,
        description="How long Blender keeps master after a scrub or button press, before FL can reclaim",
    )
    scene.scoresync_master_status = bpy.props.StringProperty(
        name="Master Status",
        default="FL (auto)",
    )

    # Hardware Mode (v2.0)
    scene.scoresync_hardware_mode = bpy.props.BoolProperty(
        name="Hardware Mode",
        default=False,
        description="Hide FL Studio-specific UI and optimise defaults for standalone hardware (MPC, Elektron, Roland MC…)",
    )

    # MIDI Mapping Layer (v2.0)
    scene.scoresync_mappings = bpy.props.CollectionProperty(type=ScoreSyncMapping)
    scene.scoresync_mapping_index = bpy.props.IntProperty(
        name="Active Mapping", default=0
    )
    scene.scoresync_mapping_learn_status = bpy.props.StringProperty(
        name="Learn Status", default=""
    )

    # Visual Sampler (v2.0)
    scene.scoresync_banks = bpy.props.CollectionProperty(type=SamplerBank)
    scene.scoresync_active_bank = bpy.props.IntProperty(
        name="Active Bank", default=0, min=0
    )
    scene.scoresync_active_pad = bpy.props.IntProperty(
        name="Active Pad", default=0, min=0
    )
    scene.scoresync_sampler_pc_switch = bpy.props.BoolProperty(
        name="PC → Bank Switch",
        default=False,
        description="MIDI Program Change messages switch the active bank (PC 0 → Bank 0, etc.)",
    )
    scene.scoresync_sampler_pc_channel = bpy.props.IntProperty(
        name="PC Channel",
        default=0, min=0, max=15,
        description="MIDI channel to listen for Program Change bank-switch messages (0 = ch 1)",
    )

    # ScoreSync Editor tab selection
    scene.scoresync_editor_tab = bpy.props.EnumProperty(
        name="Editor Tab",
        items=[
            ('SAMPLER',  "Sampler",      "Visual Sampler pad banks and clip loader", 'NLA',    0),
            ('FX',       "FX Rack",      "Live MIDI-driven visual FX slots",         'SOUND',  1),
            ('MAPPING',  "MIDI Mapping", "Map any MIDI control to any Blender property", 'DRIVER', 2),
        ],
        default='SAMPLER',
    )

    # FX Rack (v2.0)
    scene.scoresync_fx_slots = bpy.props.CollectionProperty(type=ScoreSyncFXSlot)
    scene.scoresync_fx_index = bpy.props.IntProperty(
        name="Active FX Slot", default=0, min=0
    )
    scene.scoresync_fx_learn_status = bpy.props.StringProperty(
        name="FX Learn Status", default=""
    )



def unregister_props():
    scene = bpy.types.Scene
    for attr in (
        "scoresync_input_port",
        "scoresync_output_port",
        "scoresync_status",
        "scoresync_latency_ms",
        "scoresync_autoreconnect",
        "scoresync_follow_clock",
        "scoresync_reset_on_start",
        "scoresync_add_marker_every_bar",
        "scoresync_time_sig_n",
        "scoresync_bpm_estimate",
        "scoresync_marker_preset",
        "scoresync_led_text",
        "scoresync_duplex_mode",
        "scoresync_duplex_rate_hz",
        "scoresync_duplex_debounce_ms",
        "scoresync_duplex_use_mtc",
        "scoresync_duplex_mtc_fps",
        "scoresync_script_ok",
        "scoresync_script_ok_ts",
        "scoresync_debug",
        "scoresync_use_manual_bpm",
        "scoresync_manual_bpm",
        "scoresync_master_mode",
        "scoresync_master_hold_ms",
        "scoresync_master_status",
        "scoresync_hardware_mode",
        "scoresync_mappings",
        "scoresync_mapping_index",
        "scoresync_mapping_learn_status",
        "scoresync_banks",
        "scoresync_active_bank",
        "scoresync_active_pad",
        "scoresync_sampler_pc_switch",
        "scoresync_sampler_pc_channel",
        "scoresync_editor_tab",
        "scoresync_fx_slots",
        "scoresync_fx_index",
        "scoresync_fx_learn_status",
    ):
        if hasattr(scene, attr):
            delattr(scene, attr)

# ---- Auto-restore -----------------------------------------------------------
def _auto_restore_ports():
    """Called once after register() and on load_post to reconnect last ports."""
    try:
        p = get_prefs()
        if p is None or not p.auto_connect:
            return
        in_name, out_name = get_last_ports()
        if not in_name and not out_name:
            return
        scene = bpy.context.scene
        if scene is None:
            return
        # Only set the props if the port names are still available
        try:
            from .ops_connection import _get_mido
            mido = _get_mido()
            if mido is None:
                return
            available_in  = set(mido.get_input_names())
            available_out = set(mido.get_output_names())
        except Exception:
            return
        changed = False
        if in_name in available_in:
            scene.scoresync_input_port = in_name
            changed = True
        if out_name in available_out:
            scene.scoresync_output_port = out_name
            changed = True
        if changed:
            bpy.ops.scoresync.connect()
            print(f"[ScoreSync] Auto-restored ports: In={in_name!r}  Out={out_name!r}")
    except Exception as e:
        print(f"[ScoreSync] Auto-restore failed: {e}")


def _auto_restore_timer():
    """Deferred one-shot timer so bpy.context is valid at startup."""
    _auto_restore_ports()
    return None  # returning None unregisters the timer


@bpy.app.handlers.persistent
def _load_post_handler(filepath):
    """Re-run auto-restore every time a .blend file loads."""
    # Give the scene a tick to settle before trying to set EnumProperty values
    try:
        bpy.app.timers.register(_auto_restore_ports, first_interval=0.5)
    except Exception:
        pass


# ---- Registration table ----------------------------------------------------
# PropertyGroup types (ScoreSyncMapping, SamplerPad, SamplerBank) MUST come
# before the scene CollectionProperty declarations in register_props(), so they
# are registered as a flat tuple first via the *_classes lists, then the rest.
classes = (
    # v2.0 PropertyGroups (must be first — used in CollectionProperty)
    ScoreSyncMapping,
    SamplerPad,
    SamplerBank,
    ScoreSyncFXSlot,

    ScoreSyncPreferences,

    # ---- Panels (View3D, VSE, Node Editor) ----
    *view3d_panel_classes,
    *vse_panel_classes,
    *node_panel_classes,

    # ---- ScoreSync Editor (unified popup) ----
    *editor_classes,

    SCORESYNC_OT_refresh_ports,
    SCORESYNC_OT_connect,
    SCORESYNC_OT_list_ports,
    SCORESYNC_OT_send_test,
    SCORESYNC_OT_install_deps,
    SCORESYNC_OT_open_docs,
    SCORESYNC_OT_play,
    SCORESYNC_OT_stop,
    SCORESYNC_OT_locate_to_timeline,
    SCORESYNC_OT_open_area,
    SCORESYNC_OT_drop_preset_marker,
    SCORESYNC_OT_jump_prev_marker,
    SCORESYNC_OT_jump_next_marker,
    SCORESYNC_OT_rename_markers_bar_beat,
    SCORESYNC_OT_reconnect_now,       # v0.2.2
    SCORESYNC_OT_set_duplex_mode,     # v0.3.0
    SCORESYNC_OT_check_fl_script,
    SCORESYNC_OT_export_fl_script,    # v0.3.2
    SCORESYNC_OT_snapshot,            # v0.6.0
    SCORESYNC_OT_export_log,          # v0.6.0
    SCORESYNC_OT_apply_preset,        # v0.7.0
    SCORESYNC_OT_hardware_mode_apply, # v2.0
    SCORESYNC_OT_fl_mode_apply,       # v2.0

    # v2.0 — MIDI Mapping Layer
    SCORESYNC_OT_mapping_learn_start,
    SCORESYNC_OT_mapping_learn_cancel,
    SCORESYNC_OT_mapping_assign,
    SCORESYNC_OT_mapping_select,
    SCORESYNC_OT_mapping_add,
    SCORESYNC_OT_mapping_remove,
    SCORESYNC_OT_mapping_apply_preset,
    SCORESYNC_OT_mapping_export,
    SCORESYNC_OT_mapping_import,

    # v2.0 — Visual Sampler
    SCORESYNC_OT_sampler_add_bank,
    SCORESYNC_OT_sampler_remove_bank,
    SCORESYNC_OT_sampler_select_pad,
    SCORESYNC_OT_sampler_set_active_bank,
    SCORESYNC_OT_sampler_sample_from_timeline,
    SCORESYNC_OT_sampler_load_file,
    SCORESYNC_OT_sampler_fire_pad,
    SCORESYNC_OT_sampler_export_bank,
    SCORESYNC_OT_sampler_import_bank,
    SCORESYNC_OT_sampler_reload_cache,

    # v2.0 — FX Rack
    SCORESYNC_OT_fx_setup_material,
    SCORESYNC_OT_fx_add_slot,
    SCORESYNC_OT_fx_remove_slot,
    SCORESYNC_OT_fx_select_slot,
    SCORESYNC_OT_fx_learn_start,
    SCORESYNC_OT_fx_learn_cancel,
    SCORESYNC_OT_fx_fire_slot,
    SCORESYNC_OT_vse_setup_strip,
    SCORESYNC_OT_fx_add_for_channel,
)

# ---- Add-on entry points ---------------------------------------------------
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    register_props()

    # Start duplex assist timer (v0.3.0)
    try:
        scoresync_duplex_timer_register()
    except Exception:
        pass

    # Auto-restore last ports after a short delay so bpy.context is ready (v0.7.0)
    try:
        bpy.app.timers.register(_auto_restore_timer, first_interval=1.0)
    except Exception:
        pass

    # Re-run auto-restore whenever a .blend file loads (v0.7.0)
    if _load_post_handler not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_load_post_handler)


def unregister():
    # Remove load_post handler
    if _load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post_handler)

    # Stop duplex assist timer FIRST (so callbacks don't run during teardown)
    try:
        scoresync_duplex_timer_unregister()
    except Exception:
        pass

    # Stop the core timer
    try:
        bpy.app.timers.unregister(scoresync_timer)
    except Exception:
        pass

    # Stop the one-shot restore timer if it hasn't fired yet
    try:
        bpy.app.timers.unregister(_auto_restore_timer)
    except Exception:
        pass

    unregister_props()

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
