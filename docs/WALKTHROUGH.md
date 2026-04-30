# ScoreSync v2.2 — Universal MIDI Action Mapping Walkthrough

## Overview

ScoreSync v2.2 extends the MIDI Mapping layer so any MIDI control can drive not only RNA properties (knobs, sliders) but also:

| Mode | What it does |
|---|---|
| **Property** | Continuously drive any Blender property (existing v2.0 behaviour) |
| **Operator** | Fire any Blender operator on a pad/button press |
| **Function** | Call a built-in ScoreSync action (camera switch, keyframe, sampler, etc.) |
| **Keyframe** | Insert a keyframe for a property on trigger |
| **Transport** | Play / Stop / Rewind / Next Marker, or scrub the timeline via CC |

---

## Quick Start

1. Open the **ScoreSync Editor** (`Open ScoreSync Editor` button in the N-panel).
2. Switch to the **MIDI Mapping** tab.
3. Click **Learn MIDI** and touch a pad, knob, or button on your controller.
4. Add a mapping with **Add** or apply a preset from the row at the top.
5. Select the mapping in the list, then set **Mode** in the inspector on the right.
6. Hit **Test Action** to verify without needing MIDI input.

---

## Examples

### 1. Knob → Camera Focal Length

| Field | Value |
|---|---|
| Mode | Property |
| MIDI Type | CC |
| Datablock Type | Object |
| Datablock Name | Camera |
| Property Path | data.lens |
| Min / Max | 20 / 100 |

Turn a knob on your controller to push-pull the camera lens between 20 mm and 100 mm in real time.

---

### 2. Pad → Play / Stop (Toggle)

Use the **Transport Buttons** preset, or manually:

| Field | Value |
|---|---|
| Mode | Transport |
| MIDI Type | Note On |
| Transport Action | Toggle Play/Stop |
| Fire On | Rising Edge |

One pad press plays; the next press stops. Works with any pad or button that sends Note On.

---

### 3. Pad → Insert Keyframe at Current Frame

Use the **Keyframe Tools** preset, or manually:

| Field | Value |
|---|---|
| Mode | Keyframe |
| MIDI Type | Note On |
| Datablock | (your object) |
| Property Path | location.x |
| Frame | Current Frame |
| Value | Keep Current Value |
| Fire On | Rising Edge |

Tap a pad to commit the current `location.x` value as a keyframe at the current timeline position — hands-free animation recording.

---

### 4. Knob → Material Roughness (via FL Studio routing)

In FL Studio, map a hardware knob to CC 7 on channel 1 of your loopMIDI port. Then in ScoreSync:

| Field | Value |
|---|---|
| Mode | Property |
| MIDI Type | CC  |
| Channel | 1 |
| CC Num | 7 |
| Datablock Type | Material |
| Datablock Name | (your material) |
| Property Path | roughness |
| Min / Max | 0.0 / 1.0 |

Twist the hardware knob in FL Studio → the material roughness updates live in Blender's viewport.

---

### 5. Button → Run an Operator

| Field | Value |
|---|---|
| Mode | Operator |
| MIDI Type | Note On |
| Operator ID | `view3d.view_all` |
| Props JSON | `{}` |
| Fire On | Rising Edge |

Press the pad → Blender frames all visible objects in the 3D view. Any operator callable from the Python console works here.

---

### 6. CC Scrub → Timeline Frame

| Field | Value |
|---|---|
| Mode | Transport |
| MIDI Type | CC |
| Transport Action | CC → Frame |
| Min / Max | 0 / 500 |

Move an expression pedal or fader to scrub the Blender timeline between frame 0 and 500. Combine with the **Locate to DAW** button to keep FL Studio in sync.

---

## New MIDI Types (v2.2)

| MIDI Type | Use |
|---|---|
| **Pitch Bend** | Pitch wheel — normalised 0-127 |
| **Aftertouch** | Channel pressure (all notes) |
| **Poly Touch** | Per-note pressure; Num = note number |
| **Program Chg** | Program change; triggers once per message |

---

## Banks

The four mapping banks (A/B/C/D) let you maintain independent sets of mappings for different instruments or scenes. Bind a MIDI button to each bank switch in the **MIDI Bank Switch Bindings** section, or click the bank letters at the top of the mapping list.

---

## Developer: Custom Python

Enable **Allow Custom Python in Mappings** in Scene Properties → ScoreSync.  
Each mapping then shows a one-line **Custom Python** field.  
Available variables: `bpy`, `context`, `scene`, `mapping`, `raw` (0-127), `value` (mapped float).

```python
# Example: set world background colour red on Note On
scene.world.node_tree.nodes['Background'].inputs[0].default_value = (raw/127, 0, 0, 1)
```

Only use this with trusted `.blend` files — `exec()` is used internally.
