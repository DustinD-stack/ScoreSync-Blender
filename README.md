# ScoreSync

**Sync Blender's timeline to FL Studio (or any DAW) over MIDI.**

ScoreSync is a Blender addon that listens to MIDI clock, transport, and Song
Position Pointer (SPP) messages from your DAW and keeps Blender's playhead in
sync — in real time. It also lets Blender push position back to the DAW when
you scrub the Blender timeline.

---

## Features

- **FL → Blender:** follow MIDI clock, Start/Stop/Continue, SPP locate
- **Blender → FL (Duplex Assist):** scrubbing Blender nudges the DAW when stopped
- **Auto Master switching:** FL leads while playing; Blender takes over on scrub
- **BPM estimation** from MIDI clock (EMA smoothed) + manual override
- **MTC scrub** option (quarter-frame bursts while dragging)
- **Health check:** probe/ACK handshake confirms FL script is loaded
- **Presets:** FL Follow / Blender Assist / Auto Master (one click)
- **Auto-reconnect** on port loss + auto-restore ports on startup
- **Diagnostics:** Snapshot to console, event log export

---

## Requirements

- Blender 4.2+
- FL Studio (any modern version)
- [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) (Windows virtual MIDI ports)

---

## Quick start

1. Create two loopMIDI ports: `ScoreSync_F2B` and `ScoreSync_B2F`
2. Install the addon zip in Blender
3. In the ScoreSync panel: Install deps → Refresh → select ports → Connect
4. In FL Studio: enable Output `ScoreSync_F2B` with SYNC, Input `ScoreSync_B2F` with ScoreSync script
5. Press Play in FL — Blender follows

See [docs/SETUP.md](docs/SETUP.md) for the full guide.

---

## MIDI routing

```
FL Studio  ──[ScoreSync_F2B]──►  Blender   (clock, transport, SPP)
Blender    ──[ScoreSync_B2F]──►  FL Studio (SPP locate, transport buttons)
```

**Critical:** `ScoreSync_F2B` must be **disabled** as an FL input or FL will
echo its own transport back, causing a start/stop feedback loop.

---

## File structure

```
ScoreSync/
├── __init__.py          # Registration, properties
├── ui_panel.py          # All UI panels
├── ops_connection.py    # MIDI I/O threads, queue, apply, LED
├── ops_transport.py     # Play/Stop/Locate operators (Blender → DAW)
├── ops_duplex.py        # Duplex Assist scrub → SPP/MTC
├── ops_markers.py       # Timeline marker tools
├── ops_diagnostics.py   # Port list, log export, presets, FL script export
├── ops_health.py        # FL script probe/ACK
├── prefs.py             # AddonPreferences + preset definitions
├── deps/                # Dependency installer
├── flstudio/
│   └── device_ScoreSync.py   # Bundled FL controller script
└── examples/
    └── scoresync_demo.blend

device_ScoreSync.py      # Root copy (used by deploy.py)
deploy.py                # Dev helper: copies files to install locations / builds zip
docs/
├── SETUP.md
└── TROUBLESHOOTING.md
```

---

## Development — deploy to Blender + FL

```bash
# Copy addon to Blender addons folder and FL script to Hardware folder
python deploy.py

# Build distributable zip only
python deploy.py --zip

# Preview what would be copied without doing anything
python deploy.py --dry-run
```

---

## License

MIT — see [LICENSE.txt](LICENSE.txt)

Author: Dustin Douglas
