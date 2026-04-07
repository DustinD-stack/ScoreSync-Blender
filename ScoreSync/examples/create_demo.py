"""
ScoreSync Demo Scene Builder
============================
Run this script from Blender's Scripting editor (with ScoreSync installed and
connected) to build the demo .blend file shipped with the addon.

Steps:
  1. Open Blender
  2. Switch one area to the Scripting editor
  3. Open this file
  4. Click Run Script

The script will pre-wire 13 MIDI mappings, a 4-pad Demo Bank, 5 FX slots,
and save the result alongside this file as scoresync_demo.blend.
"""

import bpy
import os

scene = bpy.context.scene

print("=" * 60)
print("ScoreSync Demo Builder — starting")
print("=" * 60)

# ── 1. MIDI Mapping presets ───────────────────────────────────────────────────
print("\n[1] Adding MIDI mapping presets...")
bpy.ops.scoresync.mapping_apply_preset(preset='CAMERA')
bpy.ops.scoresync.mapping_apply_preset(preset='ACTIVE_OBJECT')
bpy.ops.scoresync.mapping_apply_preset(preset='SCENE')
print(f"    {len(scene.scoresync_mappings)} mappings added")

# ── 2. Sample bank ────────────────────────────────────────────────────────────
print("\n[2] Creating Demo Bank...")
bpy.ops.scoresync.sampler_add_bank()
banks = scene.scoresync_banks

if banks:
    bank = banks[0]
    bank.name = "Demo Bank"

    pad_config = [
        ("Clip A — Ch1", 36, 1),   # C2
        ("Clip B — Ch2", 37, 2),   # D2
        ("Clip C — Ch3", 38, 3),   # E2
        ("Clip D — Ch4", 39, 4),   # F2
        ("Clip E — Ch5", 40, 5),   # G2
        ("Clip F — Ch6", 41, 6),   # A2
        ("Clip G — Ch7", 42, 7),   # B2
        ("Clip H — Ch8", 43, 8),   # C3
    ]

    for i, (label, note, ch) in enumerate(pad_config):
        if i >= len(bank.pads):
            break
        pad = bank.pads[i]
        pad.label       = label
        pad.note        = note
        pad.channel     = 1
        pad.output_mode = "VSE"
        pad.vse_channel = ch
        pad.enabled     = True

    print(f"    Bank '{bank.name}' — {len(bank.pads)} pads configured")
else:
    print("    WARNING: no bank created")

# ── 3. FX slots ───────────────────────────────────────────────────────────────
print("\n[3] Adding FX slots...")

# Opacity CC faders on VSE channels 1–4
for ch in range(1, 5):
    bpy.ops.scoresync.fx_add_slot()
    slot = scene.scoresync_fx_slots[-1]
    slot.label        = f"Opacity Ch{ch}"
    slot.fx_type      = "OPACITY"
    slot.trigger_mode = "CC"
    slot.target_mode  = "VSE_CHANNEL"
    slot.target_name  = str(ch)
    slot.midi_channel = 1
    slot.midi_num     = 10 + ch   # CC11–14 (mod-wheel area)
    slot.value_min    = 0.0
    slot.value_max    = 1.0
    slot.enabled      = True

# Flash Opacity — bind to pad C3 (note 48) for beat-reactive cuts
bpy.ops.scoresync.fx_add_slot()
slot = scene.scoresync_fx_slots[-1]
slot.label        = "Flash Cut"
slot.fx_type      = "OPACITY"
slot.trigger_mode = "FLASH"
slot.decay_ms     = 250
slot.target_mode  = "VSE_CHANNEL"
slot.target_name  = "1"
slot.midi_type    = "NOTE_ON"
slot.midi_channel = 1
slot.midi_num     = 48   # C3
slot.value_min    = 0.0
slot.value_max    = 1.0
slot.enabled      = True

# Saturation sweep — CC20
bpy.ops.scoresync.fx_add_slot()
slot = scene.scoresync_fx_slots[-1]
slot.label        = "Saturation All"
slot.fx_type      = "SATURATION"
slot.trigger_mode = "CC"
slot.target_mode  = "VSE_CHANNEL"
slot.target_name  = "1"
slot.midi_channel = 1
slot.midi_num     = 20
slot.value_min    = 0.0
slot.value_max    = 2.0
slot.enabled      = True

print(f"    {len(scene.scoresync_fx_slots)} FX slots added")

# ── 4. Scene defaults ─────────────────────────────────────────────────────────
print("\n[4] Setting scene defaults...")
scene.scoresync_master_mode        = "AUTO"
scene.scoresync_follow_clock       = True
scene.scoresync_reset_on_start     = True
scene.scoresync_sampler_pc_switch  = True
scene.scoresync_sampler_pc_channel = 1
scene.frame_start = 1
scene.frame_end   = 250
print("    Done")

# ── 5. Save ───────────────────────────────────────────────────────────────────
print("\n[5] Saving demo blend...")
demo_path = os.path.join(os.path.dirname(__file__), "scoresync_demo.blend")
bpy.ops.wm.save_as_mainfile(filepath=demo_path, copy=True)
print(f"    Saved: {demo_path}")

print("\n" + "=" * 60)
print("Demo scene built successfully!")
print(f"  Mappings : {len(scene.scoresync_mappings)}")
print(f"  Banks    : {len(scene.scoresync_banks)}")
print(f"  FX slots : {len(scene.scoresync_fx_slots)}")
print("=" * 60)
