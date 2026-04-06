# ScoreSync

### Turn Blender into a Live Visual Instrument

**ScoreSync** bridges your DAW and Blender in real time — lock your timeline to the beat, shred visual FX with MIDI knobs and pads, trigger video clips like an MPC, and paint shaders live with your controller. Whether you're VJing a concert, scoring a short film, or building a reactive music video, ScoreSync makes Blender feel like it was always part of your rig.

> **Works with FL Studio, any DAW, MPC, Elektron, Roland MC-series, or standalone MIDI hardware.**

---

## What It Does

### Beat-Locked Timeline Sync
Your Blender playhead follows the DAW — perfectly. MIDI Clock, Start/Stop/Continue, and Song Position Pointer keep everything in frame-accurate lockstep. Scrub the DAW and Blender follows. Press Play in DAW and Blender rolls. It just works.

### Live FX Rack — MIDI-Driven Visual Control
Map any knob, fader, or pad to any visual parameter. Fourteen built-in FX types let you tear through the mix:

| FX | What It Hits |
|---|---|
| Opacity / Bright Mult / Saturation | VSE strip blend controls |
| Brightness / Contrast | BRIGHT_CONTRAST modifier |
| Tint R / Tint G / Tint B | Per-channel COLOR_BALANCE |
| Mat Hue / Saturation / Value | ScoreSync HSV shader node |
| Mat Brightness / Contrast | ScoreSync BC shader node |
| Mat Opacity / Emission | Principled BSDF direct control |

Four trigger modes: **CC** (knob sweep), **Momentary** (dead-man hold), **Toggle** (latch), **Flash** (beat-reactive decay). Turn a pad into a strobe. Wire a fader to opacity. Make your visuals breathe.

### Visual Sampler — 16 grid-Style Pad Banks
Load video clips, image sequences, or rendered frame ranges into 4×4 pad banks. Trigger them from MIDI notes — they drop straight into the VSE or swap material textures on the fly. Stack multiple banks and switch between them with MIDI Program Change. Your setlist, your banks.

- Load from file or sample directly from the Blender timeline
- VSE output, Material output, or both simultaneously
- Velocity → Alpha for expressive dynamics
- Export / Import banks as JSON — carry your setup anywhere

### MIDI Mapping Layer — Control Anything
Map any MIDI CC or Note to any Blender property — object transforms, camera FOV, particle density, custom properties, anything the RNA path can reach. Learn mode captures in one move. Preset templates drop Camera, Active Object, or Scene mappings instantly.

### Multi-Editor Panels
ScoreSync lives in every editor you work from:

| Editor | What You Get |
|---|---|
| **3D Viewport** | Full suite — connection, transport, sampler, FX, mapping, diagnostics |
| **Video Sequence Editor** | Strip FX inspector with live MIDI bars, sampler pads, FX rack |
| **Shader / Node Editor** | Material FX chain setup, live HSV/BC sliders, sampler, mapping |

One-click buttons jump between editors without breaking your flow.

### DAW Mode + Hardware Mode
**FL Studio Mode** gives you full duplex, script health checks, and transport negotiation. **Hardware Mode** strips it back for standalone MIDI sequencers — MPC, Elektron, Roland MC-series. One click to switch.

---

## Requirements

| | |
|---|---|
| Blender | 4.2 LTS or newer |
| DAW | FL Studio (any modern version) or any MIDI clock source |
| Virtual ports | [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) (Windows) |
| Hardware mode | Any MIDI device that sends clock + note/CC |

---

## Quick Start

```
1. Create two loopMIDI ports:  ScoreSync_F2B  and  ScoreSync_B2F
2. Install the addon zip in Blender (Edit → Preferences → Add-ons → Install)
3. 3D Viewport → N-panel → ScoreSync → Connection → Install deps
4. Refresh ports, select In (F2B) and Out (B2F), click (Re)Connect
5. In FL Studio: Output = ScoreSync_F2B (SYNC on), Input = ScoreSync_B2F + ScoreSync script
6. Press Play in FL Studio — Blender locks in
```

Full setup walkthrough: [ScoreSync/docs/WALKTHROUGH.md](ScoreSync/docs/WALKTHROUGH.md)  
Troubleshooting: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

---

## MIDI Routing

```
FL Studio ──[ScoreSync_F2B]──► Blender   (clock · transport · SPP · CC · notes)
Blender   ──[ScoreSync_B2F]──► FL Studio (SPP locate · transport · duplex scrub)
```

> **Critical:** `ScoreSync_F2B` must be **disabled** as an FL MIDI Input or FL will echo transport back and trigger a start/stop loop.

---

## File Structure

```
ScoreSync/
├── __init__.py           Registration, scene properties
├── ops_connection.py     MIDI I/O threads, clock engine, apply loop, LED
├── ops_transport.py      Play / Stop / Locate operators, viewport navigation
├── ops_duplex.py         Duplex Assist — scrub sends SPP/MTC to DAW
├── ops_fx.py             FX Rack — 14 FX types, 4 trigger modes, learn engine
├── ops_mapping.py        MIDI Mapping layer — learn, apply, presets
├── ops_sampler.py        Visual Sampler — pad banks, cache, trigger engine
├── ops_markers.py        Timeline marker tools
├── ops_diagnostics.py    Port list, log export, presets, FL script export
├── ops_health.py         FL script probe/ACK handshake
├── prefs.py              AddonPreferences + preset definitions
├── ui_panel.py           3D Viewport N-panel (9 collapsible sub-panels)
├── ui_vse.py             Video Sequence Editor N-panel
├── ui_node.py            Shader / Node Editor N-panel
├── deps/                 Bundled mido + python-rtmidi wheels
├── flstudio/
│   └── device_ScoreSync.py   FL Studio MIDI controller script
├── docs/
│   └── WALKTHROUGH.md        Full feature walkthrough
└── examples/
    └── scoresync_demo.blend
```

---

## Live VJ Workflow Example

```
1. Load clips into sampler banks — one bank per song section
2. Add Opacity FX slot per VSE channel, bind each to a fader
3. Add Flash Opacity slot on all channels, bind to a kick-drum note
4. Enable PC → Bank Switch — Program Change follows your song structure
5. Hit Play in FL — Blender locks in, pads fire, faders blend, FX breathe
```

---

## Feedback, Bug Reports & Feature Requests

ScoreSync is actively developed and your input shapes what gets built next.

**Found a bug? Got a feature idea? Something not clicking?**

👉 **[Open an Issue on GitHub](https://github.com/DustinD-stack/ScoreSync-Blender/issues)**

When filing a bug report, please include:
- Blender version + OS
- What you did, what you expected, what happened instead
- The console output (Diagnostics → Snapshot is helpful)

**Feature requests are welcome** — especially around new controller types, additional FX targets, or DAW integrations beyond FL Studio. Vote on existing requests with a 👍 to help prioritize the roadmap.

---

## Roadmap Highlights

- [ ] Geometry Nodes parameter mapping
- [ ] OSC input (Ableton, TouchOSC, etc.)
- [ ] Clip launcher grid with loop controls
- [ ] MIDI output from timeline markers
- [ ] Preset library with shareable bank/mapping packs
- [ ] Mac / Linux testing + cross-platform virtual port support

---

## Development

```bash
# Deploy to Blender addons folder + FL Studio hardware folder
python deploy.py

# Build distributable zip
python deploy.py --zip

# Dry run (preview without copying)
python deploy.py --dry-run
```

---

## License

MIT — see [LICENSE.txt](LICENSE.txt)

**Author:** Dustin Douglas  
**Version:** 2.0.0  
**Blender:** 4.2 LTS+
