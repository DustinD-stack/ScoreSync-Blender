# ScoreSync — Troubleshooting

---

## Blender doesn't follow the DAW

**Check first:**
- loopMIDI is running with `ScoreSync_F2B` and `ScoreSync_B2F` ports active
- Your DAW's MIDI clock output is routed to `ScoreSync_F2B` with sync/clock enabled
- Blender MIDI In is set to `ScoreSync_F2B 1`
- You clicked **(Re)Connect** after selecting ports

**LED shows 🔴 idle:**
No clock or SPP received. Confirm your DAW's MIDI output is enabled and sending clock to `ScoreSync_F2B`.

**LED shows 🟡 SPP only:**
Position data arrives but no MIDI clock ticks. Your DAW output is connected but the "Send MIDI Clock" or "Sync" option may not be enabled.

**LED shows 🟢 clock OK but Blender doesn't move:**
Clock arrives but **Follow MIDI Clock** is off. Enable it in the Transport section.

---

## DAW transport starts/stops repeatedly (feedback loop)

**Cause:** `ScoreSync_F2B` is enabled as a DAW **MIDI Input**, so your DAW reads its own transport back.

**Fix:** In your DAW's MIDI settings → find `ScoreSync_F2B` in the Input list → **Disable** it as an input.

Only `ScoreSync_B2F` should be a DAW input. `ScoreSync_F2B` is DAW output only.

---

## "DAW Script: Not detected" after clicking Check (FL Studio only)

1. Confirm `device_ScoreSync.py` is in `Documents\Image-Line\FL Studio\Settings\Hardware\ScoreSync\`
   - Use **Tools → Export DAW Script** in the ScoreSync panel to copy it there automatically
2. In FL MIDI Settings → Input → `ScoreSync_B2F` → Controller = **ScoreSync**
3. Restart FL Studio after installing the script
4. After restart, FL's hint bar should show: `ScoreSync script loaded ✅`

---

## SPP locate lands at the wrong position

**Cause:** BPM mismatch between Blender and your DAW. SPP is converted using BPM.

**Fix:** Enable **Manual BPM** in the Transport section and enter the exact BPM from your DAW.
Or wait for the Auto BPM estimate to stabilise (takes ~2 seconds of playback).

---

## Scrubbing Blender doesn't move the DAW

1. Check **Master Mode** — if set to **DAW**, Blender never pushes.
2. Check **Duplex Mode** — must be **Assist** or **Force** (not Off).
3. The DAW must be **stopped**. While the DAW is playing, Blender goes silent.
4. Wait 400 ms after the DAW last moved. During that window Blender is still quiet.

---

## Scrubbing the DAW doesn't move Blender when stopped

- Confirm MIDI In is `ScoreSync_F2B 1` and connected
- Your DAW must send SPP when you drag the transport. Most DAWs do this by default when stopped.
- Enable **Debug logging** in Diagnostics and watch the System Console
  (`Window → Toggle System Console`) for `[ScoreSync APPLY] spp` lines

---

## MIDI learn doesn't capture anything

ScoreSync tries to open your controller's MIDI port directly for learn mode. If your DAW is running and has exclusive access to the controller port, the scan may fail silently.

**Option A — Close your DAW** before doing MIDI learn in Blender.

**Option B — Route controller through the DAW to Blender.** Configure your DAW to forward controller CC/Note data through `ScoreSync_F2B` to Blender. Then the main listener captures it for learn.

**Option C — Use the DAW's MIDI pass-through.** In most DAWs you can enable the controller as an input and route its output to `ScoreSync_F2B`.

---

## Mapping bank switches don't fire

- Make sure you clicked **Bind MIDI** for the bank and actually pressed a physical button
- Check that the binding shows the MIDI type and number (not "unbound") in the Bank Switch Bindings section
- Verify the physical button sends the same CC/Note that was learned

---

## Port list is empty / "no MIDI inputs found"

1. Install dependencies: **Connection → Install deps**
2. Click the refresh icon (↻) — ports should appear
3. Confirm loopMIDI is running (check the taskbar tray icon)

---

## Blender crashes or freezes on connect

This can happen if a previous listener thread is still attached to an open port.
Click **Reconnect now** in the Connection box to force-close and reopen.
If it persists, disable and re-enable the addon in Preferences.

---

## Ports disappear mid-session

loopMIDI ports vanish if loopMIDI crashes or is closed.
Enable **Auto-reconnect** — Blender will reopen ports when they reappear.

---

## "Install MIDI Dependencies" fails

Try installing manually in a terminal:

```
"C:\Program Files\Blender Foundation\Blender 4.2\4.2\python\bin\python.exe" -m pip install mido python-rtmidi
```

Then restart Blender and click **Refresh**.

---

## Getting more information

- **Snapshot to Console** — prints current port state, BPM, master mode, and event count
- **Export Log** — saves the last 200 events to a `.txt` file with timestamps
- **Debug logging** — enables per-message console output (verbose; use briefly)

If you report a bug, please attach the exported log and your Blender + OS version.
