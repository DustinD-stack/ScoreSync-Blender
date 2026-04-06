# ScoreSync v2 — Complete Walkthrough

ScoreSync turns Blender into a live visual instrument: it syncs your
timeline to a DAW or hardware sequencer over MIDI, lets you map any
knob/pad to any Blender property, trigger video clips from a pad bank,
and drive strip or shader FX in real time.

---

## Contents

1. [Installation & First Launch](#1-installation--first-launch)
2. [Choosing Your Mode](#2-choosing-your-mode)
3. [Connection Setup](#3-connection-setup)
4. [Transport Sync — DAW → Blender](#4-transport-sync--daw--blender)
5. [Blender → DAW (Duplex)](#5-blender--daw-duplex)
6. [MIDI Mapping Layer](#6-midi-mapping-layer)
7. [Visual Sampler](#7-visual-sampler)
8. [FX Rack](#8-fx-rack)
9. [Video Sequence Editor Workflow](#9-video-sequence-editor-workflow)
10. [Node Editor / Shader FX Workflow](#10-node-editor--shader-fx-workflow)
11. [Live Performance Tips](#11-live-performance-tips)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Installation & First Launch

### Where the panels live

| Blender area | Tab | What you'll find |
|---|---|---|
| **3D Viewport** → N-panel | ScoreSync | Everything: connection, transport, mapping, sampler, FX rack |
| **Video Sequence Editor** → N-panel | ScoreSync | Strip FX inspector, VSE FX rack, sampler pads, transport |
| **Shader/Node Editor** → N-panel | ScoreSync | Material FX setup, MAT FX slots, MIDI mapping |

### Installing MIDI dependencies

ScoreSync bundles `mido` and `python-rtmidi` wheels inside the addon.

1. Open the **3D Viewport** N-panel → **ScoreSync** tab.
2. Under **Connection**, click **Install** next to "1. Dependencies".
3. Wait for the console to print `mido installed OK`.
4. Restart Blender once (required only the very first time).

### loopMIDI (Windows — FL Studio workflow)

Create two virtual ports in loopMIDI:

| Port name | Direction |
|---|---|
| `ScoreSync_F2B` | FL Studio → Blender |
| `ScoreSync_B2F` | Blender → FL Studio |

In FL Studio MIDI settings, enable **ScoreSync_F2B as Output** and
**ScoreSync_B2F as Input**. Do **not** enable F2B as an FL MIDI Input —
that creates a feedback loop.

---

## 2. Choosing Your Mode

The mode switcher button at the top of every ScoreSync panel controls
which features are visible.

### FL Studio Mode (default)

Full feature set. Shows:
- Export FL Script / Check FL Script / health indicator
- Duplex scrub-send controls
- Master mode AUTO/FL/BLENDER

Use this when working with FL Studio over loopMIDI.

### Hardware Mode

Click **Hardware Mode →** to switch. This:
- Hides all FL-specific UI (script export, health check)
- Sets Master = **FL** (hardware always leads)
- Sets Duplex = **Off**
- Enables **Manual BPM**

Use this with MPC, Elektron, Roland MC-series, or any standalone MIDI
sequencer. Click **← Switch to FL Mode** to revert.

---

## 3. Connection Setup

Open **3D Viewport → ScoreSync → Connection**.

### Step-by-step

**1. Install dependencies** — click **Install** (once ever).

**2. Refresh and pick ports** — click the refresh icon (↻), then:
- **In (F2B)**: the port your DAW/hardware sends on → Blender receives
- **Out (B2F)**: the port Blender sends on → DAW/hardware receives

Validation warnings appear immediately if you pick the wrong ports.

**3. Connect** — click **(Re)Connect**. The LED in the header updates:

| LED | Meaning |
|---|---|
| 🟢 clock OK | MIDI clock arriving — full sync active |
| 🟡 SPP only | Position data but no clock ticks |
| 🔴 idle | Nothing received — check ports |

**4. Check FL Script** *(FL mode only)* — click the **?** icon.
ScoreSync sends CC119=7 and waits for ACK CC119=100 from the FL script.
"FL Script: OK ✓" confirms end-to-end wiring.

**5. Master mode** — pick how transport authority is shared:

| Mode | Behaviour |
|---|---|
| **Auto** | FL leads while playing; Blender claims master on scrub/button-press then releases |
| **FL** | Blender only follows — never pushes transport |
| **Blender** | Blender always pushes — ignores incoming transport |

**Auto** is the recommended starting point for most workflows.

---

## 4. Transport Sync — DAW → Blender

Open **Transport** (sub-panel in View3D).

### Follow Clock

When **Follow Clock** is on, every MIDI Clock tick (24 per beat) advances
`frame_current`. ScoreSync uses an EMA BPM estimate from the tick
intervals — typically ±0.5 BPM of FL's actual tempo.

### Manual BPM Override

If the auto-estimate is noisy (e.g. external gear with uneven clock),
enable **Manual BPM** and type the exact BPM. All SPP ↔ frame
conversions use this value instead.

### Reset on Start

When enabled, a MIDI Start message jumps Blender to frame 0 before
playing. Disable this if you use Continue-style restarts mid-song.

### Latency compensation

In **Connection**, set **Latency (ms)** to delay applying incoming
messages — useful to absorb jitter from long USB chains or wireless MIDI.

---

## 5. Blender → DAW (Duplex)

Open **Master / Duplex** (sub-panel in View3D).

### Play / Stop / Locate

The **Transport** sub-panel has **Play**, **Stop**, and **Locate to
Frame** buttons that send MIDI Start/Stop/SPP to the DAW.

### Auto master switching

In **Auto** mode, Blender claims master when you:
- Click Play/Stop/Locate
- Scrub the timeline with the mouse

Blender holds master for **Hold (ms)** then yields back to the DAW.
The current holder is shown in Connection → "Now: FL (idle)" etc.

### Scrub send settings

| Setting | Effect |
|---|---|
| **Mode: Off** | DAW drives Blender only — no outbound SPP |
| **Mode: Assist** | Scrubbing Blender sends SPP bursts to nudge DAW |
| **Mode: Force** | Always send SPP (testing only) |
| **Hz** | How fast SPP bursts fire while scrubbing |
| **Debounce** | After scrub stops, wait this long then send a final exact locate |
| **Use MTC** | Send MTC quarter-frames during scrub instead of SPP |

---

## 6. MIDI Mapping Layer

Open **MIDI Mapping** (sub-panel in View3D, or compact view in VSE/Node
Editor sidebars).

The mapping layer lets any MIDI CC or Note On drive any Blender property
— object transforms, camera FOV, material inputs, custom props, anything
reachable by RNA path.

### Workflow

1. Click **Learn MIDI** — the button turns red with "Waiting…"
2. Move a knob, turn a fader, or hit a pad on your device.
3. ScoreSync captures the CC/Note — the status line shows what it got.
4. Click **Add** to create a new mapping slot.
5. Click the slot row to select it — the **inspector** opens below.
6. Click **← Assign Learned** to bind the captured MIDI to that slot.
7. Fill in the **Datablock** (e.g. `Camera`) and **Path** (e.g.
   `data.angle`) and set the **Min/Max** output range.
8. The **Live** readout at the bottom shows the current raw value and
   mapped output as you move the control.

### Preset templates

| Preset | What it adds |
|---|---|
| **Camera** | 6 mappings: Cam X/Y/Z, Rot X/Z, FOV |
| **Active Obj** | 5 mappings: Obj X/Y/Z, Scale, Rot Z |
| **Scene** | 2 mappings: frame_current, frame_start |

Presets auto-assign the next free CC numbers.

### Datablock name special values

| Name | Resolves to |
|---|---|
| `__ACTIVE__` | The currently active object |
| `__SCENE__` | The current scene |
| Any object/material name | That specific datablock |

### Example paths

```
location.x            Object X position
rotation_euler.z      Object Z rotation (radians)
data.angle            Camera field of view
scale.x               Object X scale
frame_current         Scene frame
```

### Export / Import

Save all mappings to JSON with **Export** for recall between sessions.
**Import** appends loaded mappings to the existing list.

---

## 7. Visual Sampler

Open **Visual Sampler** (sub-panel in View3D, or **Sampler Pads** in the
VSE sidebar).

The sampler maps MIDI notes to video clips or rendered frame ranges.
Pressing a pad either inserts a strip into the VSE or swaps a material's
image texture — or both.

### Creating banks and pads

1. Click **Add Bank** — a bank of 16 pads (4×4) is created.
2. Click a pad name in the grid to **select** it (highlighted).
3. The **Pad Inspector** opens below — set the note, channel, and output mode.

### Loading a sample

**Option A — external file**
In the pad inspector, click **Load File** and pick a video (mp4, mov,
mkv…) or image sequence (png, jpg, exr…).

**Option B — rendered frame range**
Set your scene's Start/End frame range, then click **Sample Timeline**.
ScoreSync records the frame range as a RENDER-type sample.

### Output modes

| Mode | What happens when triggered |
|---|---|
| **VSE** | Inserts/replaces a strip on the pad's VSE channel at `frame_current` |
| **Material** | Swaps the Image Texture node on the target object's active material |
| **Both** | Does both simultaneously |

### Velocity → Alpha

Enable on a pad to have harder MIDI hits produce a more opaque result
(blend_alpha for VSE, Principled Alpha for materials).

### Bank switching with Program Change

Enable **PC → Bank Switch** and pick the channel.  
MIDI Program Change 0 = Bank 0, PC 1 = Bank 1, and so on — regardless of
how many banks you have (clamped to the last bank).

Use this to follow song structure: one PC per song section.

### Export / Import banks

**Export Bank** saves the active bank's pad assignments (notes, channels,
sample IDs, output settings, colors) to JSON.  
**Import Bank** loads a saved bank into a new slot.

Note: sample files are referenced by path — keep them accessible.

---

## 8. FX Rack

Open **FX Rack** (sub-panel in View3D), **FX Rack** in the VSE sidebar
(VSE-type slots only), or **Material FX (MIDI)** in the Node Editor
sidebar (MAT-type slots only).

Each FX slot binds a MIDI control to a visual parameter.

### FX types

**VSE strips** (target = "VSE Channel #"):

| Type | What it drives |
|---|---|
| Opacity | Strip blend_alpha (fade in/out) |
| Bright Mult | Strip color_multiply |
| Saturation | Strip color_saturation |
| Brightness | BRIGHT_CONTRAST modifier — bright offset |
| Contrast | BRIGHT_CONTRAST modifier — contrast |
| Tint R/G/B | COLOR_BALANCE modifier — gain per channel |

**Materials** (target = Object name or "Active Mat"):

| Type | What it drives |
|---|---|
| Mat Opacity | Principled BSDF Alpha |
| Mat Emission | Principled Emission Strength |
| Mat Hue | ScoreSync HSV node — hue |
| Mat Saturation | ScoreSync HSV node — saturation |
| Mat Value | ScoreSync HSV node — value/brightness |
| Mat Brightness | ScoreSync BC node — bright offset |
| Mat Contrast | ScoreSync BC node — contrast |

### Trigger modes

| Mode | Behaviour |
|---|---|
| **CC** | Knob/fader — raw 0–127 maps linearly to Min→Max |
| **Momentary** | Note held = Max, Note released = Min (dead-man) |
| **Toggle** | Each Note On flips between Min and Max (latching) |
| **Flash** | Note On snaps to Max then decays back to Min over Decay (ms) |

### Adding a slot

1. Click **Add FX Slot**.
2. Select the new row — the inspector opens.
3. Set **FX Type**, **Target** (VSE channel number or object name),
   **Trigger Mode**, and value **Min/Max**.
4. Click the **REC** (🔴) icon on the row and move a MIDI control to
   bind it.
5. The **live bar** (`████░░░░`) and numeric value update in real time.

### Setup helpers

- **Setup Strip FX Modifiers** (VSE sidebar / FX Rack): adds
  BRIGHT_CONTRAST + COLOR_BALANCE modifiers to the active strip so
  Brightness, Contrast, and Tint slots can drive them.
- **Setup Material FX Chain** (Node Editor / FX Rack): inserts ScoreSync
  HSV and BrightContrast nodes between the Image Texture and Principled
  BSDF so all MAT_* slots work immediately.

---

## 9. Video Sequence Editor Workflow

Open the **VSE**, press **N** to open the sidebar, click **ScoreSync**.

### Panel layout

```
ScoreSync
  🟢 clock OK         Connected
  [▶ Play] [■ Stop] [⌚ Locate]

▼ Active Strip
  StripName  Ch 3  [100–250]
  ─ Blend ──────────────────
  Opacity  [========] 0.85
  Blend Type: ALPHA_OVER
  Bright Mult  [=====] 1.0
  Saturation   [=====] 1.0
  ─ Modifiers ──────────────
  Brightness  [==] 0.0    Contrast [==] 0.0
  Tint (Gain) [RGB picker]
  ─ MIDI FX on ch 3 ────────
  OPACITY       [████░░░░] 0.72
  BRIGHTNESS    [░░░░░░░░] 0.00

▼ FX Rack           (VSE slots only)
▼ Sampler Pads
▼ MIDI Mapping
```

### Active Strip Inspector

Select any strip in the VSE and its controls appear immediately:

- **Opacity** and **Blend Type** — adjust with sliders or let MIDI drive
- **Bright Mult** and **Saturation** — direct strip properties
- **Brightness/Contrast** and **Tint** — modifier-based (click "Setup
  Strip FX Modifiers" first if modifiers are missing)
- The "MIDI FX on this channel" section shows all FX slots targeting
  this channel with their live values

### Quick-add FX for the selected channel

If no slots target the selected strip's channel yet, three quick-add
buttons appear at the bottom of the Active Strip section:
**+ Opacity**, **+ Bright**, **+ Sat** — each creates a pre-configured
slot ready for MIDI learn.

### Live VJ workflow example

1. Load clips into sampler pads (VSE output mode, different VSE channels).
2. Add an Opacity FX slot per channel, bind each to a separate fader.
3. Add a Flash Opacity slot on all channels, bind to a pad for quick cuts.
4. During performance: faders blend the layers, pads trigger new clips,
   MIDI clock keeps Blender in lock-step with your track.

---

## 10. Node Editor / Shader FX Workflow

Open the **Shader/Node Editor** with a material active, press **N**,
click **ScoreSync**.

### Setup

1. Click **Setup Material FX Chain** — ScoreSync inserts:
   - `ScoreSync HSV` (Hue/Sat/Value node)
   - `ScoreSync BC` (Bright/Contrast node)
   between your Image Texture and Principled BSDF.
2. The panel shows live sliders for all three HSV values and both BC
   values — you can tweak them manually here even without MIDI.

### Adding MIDI-driven material FX

1. Open **Material FX (MIDI)** sub-panel.
2. Add a slot — pick a MAT_* type (e.g. **Mat Hue**).
3. Set Target to **Active Mat** or type an object name.
4. Click the REC icon and move a MIDI CC.
5. Adjust Min/Max range (e.g. Hue: 0.0–1.0 for full colour sweep).

### Typical live shader FX

| Control | FX type | Effect |
|---|---|---|
| Knob | Mat Hue | Sweeps the hue of the whole material |
| Fader | Mat Value | Dims / brightens the material |
| Pad (toggle) | Mat Opacity | Snap material to transparent / opaque |
| Pad (flash) | Mat Emission | Beat-reactive glow flash |

---

## 11. Live Performance Tips

### Recommended setup for live VJ

1. Use **Auto** master mode.
2. Enable **Reset on Start** so FL position and Blender always agree
   on bar 1 after a restart.
3. Set **Manual BPM** to your track's exact tempo for rock-solid SPP
   conversion.
4. Use **PC → Bank Switch** with one Program Change per song section —
   Intro/Verse/Hook/Break/Outro banks pre-loaded.

### Beat-reactive FX

- Set an Opacity or Emission **Flash** slot with **Decay = 200–400 ms**
  and bind to a kick-drum note or a pad you tap on beats.
- Multiple Flash slots on different channels with different decay times
  create layered reaction effects.

### Hardware-only setup (MPC / Elektron)

1. Click **Hardware Mode →**.
2. Set your hardware's MIDI output → Blender In port.
3. Use Program Change for bank switching, Note On for pads, CC for FX.
4. Master is locked to FL (i.e. your hardware — it's always the clock
   source).

### Saving your setup

- **Export Mappings** → saves all MIDI → property bindings.
- **Export Bank** (per bank) → saves pad assignments and sample IDs.
- Keep both JSON files next to your `.blend` file; the sample cache
  (`*_scoresync_cache.json`) is auto-saved alongside the .blend.
- Use **Diagnostics → Snapshot** to print full state to the console
  before a performance for a quick sanity check.

---

## 12. Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for the full guide.

Quick reference:

| Symptom | First thing to check |
|---|---|
| LED stays 🔴 | Wrong ports selected, or F2B enabled as FL Input creating a loop |
| "FL Script: not detected" | Run Export FL Script, placed in wrong folder, or DEBUG=True in script causing parse error |
| Blender frame drifts | Enable Manual BPM and set exact tempo |
| Sampler pad fires but no strip appears | Check pad output_mode = VSE, correct VSE channel, sample path valid |
| Material FX slot does nothing | Run Setup Material FX Chain in Node Editor |
| VSE strip FX slot does nothing | Run Setup Strip FX Modifiers in VSE sidebar |
| Note Off not releasing Momentary FX | Check your device sends Note Off (not Note On velocity 0) — some devices need this set in their MIDI config |
