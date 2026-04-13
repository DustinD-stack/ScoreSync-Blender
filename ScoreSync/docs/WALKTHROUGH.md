# ScoreSync — Complete Walkthrough

ScoreSync turns Blender into a live visual instrument. It syncs your timeline to any DAW or hardware sequencer over MIDI, lets you map any knob or pad to any Blender property, trigger video clips from a pad bank, drive strip and shader FX in real time, and switch complete sets of mappings between banks mid-performance.

---

## Contents

1. [Installation & First Launch](#1-installation--first-launch)
2. [Choosing Your Mode](#2-choosing-your-mode)
3. [Connection Setup](#3-connection-setup)
4. [Transport Sync — DAW → Blender](#4-transport-sync--daw--blender)
5. [Blender → DAW (Duplex)](#5-blender--daw-duplex)
6. [MIDI Mapping Layer](#6-midi-mapping-layer)
7. [Mapping Banks — A/B/C/D](#7-mapping-banks--abcd)
8. [Visual Sampler](#8-visual-sampler)
9. [FX Rack](#9-fx-rack)
10. [Video Sequence Editor Workflow](#10-video-sequence-editor-workflow)
11. [Node Editor / Shader FX Workflow](#11-node-editor--shader-fx-workflow)
12. [Live Performance Tips](#12-live-performance-tips)
13. [Troubleshooting](#13-troubleshooting)

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
2. Under **Connection**, click **Install deps**.
3. Wait for the console to print `mido installed OK`.
4. Restart Blender once (required only the very first time).

### loopMIDI (Windows)

Create two virtual ports in loopMIDI:

| Port name | Direction |
|---|---|
| `ScoreSync_F2B` | DAW / Hardware → Blender |
| `ScoreSync_B2F` | Blender → DAW / Hardware |

In your DAW's MIDI settings, route clock output to `ScoreSync_F2B`.
Do **not** enable `ScoreSync_F2B` as a DAW MIDI Input — that creates a feedback loop.

---

## 2. Choosing Your Mode

The mode switcher at the top of every ScoreSync panel controls which features are visible.

### DAW Mode (default)

Full feature set. Shows:
- Export DAW Script / Check DAW Script / health indicator (FL Studio)
- Duplex scrub-send controls
- Master mode AUTO / DAW / BLENDER

Use this when working with a DAW over loopMIDI.

### Hardware Mode

Click **Hardware Mode →** to switch. This:
- Hides DAW-specific UI (script export, health check)
- Sets Master = **DAW** (hardware always leads)
- Sets Duplex = **Off**
- Enables **Manual BPM**

Use this with MPC, Elektron, Roland MC-series, or any standalone MIDI sequencer. Click **← DAW Mode** to revert.

---

## 3. Connection Setup

Open **3D Viewport → ScoreSync → Connection**.

### Step-by-step

**1. Install dependencies** — click **Install deps** (once ever).

**2. Refresh and pick ports** — click the refresh icon (↻), then:
- **In (F2B)**: the port your DAW/hardware sends clock on → Blender receives
- **Out (B2F)**: the port Blender sends on → DAW/hardware receives

Validation warnings appear immediately if you pick the wrong ports.

**3. Connect** — click **(Re)Connect**. The LED in the header updates:

| LED | Meaning |
|---|---|
| 🟢 clock OK | MIDI clock arriving — full sync active |
| 🟡 SPP only | Position data but no clock ticks |
| 🔴 idle | Nothing received — check ports |

**4. Check DAW Script** *(FL Studio only)* — click the **?** icon.
ScoreSync sends a probe and waits for an ACK from the FL script.
"DAW Script: OK ✓" confirms end-to-end wiring.

**5. Master mode** — pick how transport authority is shared:

| Mode | Behaviour |
|---|---|
| **Auto** | DAW leads while playing; Blender claims master on scrub/button-press then releases |
| **DAW** | Blender only follows — never pushes transport |
| **Blender** | Blender always pushes — ignores incoming transport |

**Auto** is the recommended starting point.

---

## 4. Transport Sync — DAW → Blender

Open **Transport** in the View3D panel.

### Follow Clock

When **Follow Clock** is on, every MIDI Clock tick (24 per beat) advances
`frame_current`. ScoreSync uses an EMA BPM estimate from the tick intervals.

### Manual BPM Override

If the auto-estimate is noisy (external gear with uneven clock), enable **Manual BPM** and type the exact BPM. All SPP ↔ frame conversions use this value instead.

### Reset on Start

When enabled, a MIDI Start message jumps Blender to frame 0 before playing.
Disable this if you use Continue-style restarts mid-song.

### Latency compensation

Set **Latency (ms)** to delay applying incoming messages — useful to absorb jitter from long USB chains or wireless MIDI.

---

## 5. Blender → DAW (Duplex)

Open **Master / Duplex** in the View3D panel.

### Play / Stop / Locate

The **Transport** sub-panel has **Play**, **Stop**, and **Locate to Frame** buttons that send MIDI Start/Stop/SPP to the DAW.

### Auto master switching

In **Auto** mode, Blender claims master when you click Play/Stop/Locate or scrub the timeline.
Blender holds master for **Hold (ms)** then yields back to the DAW.

### Scrub send settings

| Setting | Effect |
|---|---|
| **Mode: Off** | DAW drives Blender only — no outbound SPP |
| **Mode: Assist** | Scrubbing Blender sends SPP bursts to nudge the DAW |
| **Mode: Force** | Always send SPP (testing only) |
| **Hz** | How fast SPP bursts fire while scrubbing |
| **Debounce** | After scrub stops, wait this long then send a final exact locate |
| **Use MTC** | Send MTC quarter-frames during scrub instead of SPP |

---

## 6. MIDI Mapping Layer

Open **MIDI Mapping** in the View3D panel, or open the full **ScoreSync Editor** (Mapping tab) for the complete interface.

The mapping layer lets any MIDI CC or Note On drive any Blender property — object transforms, camera FOV, material inputs, custom props, anything reachable by RNA path.

### Workflow

1. Click **Learn MIDI** — the button turns red with "Listening…"
2. Move a knob, fader, or hit a pad on your device.
3. ScoreSync captures the CC/Note — the status line confirms what it got.
4. Click **Add** to create a new mapping slot.
5. Click the slot row to select it — the **inspector** opens on the right.
6. Click **← Assign from Learn** to bind the captured MIDI to that slot.
7. Set the **Datablock** (e.g. `Camera`) and click the magnifier **🔍** next to Path to browse all available RNA paths.
8. Set **Min/Max** output range.
9. The **Live** readout shows the current raw value and mapped output as you move the control.

### Preset templates

| Preset | What it adds |
|---|---|
| **Camera** | 6 mappings: Cam X/Y/Z, Rot X/Z, FOV |
| **Active Obj** | 5 mappings: Obj X/Y/Z, Scale, Rot Z |
| **Scene** | 2 mappings: frame_current, frame_start |

### Datablock name special values

| Name | Resolves to |
|---|---|
| `__ACTIVE__` | The currently active object in the viewport |
| `__SCENE__` | The current scene |

### Path picker

Click the **magnifier icon 🔍** next to any mapping's Path field to open a searchable browser. It lists curated common paths (location, rotation, scale, camera, light, materials) plus a live scan of the actual datablock's RNA properties. Type to filter — e.g. "energy" for lights, "angle" for camera FOV.

### Export / Import

Save all mappings to JSON with **Export** for recall between sessions.
**Import** appends loaded mappings to the existing list.

---

## 7. Mapping Banks — A/B/C/D

Got a small controller with only 8 knobs? Banks let the same physical controls run completely different sets of parameters. Switch banks with a button press — your whole control surface changes instantly.

### How banks work

- Every mapping belongs to one bank (A, B, C, or D).
- Only the **active bank's** mappings respond to MIDI. Other banks are completely silent until switched.
- Banks A/B/C/D selector sits at the top of the Mapping tab.

### Assigning mappings to banks

In the mapping **inspector** (select a row on the left), the **Bank** field sets which bank this mapping lives in. All new mappings default to Bank A.

### Switching banks live

**From the UI:** click A/B/C/D at the top of the Mapping tab.

**From MIDI:** use the Bank Switch Bindings section (below the A/B/C/D buttons).
Click **Bind MIDI** next to a bank, press any button or pad on your controller,
and that button now switches to that bank during performance.

### Example — 8-knob controller, 4 scenes

| Bank | Knobs control |
|---|---|
| A | Camera: X, Y, Z, FOV |
| B | Active Object: X, Y, Z, Scale |
| C | Lighting: Energy, Spot Size, Shadow, Radius |
| D | Scene: Frame, BPM, Render Scale, World Strength |

Bind four pads on your controller to switch A/B/C/D. Same knobs, four times the parameters.

---

## 8. Visual Sampler

Open **Visual Sampler** in the View3D panel, or **Sampler Pads** in the VSE sidebar.

The sampler maps MIDI notes to video clips or rendered frame ranges.
Pressing a pad inserts a strip into the VSE, swaps a material's image texture, or both.

### Creating banks and pads

1. Click **Add Bank** — a bank of 16 pads (4×4) is created.
2. Click a pad to select it.
3. The **Pad Inspector** opens — set the note, channel, and output mode.

### Loading a sample

**External file:** click **Load File** and pick a video or image sequence.

**Rendered range:** set your scene's Start/End frames, then click **Sample Timeline**.

### Output modes

| Mode | What happens on trigger |
|---|---|
| **VSE** | Inserts/replaces a strip on the pad's VSE channel at `frame_current` |
| **Material** | Swaps the Image Texture node on the active material |
| **Both** | Does both simultaneously |

### Bank switching with Program Change

Enable **PC → Bank Switch** and pick the channel.
MIDI Program Change 0 = Bank 0, PC 1 = Bank 1, and so on.

---

## 9. FX Rack

Open **FX Rack** in the View3D panel, the VSE sidebar, or the Node Editor sidebar.

Each FX slot binds a MIDI control to a visual parameter.

### FX types

**VSE strips:** Opacity, Bright Mult, Saturation, Brightness, Contrast, Tint R/G/B

**Materials:** Mat Opacity, Mat Emission, Mat Hue, Mat Saturation, Mat Value, Mat Brightness, Mat Contrast

### Trigger modes

| Mode | Behaviour |
|---|---|
| **CC** | Knob/fader — 0–127 maps linearly to Min→Max |
| **Momentary** | Held = Max, released = Min |
| **Toggle** | Each press flips between Min and Max |
| **Flash** | Snaps to Max then decays back to Min over Decay ms |

### Adding a slot

1. Click **Add FX Slot**.
2. Select the new row — inspector opens.
3. Set FX Type, Target, Trigger Mode, and Min/Max.
4. Click the REC icon and move a MIDI control to bind it.
5. The live bar updates in real time.

---

## 10. Video Sequence Editor Workflow

Open the **VSE**, press **N** → **ScoreSync** tab.

Select any strip in the VSE and its controls appear immediately in the Active Strip inspector: Opacity, Blend Type, Brightness/Contrast, Tint, and a live view of all FX slots targeting that channel.

### Quick-add FX

If no slots target the selected strip's channel yet, **+ Opacity**, **+ Bright**, **+ Sat** buttons appear — each creates a pre-configured slot ready for MIDI learn.

---

## 11. Node Editor / Shader FX Workflow

Open the **Shader/Node Editor** with a material active, press **N** → **ScoreSync**.

1. Click **Setup Material FX Chain** — ScoreSync inserts an HSV and BrightContrast node between your Image Texture and Principled BSDF.
2. Add Material FX slots (Mat Hue, Mat Saturation, Mat Value, etc.) and bind them to MIDI CCs.

---

## 12. Live Performance Tips

### Beat-reactive FX

Set a **Flash** slot with Decay = 200–400 ms and bind it to a kick-drum note or a pad you tap on the beat. Multiple Flash slots on different channels with different decay times create layered beat-reaction effects.

### Mapping banks for song sections

Prepare one bank per song section (Intro, Verse, Hook, Outro). Bind each to a pad button. Switch banks as the song moves — your whole control surface reconfigures instantly with no menu touching.

### Hardware-only setup (MPC / Elektron)

1. Click **Hardware Mode →**.
2. Set your hardware's MIDI output → Blender In port.
3. Use Program Change for sampler bank switching, Note On for pads, CC for FX and mappings.

### Saving your setup

- **Export Mappings** — saves all MIDI → property bindings as JSON.
- **Export Bank** (per bank) — saves pad assignments and sample IDs.
- **Diagnostics → Snapshot** — prints full state to the console before a performance for a quick sanity check.

---

## 13. Troubleshooting

See [TROUBLESHOOTING.md](../../docs/TROUBLESHOOTING.md) for the full guide.

Quick reference:

| Symptom | First thing to check |
|---|---|
| LED stays 🔴 | Wrong ports selected, or `ScoreSync_F2B` enabled as DAW Input creating a feedback loop |
| "DAW Script: not detected" | Export DAW Script, place in correct folder, reload script in DAW |
| Blender frame drifts | Enable Manual BPM and enter exact tempo |
| MIDI learn captures nothing | DAW may hold controller port exclusively — close DAW or use MIDI pass-through |
| Bank switches don't fire | Re-learn the binding — check it shows the MIDI type/number |
| Sampler pad fires but no strip appears | Check pad output_mode = VSE, correct VSE channel, sample path valid |
| Material FX slot does nothing | Run Setup Material FX Chain in Node Editor |
| VSE strip FX slot does nothing | Run Setup Strip FX Modifiers in VSE sidebar |
