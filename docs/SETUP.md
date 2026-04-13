# ScoreSync — Setup Guide

ScoreSync syncs Blender's timeline to any DAW or hardware sequencer over MIDI using two virtual loopMIDI ports. Setup takes about 5 minutes.

---

## Requirements

| Requirement | Where to get it |
|---|---|
| Blender 4.2 or later | blender.org |
| A DAW or hardware sequencer that sends MIDI clock | FL Studio, Ableton, Bitwig, Reaper, Logic, MPC, Elektron, Roland MC-series… |
| loopMIDI — Windows virtual MIDI ports | tobias-erichsen.de/software/loopmidi.html |
| Internet connection (first run only) | for pip dependency install |

---

## Step 1 — Create loopMIDI ports

Open loopMIDI and create **exactly two ports** with these names (spelling matters):

| Port name | Direction |
|---|---|
| `ScoreSync_F2B` | DAW / Hardware → Blender |
| `ScoreSync_B2F` | Blender → DAW / Hardware |

Leave loopMIDI running in the background whenever you use ScoreSync.

---

## Step 2 — Install the Blender addon

1. In Blender: **Edit → Preferences → Add-ons → Install**
2. Select the ScoreSync zip file
3. Enable the checkbox next to **ScoreSync**
4. Open the **ScoreSync** tab in the View 3D sidebar (press **N**)

---

## Step 3 — Install MIDI dependencies

In the ScoreSync panel → **Connection → Install deps**

This installs `mido` and `python-rtmidi` into Blender's Python.
After it completes, click **Refresh**. A one-time Blender restart may be needed.

---

## Step 4 — Route your DAW's MIDI clock to Blender

ScoreSync receives sync on the **ScoreSync_F2B** loopMIDI port.
Configure your DAW to send MIDI clock output to that port:

**FL Studio**
- Options → MIDI Settings → Output tab
- Enable `ScoreSync_F2B`, tick **SYNC**
- Do **not** enable `ScoreSync_F2B` as a MIDI Input — that creates a feedback loop

**Ableton Live**
- Preferences → MIDI → `ScoreSync_F2B` Output → set **Sync** to On

**Bitwig Studio**
- Settings → MIDI Controllers → add `ScoreSync_F2B` as output, enable Clock

**Reaper**
- Preferences → MIDI Devices → `ScoreSync_F2B` output → enable Send Clock

**Hardware (MPC, Elektron, Roland MC…)**
- Set the hardware's MIDI Out to `ScoreSync_F2B` via a USB-MIDI or DIN interface
- Enable MIDI Clock Send on the hardware

---

## Step 5 — (FL Studio only) Export and load the DAW script

If you're using FL Studio, ScoreSync includes a dedicated controller script that enables health checks and bidirectional transport.

1. In the ScoreSync panel → **Tools → Export DAW Script**
2. Place the exported file in: `Documents\Image-Line\FL Studio\Settings\Hardware\ScoreSync\`
3. In FL Studio: Options → MIDI Settings → Input → `ScoreSync_B2F` → Controller → **ScoreSync**
4. Restart FL Studio (or reload the script)

For all other DAWs, skip this step — basic clock sync works without a script.

---

## Step 6 — Connect in Blender

In the ScoreSync panel → **Connection**:

1. Click the refresh icon (↻) to scan for ports
2. **MIDI In** → `ScoreSync_F2B 1`
3. **MIDI Out** → `ScoreSync_B2F 1`
4. Click **(Re)Connect**

The LED in the header tells you what's happening:

| LED | Meaning |
|---|---|
| 🟢 clock OK | MIDI clock arriving — full sync active |
| 🟡 SPP only | Position data but no clock ticks |
| 🔴 idle | Nothing received — check your DAW output routing |

---

## Step 7 — Choose a preset (optional)

| Preset | Use when |
|---|---|
| **DAW Follow** | DAW drives everything; Blender is a passive display |
| **Blender Assist** | You mostly work in the DAW but want to scrub Blender when the DAW is stopped |
| **Auto Master** | Equal collaboration; whoever moves last leads for a few seconds |

---

## Verify it works

1. Press Play in your DAW → Blender's timeline should start moving
2. Drag your DAW's transport cursor → Blender should follow
3. Stop the DAW → scrub Blender's playhead → the DAW cursor should move (Assist/Auto modes)

---

## Auto-connect on startup

Once you connect successfully, port names are saved in Addon Preferences.
On next Blender start (or file load), ports are automatically reconnected if loopMIDI is running.

To disable: **Edit → Preferences → Add-ons → ScoreSync → uncheck Auto-connect on startup**
