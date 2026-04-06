# ScoreSync — Setup Guide

ScoreSync syncs Blender's timeline to FL Studio (or any DAW) over MIDI using
two virtual loopMIDI ports. Setup takes about 5 minutes.

---

## Requirements

| Requirement | Where to get it |
|---|---|
| Blender 4.2 or later | blender.org |
| FL Studio (any modern version) | image-line.com |
| loopMIDI (Windows virtual MIDI ports) | tobias-erichsen.de/software/loopmidi.html |
| Internet connection (first run only) | for pip dependency install |

---

## Step 1 — Create loopMIDI ports

Open loopMIDI and create **exactly two ports** with these names (spelling matters):

| Port name | Direction |
|---|---|
| `ScoreSync_F2B` | FL Studio → Blender |
| `ScoreSync_B2F` | Blender → FL Studio |

Leave loopMIDI running in the background.

---

## Step 2 — Install the Blender addon

1. In Blender: **Edit → Preferences → Add-ons → Install**
2. Select `ScoreSync_v0.8.0.zip`
3. Enable the checkbox next to **ScoreSync**
4. Open the **ScoreSync** tab in the View 3D sidebar (N key)

---

## Step 3 — Install MIDI dependencies

In the ScoreSync panel → **Setup Wizard → Step 1 → Install**

This installs `mido` and `python-rtmidi` into Blender's Python.  
After it completes, click **Refresh** (Step 2).

---

## Step 4 — Configure FL Studio MIDI

Go to **FL Studio → Options → MIDI Settings**:

| Direction | Port | Setting |
|---|---|---|
| **Output** | `ScoreSync_F2B` | Enable, tick **SYNC** (sends clock + transport to Blender) |
| **Input** | `ScoreSync_B2F` | Enable, set Controller script to **ScoreSync** |
| **Input** | `ScoreSync_F2B` | **Disable** (critical — if enabled, FL echoes its own transport causing a feedback loop) |

> The ScoreSync controller script (`device_ScoreSync.py`) must be placed in:  
> `Documents\Image-Line\FL Studio\Settings\Hardware\ScoreSync\`  
> Use the **Export FL Script** button in the panel to copy it there.

---

## Step 5 — Export and load the FL script

1. In the ScoreSync panel → **Tools → Export FL Script**
2. Navigate to `Documents\Image-Line\FL Studio\Settings\Hardware\ScoreSync\`  
   (create the `ScoreSync` folder if it doesn't exist)
3. Click **Accept**
4. In FL Studio: **Options → MIDI Settings → Input → ScoreSync_B2F → Controller → ScoreSync**
5. Restart FL Studio (or reload the script)

---

## Step 6 — Connect in Blender

In the ScoreSync panel → **Setup Wizard**:

1. **MIDI In** → `ScoreSync_F2B 1`
2. **MIDI Out** → `ScoreSync_B2F 1`
3. Click **(Re)Connect**
4. Click **Check FL Script** — should show ✅ FL Script OK within 2 seconds

---

## Step 7 — Choose a preset

| Preset | Use when |
|---|---|
| **FL Follow** | FL drives everything; Blender is a passive display |
| **Blender Assist** | You mostly work in FL but want to scrub Blender when FL is stopped |
| **Auto Master** | Equal collaboration; whoever moves last leads for 4 seconds |

---

## Verify it works

1. Press Play in FL Studio → Blender timeline should start moving
2. Drag FL's transport cursor → Blender should follow
3. Stop FL → scrub Blender's playhead → FL cursor should move (Assist/Auto modes)

---

## Auto-connect on startup

Once you connect successfully, port names are saved in Addon Preferences.  
On next Blender start (or file load), ports are automatically reconnected if loopMIDI is running.

To disable: **Edit → Preferences → Add-ons → ScoreSync → uncheck Auto-connect on startup**
