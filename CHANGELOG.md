# ScoreSync Changelog

## v1.0.0 (2026-04-05)
- **v1.0 release — all Phase 9 criteria met**
- `SCORESYNC_OT_send_test`: now sends a real CC#119=1 on the MIDI Out port (was a no-op stub); confirms end-to-end wiring without affecting FL transport
- Removed "preview" from addon description and Send Test button label
- Excluded `powershell mirroring.md` dev artifact from zip builds
- Fixed redundant case-check in port swap validation (`ui_panel.py`)
- Verified all v1.0 criteria: FL→Blender sync, Blender→FL assist, auto master, health check, diagnostics, presets, persistence, packaging, docs

## v0.8.0 (2026-04-05)
- Phase 8: packaging, docs, `--zip` build target in deploy.py
- `docs/SETUP.md` — full 7-step setup guide
- `docs/TROUBLESHOOTING.md` — self-serve diagnosis for every common failure
- `README.md` — feature list, quick start, file structure, dev workflow

## v0.7.0 (2026-04-05)
- **Presets + Persistence**
- `prefs.py`: `ScoreSyncPreferences` (AddonPreferences) stores last port names
- Auto-restore on Blender startup and on every `.blend` file load
- Three built-in presets: FL Follow, Blender Assist, Auto Master
- `SCORESYNC_OT_apply_preset` operator; preset buttons in UI
- Port names saved automatically after each successful connect

## v0.6.0 (2026-04-05)
- **Diagnostics + Log Export**
- `DEV.event_log` ring buffer (200 entries); `_log_event()` helper
- `SCORESYNC_OT_snapshot` — prints full state to System Console
- `SCORESYNC_OT_export_log` — saves timestamped event log to `.txt`
- Snapshot + Export Log buttons in Diagnostics box
- Improved FL hint messages: probe ACK, START/STOP/CONTINUE, SPP OK/FAIL

## v0.5.0 (2026-04-05)
- **Auto Master Switching**
- `DEV.master_until_ts`, `_claim_blender_master()`, `_blender_is_master()`
- Three modes: AUTO (default), FL (locked), BLENDER (locked)
- Blender claims master on any button press or scrub; holds for configurable duration
- Incoming FL transport/SPP dropped while Blender holds master
- Live master status string updated in timer; shown in Setup Wizard + Duplex box

## v0.4.0 (2026-04-05)
- **BPM Accuracy Upgrade**
- Shared `_get_bpm(scene)` helper: manual override → scene estimate → EMA → 120
- Clock BPM now uses listener-thread arrival timestamp (not drain time)
- dt guard tightened to 0.01–0.08 s to reject glitch spikes
- Manual BPM toggle + field in Transport-in section
- SPP apply and all outbound sends use `_get_bpm`

## v0.3.3 (2026-04-05) — merged into v0.4.0
- **Echo Guard (Phase 2)**
- `DEV.tx_lock_until`: 350 ms incoming transport block after button-press sends
- `_arm_tx_lock()` called by Play, Stop, Locate operators
- Duplex continuous sends do NOT arm the lock (avoids scrub freeze)
- `DEV.last_fl_spp_ts`: 400 ms quiet window prevents duplex echoing FL scrubs

## v0.3.2 (2026-04-05)
- **Setup Wizard + Export**
- Setup Wizard section in panel with 5 numbered steps
- Port validation warnings: same port, swapped ports, no ports found
- Feedback loop reminder when F2B appears as selected input
- `SCORESYNC_OT_export_fl_script` — file browser copies bundled FL script
- `ScoreSync/flstudio/device_ScoreSync.py` — FL script bundled inside addon
- `DEBUG = False` toggle in FL script; verbose prints gated behind it
- `DEV.tx_lock_until` field added to `_ScoreSyncDevice`

## v0.3.1 (prior)
- MTC quarter-frame option during scrub (`scoresync_duplex_use_mtc`, `scoresync_duplex_mtc_fps`)

## v0.3.0 (prior)
- Duplex Assist mode: Blender scrub → SPP → FL Studio
- `_duplex_tick` Blender timer; `SCORESYNC_OT_set_duplex_mode`

## v0.2.2 (prior)
- Auto-reconnect on port loss; `SCORESYNC_OT_reconnect_now`

## v0.2.1 (prior)
- Marker workflow: preset drop, prev/next jump, rename to Bar:Beat

## v0.1.x (prior)
- Initial FL → Blender sync: MIDI clock, SPP, Start/Stop/Continue
- FL script health check (probe CC119=7, ACK CC119=100)
- LED status indicator (🟢/🟡/🔴)
