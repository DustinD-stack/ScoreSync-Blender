# ScoreSync — Troubleshooting

---

## Blender doesn't follow FL Studio

**Check first:**
- loopMIDI is running with `ScoreSync_F2B` and `ScoreSync_B2F` ports
- FL Studio Output `ScoreSync_F2B` is enabled with SYNC ticked
- Blender MIDI In is set to `ScoreSync_F2B 1`
- You clicked **(Re)Connect** after selecting ports

**LED shows 🔴 idle:**  
No clock or SPP received. Confirm FL Output is enabled with SYNC.

**LED shows 🟡 SPP only:**  
SPP arrives but no MIDI clock. FL Output is connected but SYNC may not be ticked, or "Send master sync" is off.

**LED shows 🟢 clock OK but Blender doesn't move:**  
Clock arrives but Follow MIDI Clock is off. Enable it in Transport-in section.

---

## FL Studio transport starts/stops repeatedly (feedback loop)

**Cause:** `ScoreSync_F2B` is enabled as an FL **input**, so FL reads its own transport back.

**Fix:** Go to FL MIDI Settings → Input tab → find `ScoreSync_F2B` → **Disable** it.

The Setup Wizard shows a warning if your selected Input port looks like F2B.

---

## "FL Script: Not detected ❌" after clicking Check

1. Confirm `device_ScoreSync.py` is in `Documents\Image-Line\FL Studio\Settings\Hardware\ScoreSync\`
   - Use **Export FL Script** in the Tools section to copy it there
2. In FL MIDI Settings → Input → `ScoreSync_B2F` → Controller = **ScoreSync**
3. Restart FL Studio after installing the script
4. After restart, FL's hint bar should show: `ScoreSync script loaded ✅`

---

## SPP locate lands at the wrong position

**Cause:** BPM mismatch between Blender and FL. SPP is converted using BPM.

**Fix:** Enable **Manual BPM** in the Transport-in section and enter the exact BPM from FL.  
Or wait for the Auto BPM estimate to stabilise (takes ~2 seconds of playback).

---

## Scrubbing Blender doesn't move FL

1. Check Master Mode — if set to **FL**, Blender never pushes.
2. Check Duplex Mode — must be **Assist** or **Force** (not Off).
3. FL must be **stopped**. While FL is playing, Blender goes silent.
4. Wait 400 ms after FL last moved. During that window Blender is still quiet.

---

## Scrubbing FL doesn't move Blender when stopped

- Confirm MIDI In is `ScoreSync_F2B 1` and connected
- FL must send SPP when you drag the transport. Some FL versions only send SPP
  when the song position changes while stopped — try dragging slowly.
- Enable **Debug logging** in Diagnostics and watch the System Console
  (`Window → Toggle System Console`) for `[ScoreSync APPLY] spp` lines

---

## Port list is empty / "no MIDI inputs found"

1. Install dependencies: **Setup Wizard → Step 1 → Install**
2. Click **Refresh** — ports should appear
3. Confirm loopMIDI is running (check the taskbar tray icon)

---

## Blender crashes or freezes on connect

This can happen if a previous listener thread is still attached to an open port.  
Click **Reconnect now** (in the Connection box) to force-close and reopen.  
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

If you report a bug, please attach the exported log.
