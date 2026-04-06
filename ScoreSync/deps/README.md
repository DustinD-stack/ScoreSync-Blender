
# ScoreSync v0.1.1 (Preview)

Sync Blender’s timeline to your DAW over MIDI.

## Features
- Choose MIDI input port
- Install `mido` + `python-rtmidi` from inside Blender
- Diagnostics: list ports, send test (console)
- Designed for DAW-as-master setups

## Requirements
- Blender 4.0+
- A DAW capable of sending MIDI clock / transport
- A virtual loopback or hardware MIDI connection

## Quick Start
1. Download the ZIP and install via **Edit → Preferences → Add-ons → Install…**
2. Open **3D View → Sidebar → ScoreSync**
3. Click **Install MIDI Dependencies**
4. Click **Refresh Ports**
5. Pick your DAW’s output port as **MIDI In**
6. Press Play in your DAW → Blender timeline should follow (in future versions).

> This is a preview release focused on connectivity & diagnostics. Transport following and duplex control are staged for later versions.

## Support
Please report issues with:
- OS
- Blender version
- DAW name/version
- Exact error from Blender console


# ScoreSync (preview)

Sync Blender’s timeline with your DAW over MIDI.

## Features
- DAW → Blender: MIDI Clock, SPP, Start/Stop/Continue
- BPM estimate, “add marker every bar,” marker tools
- Duplex Assist: scrub in Blender to nudge the DAW (SPP or MTC), final SPP locate
- Transport TX: Play/Stop (MMC or fallback), Locate (SPP)
- Auto-reconnect, LED status

## Setup
1. Install the ZIP in **Edit → Preferences → Add-ons → Install…**
2. Create two virtual MIDI ports (Windows: loopMIDI):  
   - `FL to Blender` (DAW → Blender)  
   - `Blender to FL` (Blender → DAW)
3. In the panel, pick **MIDI In/Out** and click **(Re)Connect**.
4. Use **Duplex Assist** (Assist mode) to scrub Blender and follow in DAW.

## Known limits
- MTC is Assist-only (scrubbing). Final locate is sent via SPP for compatibility.
