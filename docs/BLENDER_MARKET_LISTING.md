# ScoreSync — Blender Market Listing Copy

---

## TITLE
ScoreSync — Live MIDI Sync, Visual Sampler & FX Rack for Blender

## TAGLINE
Lock Blender to your DAW. Fire clips from a pad. Shred visuals with a knob. All in real time.

---

## SHORT DESCRIPTION (shown in search results — 160 chars max)
Real-time MIDI sync, MPC-style clip sampler, live FX rack, and MIDI mapping for Blender. Works with FL Studio, any DAW, or standalone MIDI hardware.

---

## FULL DESCRIPTION

### ScoreSync turns Blender into a live visual instrument.

Whether you're VJing a concert, scoring a film to picture, building a beat-reactive music video, or performing live A/V — ScoreSync is the missing link between your DAW and Blender.

Press Play in FL Studio. Blender locks in. Twist a knob. A shader tears apart in real time. Hit a pad. A video clip drops onto the timeline. This is what Blender feels like when it's wired to your music.

---

### BEAT-LOCKED TIMELINE SYNC

ScoreSync listens to MIDI Clock, Start/Stop/Continue, and Song Position Pointer from your DAW and keeps Blender's playhead in frame-accurate sync — in real time. Scrub Blender and the DAW follows. Hit Play in FL Studio and Blender rolls. No drift. No guesswork.

- Auto BPM detection from MIDI clock (EMA-smoothed, typically ±0.5 BPM)
- Manual BPM override for rock-solid SPP conversion
- Reset-on-Start for clean bar-1 restarts
- Works with FL Studio, Ableton (via MIDI clock), Reaper, Logic, or any hardware sequencer

---

### LIVE FX RACK — 14 MIDI-DRIVEN VISUAL EFFECTS

Map any knob, fader, or pad to visual parameters across VSE strips and shader materials. Four trigger modes let you perform, not just automate.

**VSE Strip FX:**
- Opacity — fade strips in and out like a mixer
- Bright Mult & Saturation — direct strip controls
- Brightness & Contrast — BRIGHT_CONTRAST modifier
- Tint R / G / B — per-channel COLOR_BALANCE

**Material / Shader FX:**
- Mat Hue / Saturation / Value — ScoreSync HSV node
- Mat Brightness / Contrast — ScoreSync BC node
- Mat Opacity & Emission — Principled BSDF direct

**Trigger Modes:**
- **CC** — smooth knob/fader sweep across Min→Max
- **Momentary** — hold pad = Max, release = Min (dead-man switch)
- **Toggle** — each hit latches between Min and Max
- **Flash** — hits Max then decays over your set time (beat-reactive strobe/glow)

---

### VISUAL SAMPLER — MPC-STYLE PAD BANKS

Load video clips, image sequences, or rendered frame ranges into 4×4 pad banks and trigger them live from MIDI notes. Clips drop into the VSE or swap material textures — or both at once.

- Multiple banks, switched via MIDI Program Change (one PC per song section)
- Load from file or sample directly from the Blender timeline
- VSE output, Material output, or simultaneously
- Velocity → Alpha for expressive, dynamic hits
- Export / Import banks as JSON — carry your entire setup between projects

---

### MIDI MAPPING LAYER — CONTROL ANYTHING

Map any MIDI CC or Note On to any Blender property. Object X position. Camera FOV. Particle density. Custom properties. If Blender's RNA path can reach it, ScoreSync can drive it.

- One-move Learn mode — wiggle a knob, it's captured
- Preset templates: Camera (6 axes), Active Object (5 axes), Scene (2 controls)
- Live value readout in the inspector — see raw MIDI → mapped output in real time
- Export/Import as JSON for full session recall

---

### LIVES IN EVERY EDITOR

ScoreSync's panel is accessible from wherever you work:

- **3D Viewport** — full suite with live VSE strip monitor
- **Video Sequence Editor** — strip FX inspector with live MIDI bars, sampler, FX rack
- **Shader / Node Editor** — material FX chain, live HSV/BC sliders, full sampler access

One-click buttons jump between editors without losing your place.

---

### FL STUDIO MODE + HARDWARE MODE

**FL Studio Mode:** Full duplex transport negotiation, script health check, auto-reconnect, and scrub-send. Use this with loopMIDI for the tightest possible FL ↔ Blender integration.

**Hardware Mode:** Stripped back for standalone MIDI gear — MPC, Elektron, Roland MC-series, Arturia BeatStep, etc. One click switches modes. No reconfiguration needed.

---

### WHAT'S IN THE BOX

- ScoreSync Blender addon (installs as a standard .zip)
- FL Studio device script (drop-in, no coding needed)
- Full walkthrough documentation covering every feature
- Demo .blend with pre-wired FX slots, pad banks, and MIDI mappings
- Ongoing updates + bug fixes via GitHub

---

## FEATURE BULLETS (for sidebar / quick-scan)

- Real-time MIDI clock sync — DAW drives Blender frame-accurately
- Duplex transport — Blender can push Play/Stop/Locate back to the DAW
- 14 FX types across VSE strips and shader materials
- 4 trigger modes: CC, Momentary, Toggle, Flash
- MPC-style 4×4 pad banks with clip sampler
- MIDI Program Change → bank switching
- Map any MIDI control to any Blender property (RNA path)
- Works with FL Studio, any DAW, or standalone MIDI hardware
- Panels in 3D View, VSE, and Shader Editor
- One-click editor jumping
- Export/import mappings and banks as JSON
- Bundled FL Studio controller script
- loopMIDI virtual port setup guide included
- Active development — feedback drives the roadmap

---

## FAQ

**Does it work with Ableton / Reaper / Logic?**
Yes — any DAW that can send MIDI clock and transport messages works for sync. The bundled FL Studio script adds extra features (health check, duplex negotiation) specific to FL, but sync and FX work with any MIDI source.

**Does it work on Mac or Linux?**
Currently developed and tested on Windows with loopMIDI. Mac/Linux support is on the roadmap. Technically the MIDI layer (mido + rtmidi) is cross-platform, but virtual port setup differs per OS.

**What Blender version is required?**
Blender 4.2 LTS or newer.

**Can I use it for commercial projects?**
Yes — your license covers personal and commercial use including client work, film, live performance, and installations.

**Does it require a subscription?**
No. One-time purchase includes all 2.x updates for 12 months.

**How do I report bugs or request features?**
Open an issue at https://github.com/DustinD-stack/ScoreSync-Blender/issues — bugs are prioritized, feature requests are voted on.

---

## TAGS
midi, sync, fl studio, live, vj, performance, sequencer, transport, clock, fx, shader, vse, sampler, pad, realtime, music, audio, animation, compositor, node

## CATEGORY
Animation > Tools

## PRICE SUGGESTION
$29 — $39 (comparable: MIDI controls for Blender typically $15–$45; this covers sync + sampler + FX rack)

---

## SCREENSHOTS NEEDED (capture these)
1. 3D Viewport N-panel open — sampler grid with a pad selected showing Load File / Sample Timeline
2. VSE with Active Strip inspector showing live MIDI bars and opacity slider
3. Shader Editor N-panel showing Material FX Chain with live HSV sliders
4. FX Rack with 3–4 active slots and Flash mode selected on one
5. MIDI Mapping list with inspector open showing a camera FOV binding
6. Side-by-side: FL Studio playing + Blender timeline locked in sync (split screenshot)
