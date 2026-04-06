# ScoreSync - ops_connection.py
# MIDI I/O, listener thread, main-thread apply, LED, auto-reconnect, and FL script health.

import bpy
import threading, time

# ---- mido loader -----------------------------------------------------------
def _get_mido():
    try:
        import mido
        try:
            mido.set_backend("mido.backends.rtmidi")
        except Exception:
            pass
        return mido
    except Exception:
        return None

# ---- Enums for ports -------------------------------------------------------
def items_midi_inputs(self, context):
    mido = _get_mido()
    items = []
    try:
        names = mido.get_input_names() if mido else []
    except Exception:
        names = []

    if not names:
        items.append(("NONE", "<no MIDI inputs found>", "Install deps and refresh"))
    else:
        for n in names:
            items.append((n, n, f"MIDI input: {n}"))
    return items


def items_midi_outputs(self, context):
    mido = _get_mido()
    items = []
    try:
        names = mido.get_output_names() if mido else []
    except Exception:
        names = []

    if not names:
        items.append(("NONE", "<no MIDI outputs found>", "Install deps and refresh"))
    else:
        for n in names:
            items.append((n, n, f"MIDI output: {n}"))
    return items


# ---- Device state (LED, timers, bars, etc.) --------------------------------
class _ScoreSyncDevice:
    # port state
    in_port_name = None
    out_port_name = None
    in_port = None
    out_port = None
    listener_running = False
    timer_registered = False
    stop_requested = False

    # health listener (listen for FL ACK on a second port)
    health_in_port = None
    health_listener_running = False
    health_stop_requested = False
    health_port_name = None


    # timing/health for LED
    last_clock_ts = 0.0
    last_spp_ts = 0.0
    last_any_ts = 0.0

    # BPM estimate from MIDI clock
    bpm_ema = 0.0
    bpm_alpha = 0.2

    # frame/bar state
    frame_origin = 0
    frame_accum_f = 0.0
    clock_total = 0
    clocks_in_bar = 0
    bar_index = 1
    # debug clock stats
    clock_dbg_ts = 0.0
    clock_dbg_count = 0
    # debug / jitter guards
    last_spp_pos = None
    last_spp_apply_ts = 0.0
    dbg_last_print = 0.0
    dbg_clock_count = 0
    dbg_clock_ts = 0.0

    # True while FL is playing (received start/continue, cleared on stop).
    # ops_duplex uses this to silence outgoing SPP while FL is master.
    fl_is_playing = False

    # Echo guard: ignore incoming transport/SPP until this timestamp.
    # Set by ops_transport after button-press sends (Play/Stop/Locate).
    tx_lock_until = 0.0

    # Timestamp of the last SPP message received FROM FL.
    last_fl_spp_ts = 0.0

    # Auto master: Blender holds master until this timestamp, then FL reclaims.
    # Set by _claim_blender_master(); 0.0 means FL is currently master.
    master_until_ts = 0.0

    # Diagnostics: ring buffer of recent events for log export.
    # Each entry is a dict: {ts, type, detail}
    event_log = []
    EVENT_LOG_MAX = 200


DEV = _ScoreSyncDevice()


def _log_event(event_type: str, detail: str = ""):
    """Append to the DEV ring buffer (thread-safe for reads on main thread only)."""
    entry = {"ts": time.time(), "type": event_type, "detail": detail}
    DEV.event_log.append(entry)
    if len(DEV.event_log) > DEV.EVENT_LOG_MAX:
        del DEV.event_log[:-DEV.EVENT_LOG_MAX]


def _claim_blender_master(scene):
    """Blender takes transport master for the configured hold duration."""
    hold_ms = max(200, int(getattr(scene, "scoresync_master_hold_ms", 2000)))
    DEV.master_until_ts = time.time() + hold_ms / 1000.0
    _log_event("TX master_claim", f"hold={hold_ms}ms")


def _blender_is_master() -> bool:
    """True while Blender hold is active (AUTO mode check only)."""
    return time.time() < DEV.master_until_ts


def _get_bpm(scene) -> float:
    """Return the best available BPM: manual override → scene estimate → EMA → 120."""
    if getattr(scene, "scoresync_use_manual_bpm", False):
        manual = float(getattr(scene, "scoresync_manual_bpm", 0.0) or 0.0)
        if manual > 0.0:
            return manual
    est = float(getattr(scene, "scoresync_bpm_estimate", 0.0) or 0.0)
    if est > 0.0:
        return est
    ema = float(getattr(DEV, "bpm_ema", 0.0) or 0.0)
    return ema if ema > 0.0 else 120.0



# ---- Queue + small helpers --------------------------------------------------
_message_queue = []  # list[(ts, msg_dict)]
_QLOCK = threading.Lock()
_LISTENER_GEN = 0

def _dbg(scene, text, min_dt=0.0):
    """Rate-limited console debug when scene.scoresync_debug is ON."""
    if not getattr(scene, "scoresync_debug", False):
        return
    now = time.time()
    if min_dt <= 0.0 or (now - DEV.dbg_last_print) >= min_dt:
        print(text)
        DEV.dbg_last_print = now


def _enqueue(msg):
    with _QLOCK:
        _message_queue.append((time.time(), msg))
        if len(_message_queue) > 512:      # cap backlog
            del _message_queue[:-256]      # drop oldest, keep newest

def _toggle_playing(play_wanted: bool):
    scr = bpy.context.screen
    if not scr:
        return
    is_playing = scr.is_animation_playing
    if play_wanted and not is_playing:
        bpy.ops.screen.animation_play()
    elif (not play_wanted) and is_playing:
        bpy.ops.screen.animation_play()

def _add_marker_if_needed(scene):
    if not getattr(scene, "scoresync_add_marker_every_bar", False):
        return
    beats_per_bar = max(1, int(getattr(scene, "scoresync_time_sig_n", 4)))
    clocks_per_bar = 24 * beats_per_bar
    if DEV.clocks_in_bar >= clocks_per_bar:
        f = int(scene.frame_current)
        name = f"Bar {DEV.bar_index:03d}"
        try:
            scene.timeline_markers.new(name=name, frame=f)
        except Exception:
            scene.timeline_markers.new(name=f"{name}*", frame=f)
        DEV.bar_index += 1
        DEV.clocks_in_bar -= clocks_per_bar

def _update_led(scene):
    now = time.time()
    # Fresh clock in last 0.6s -> green
    if DEV.last_clock_ts and (now - DEV.last_clock_ts) <= 0.6:
        scene.scoresync_led_text = "🟢 clock OK"
        return
    # No clock, but SPP in last 2s -> yellow
    if DEV.last_spp_ts and (now - DEV.last_spp_ts) <= 2.0:
        scene.scoresync_led_text = "🟡 SPP only"
        return
    # Otherwise red
    scene.scoresync_led_text = "🔴 idle"


def _ensure_ports(scene):
    """If Auto-reconnect is ON, try to reopen missing ports when they reappear."""
    if not getattr(scene, "scoresync_autoreconnect", True):
        return
    mido = _get_mido()
    if not mido:
        return

    # INPUT
    if DEV.in_port_name and (not DEV.listener_running) and (DEV.in_port is None) and (not DEV.stop_requested):
        try:
            inputs = set(mido.get_input_names())
        except Exception:
            inputs = set()
        if DEV.in_port_name in inputs:
            try:
                global _LISTENER_GEN
                _LISTENER_GEN += 1
                gen = _LISTENER_GEN
                t = threading.Thread(target=_listener_loop, args=(DEV.in_port_name, gen), daemon=True)
                t.start()
                scene.scoresync_status = f"Auto-reconnect In: {DEV.in_port_name}"
            except Exception:
                pass

    # OUTPUT
    if DEV.out_port_name and (DEV.out_port is None):
        try:
            outputs = set(mido.get_output_names())
        except Exception:
            outputs = set()
        if DEV.out_port_name in outputs:
            try:
                DEV.out_port = mido.open_output(DEV.out_port_name)
                scene.scoresync_status = f"Auto-reconnect Out: {DEV.out_port_name}"
            except Exception:
                pass

# ---- Main-thread apply ------------------------------------------------------
def _apply_incoming(scene, ts, msg):
    """Run on Blender's main thread via timer."""
    # latency gate
    latency_s = int(getattr(scene, "scoresync_latency_ms", 0)) / 1000.0
    if time.time() - ts < latency_s:
        return False

    t = msg.get("type")
    if getattr(scene, "scoresync_debug", False) and t in ("start", "stop", "continue", "spp"):
        print(f"[ScoreSync APPLY] {t}  msg={msg}")

    # Master mode gating: block FL transport/SPP while Blender holds master.
    if t in ("start", "stop", "continue", "spp"):
        master_mode = getattr(scene, "scoresync_master_mode", "AUTO")
        if master_mode == "BLENDER":
            _dbg(scene, f"[ScoreSync APPLY] master=BLENDER — dropping incoming {t}")
            return True
        if master_mode == "AUTO" and _blender_is_master():
            _dbg(scene, f"[ScoreSync APPLY] master=BLENDER(hold) — dropping incoming {t}")
            return True

    # Echo guard: ignore incoming transport/SPP for 350 ms after a button-press send.
    if t in ("start", "stop", "continue", "spp"):
        if time.time() < DEV.tx_lock_until:
            _dbg(scene, f"[ScoreSync APPLY] tx_lock active — dropping {t}")
            return True


    # FL script health ACK (thread-safe set on main thread)
    
    if t == "health_ok":
        scene.scoresync_script_ok = True
        scene.scoresync_script_ok_ts = time.time()
        scene.scoresync_led_text = "🟢 FL Script OK"
        scene.scoresync_status = "FL Script: OK"
        _log_event("health_ok", "FL script ACK received")
        return True



    if t == "start":
        DEV.last_any_ts = time.time()
        DEV.fl_is_playing = True
        if getattr(scene, "scoresync_reset_on_start", True):
            scene.frame_current = 0
            DEV.frame_origin = 0
            DEV.frame_accum_f = 0.0
            DEV.clock_total = 0
            DEV.clocks_in_bar = 0
            DEV.bar_index = 1
        _toggle_playing(True)
        scene.scoresync_status = "Start"
        _log_event("RX start")
        return True

    if t == "continue":
        DEV.last_any_ts = time.time()
        DEV.fl_is_playing = True
        _toggle_playing(True)
        scene.scoresync_status = "Continue"
        _log_event("RX continue")
        return True

    if t == "stop":
        DEV.last_any_ts = time.time()
        DEV.fl_is_playing = False
        _toggle_playing(False)
        scene.scoresync_status = "Stop"
        _log_event("RX stop")
        return True

    if t == "spp":
        DEV.last_any_ts = DEV.last_spp_ts = DEV.last_fl_spp_ts = time.time()
        spp_units = int(msg.get("position", 0))

        fps = float(scene.render.fps or 30) / float(scene.render.fps_base or 1.0)
        bpm = _get_bpm(scene)

        beats = float(spp_units) / 4.0
        seconds = beats * (60.0 / bpm)
        frame = int(seconds * fps)

        scene.frame_current = max(0, frame)
        DEV.frame_origin = int(scene.frame_current)
        DEV.frame_accum_f = 0.0
        DEV.clock_total = 0
        DEV.clocks_in_bar = 0
        DEV.bar_index = 1
        scene.scoresync_status = f"SPP -> frame {frame}"
        _log_event("RX spp", f"spp={spp_units} frame={frame} bpm={bpm:.1f}")
        return True



    if t == "clock":
        # Use the arrival timestamp from the listener thread for accurate BPM.
        # Falling back to time.time() only if the message predates the ts field.
        now = msg.get("ts") or time.time()
        wall = time.time()

        # Debug: print effective clock rate about once per second
        if getattr(scene, "scoresync_debug", False):
            if DEV.clock_dbg_ts <= 0.0:
                DEV.clock_dbg_ts = wall
                DEV.clock_dbg_count = 0
            DEV.clock_dbg_count += 1
            if (wall - DEV.clock_dbg_ts) >= 1.0:
                hz = DEV.clock_dbg_count / (wall - DEV.clock_dbg_ts)
                print(f"[ScoreSync CLOCK] ~{hz:.1f} msgs/sec  follow_clock={getattr(scene,'scoresync_follow_clock',True)}")
                DEV.clock_dbg_ts = wall
                DEV.clock_dbg_count = 0

        prev_ts = DEV.last_clock_ts
        DEV.last_any_ts = wall
        DEV.last_clock_ts = now   # store arrival ts for next dt

        if not getattr(scene, "scoresync_follow_clock", True):
            return True  # user disabled

        # BPM estimate from MIDI clock (24 ticks per quarter note → 60/24 = 2.5)
        if prev_ts > 0:
            dt = now - prev_ts
            if 0.01 < dt < 0.08:   # valid range: ~750–6000 BPM guard; realistically 0.02–0.05
                inst_bpm = 2.5 / dt
                if DEV.bpm_ema <= 0.0:
                    DEV.bpm_ema = inst_bpm
                else:
                    DEV.bpm_ema = DEV.bpm_alpha * inst_bpm + (1 - DEV.bpm_alpha) * DEV.bpm_ema
                scene.scoresync_bpm_estimate = float(DEV.bpm_ema)

        bpm = DEV.bpm_ema if DEV.bpm_ema > 0 else 120.0
        fps = float(scene.render.fps or 30) / float(scene.render.fps_base or 1.0)
        frames_per_clock = (fps * 60.0) / (bpm * 24.0)
        DEV.frame_accum_f += frames_per_clock
        advance = int(DEV.frame_accum_f)
        if advance:
            DEV.frame_accum_f -= advance
            # -- IMPORTANT: accumulate
            DEV.frame_origin += advance         
            scene.frame_current = max(0, DEV.frame_origin)

        DEV.clock_total += 1
        DEV.clocks_in_bar += 1
        _add_marker_if_needed(scene)
        scene.scoresync_status = "Clock"
        return True

    # ---- MIDI Program Change → bank switch (v2.0) ----
    if t == "program_change":
        try:
            from .ops_sampler import ingest_pc_for_sampler
            ingest_pc_for_sampler(
                int(msg.get("channel", 0)),
                int(msg.get("program", 0)),
                scene,
            )
        except Exception:
            pass
        return True

    # ---- Visual Sampler + FX trigger (v2.0) ----
    if t == "note_on":
        ch       = int(msg.get("channel",  0))
        note     = int(msg.get("note",     0))
        velocity = int(msg.get("velocity", 0))
        if velocity > 0:
            try:
                from .ops_sampler import ingest_note_for_sampler, DEV_SAMPLER, load_cache
                if not DEV_SAMPLER.cache:
                    DEV_SAMPLER.cache = load_cache()
                ingest_note_for_sampler(ch, note, velocity, scene)
            except Exception:
                pass
            try:
                from .ops_fx import handle_note_on_fx
                handle_note_on_fx(ch, note, velocity, scene)
            except Exception:
                pass
        return True

    if t == "note_off":
        ch   = int(msg.get("channel", 0))
        note = int(msg.get("note",    0))
        try:
            from .ops_fx import handle_note_off_fx
            handle_note_off_fx(ch, note, scene)
        except Exception:
            pass
        return True

    if t == "error":
        scene.scoresync_status = f"Error: {msg.get('err','')}"

        return True

    return True

# ---- Timer ------------------------------------------------------------------
def scoresync_timer():
    scene = bpy.context.scene
    if scene is None:
        return 0.2

    # Stronger auto-retry
    _ensure_ports(scene)

    
    # Drain queue (prioritize transport/SPP over clock)
    n = 0

    with _QLOCK:
        # If backlog grows, drop old clock ticks first (keep newest clocks)
        if len(_message_queue) > 256:
            clocks_kept = 0
            new_q = []
            for ts, msg in reversed(_message_queue):
                t = msg.get("type")
                if t == "clock":
                    if clocks_kept < 64:
                        new_q.append((ts, msg))
                        clocks_kept += 1
                else:
                    new_q.append((ts, msg))
            _message_queue[:] = list(reversed(new_q))

        while _message_queue and n < 64:
            ts, msg = _message_queue[0]
            if _apply_incoming(scene, ts, msg):
                _message_queue.pop(0)
            else:
                break
            n += 1


    # ---- MIDI Mapping apply tick (v2.0) ----
    try:
        from .ops_mapping import apply_mappings_tick
        apply_mappings_tick(scene)
    except Exception:
        pass

    # ---- FX Rack apply tick (v2.0) ----
    try:
        from .ops_fx import apply_fx_tick
        apply_fx_tick(scene)
    except Exception:
        pass

    # Update master status string for the UI
    try:
        master_mode = getattr(scene, "scoresync_master_mode", "AUTO")
        if master_mode == "FL":
            scene.scoresync_master_status = "FL (locked)"
        elif master_mode == "BLENDER":
            scene.scoresync_master_status = "Blender (locked)"
        elif _blender_is_master():
            remaining = max(0.0, DEV.master_until_ts - time.time())
            scene.scoresync_master_status = f"Blender ({remaining:.1f}s)"
        elif DEV.fl_is_playing:
            scene.scoresync_master_status = "FL (playing)"
        else:
            scene.scoresync_master_status = "FL (idle)"
    except Exception:
        pass

    # Update LED (🟢/🟡/🔴)
    # keep FL Script OK visible for 10s after last ACK
    try:
        if scene.scoresync_script_ok and (time.time() - scene.scoresync_script_ok_ts) < 10.0:
            scene.scoresync_led_text = "🟢 FL Script OK"
            return 0.10
    except Exception:
        pass

    _update_led(scene)
    return 0.10  # ~10 Hz

# ---- Listener thread --------------------------------------------------------
def _listener_loop(port_name, gen):
    """Background MIDI input thread. DO NOT touch bpy data directly here."""
    mido = _get_mido()
    if not mido:
        _enqueue({"type":"error","err":"mido not available"})
        return
    try:
        DEV.listener_running = True
        with mido.open_input(port_name) as inport:
            print("[ScoreSync] MIDI In opened:", port_name)

            DEV.in_port = inport
            for msg in inport:
                scene = bpy.context.scene  # safe-ish for reads; don't write bpy data here

                if msg.type in ("start", "stop", "continue", "songpos"):
                    _dbg(scene, f"[ScoreSync RX] {msg.type}   raw={msg}", 0.0)

                if msg.type == "clock":
                    # count clocks and print once per second
                    now = time.time()
                    if DEV.dbg_clock_ts <= 0.0:
                        DEV.dbg_clock_ts = now
                        DEV.dbg_clock_count = 0
                    DEV.dbg_clock_count += 1
                    if (now - DEV.dbg_clock_ts) >= 1.0:
                        hz = DEV.dbg_clock_count / (now - DEV.dbg_clock_ts)
                        _dbg(scene, f"[ScoreSync RX] clock rate ~{hz:.1f}/sec", 0.0)
                        DEV.dbg_clock_ts = now
                        DEV.dbg_clock_count = 0

                if DEV.stop_requested or gen != _LISTENER_GEN:
                    break


                # ---- FL script health echo (ACK) ----
                if msg.type == "control_change" and msg.control == 119 and msg.value == 100:
                    _enqueue({"type": "health_ok"})
                    continue  # done with this msg

                # debug (prints but does not consume)
                if msg.type == "control_change" and msg.control == 119:
                    print("[ScoreSync] IN CC:", msg.control, msg.value)

                # ---- MIDI Mapping Layer + FX Rack (v2.0) ----
                if msg.type == "control_change":
                    try:
                        from .ops_mapping import ingest_midi_for_mapping
                        ingest_midi_for_mapping("CC", msg.channel, msg.control, msg.value)
                    except Exception:
                        pass
                    try:
                        from .ops_fx import capture_fx_learn
                        capture_fx_learn("CC", msg.channel, msg.control)
                    except Exception:
                        pass

                elif msg.type == "note_on":
                    try:
                        from .ops_mapping import ingest_midi_for_mapping
                        ingest_midi_for_mapping("NOTE_ON", msg.channel, msg.note, msg.velocity)
                    except Exception:
                        pass
                    try:
                        from .ops_fx import capture_fx_learn
                        capture_fx_learn("NOTE_ON", msg.channel, msg.note)
                    except Exception:
                        pass
                    # Enqueue for sampler + FX (must fire on main thread)
                    _enqueue({"type": "note_on", "channel": msg.channel,
                              "note": msg.note, "velocity": msg.velocity})

                elif msg.type == "note_off":
                    _enqueue({"type": "note_off", "channel": msg.channel,
                              "note": msg.note})

                elif msg.type == "program_change":
                    _enqueue({"type": "program_change", "channel": msg.channel,
                              "program": msg.program})

                # Transport
                if msg.type in ("start", "stop", "continue"):
                    _enqueue({"type": msg.type})

                # Song Position Pointer (14-bit)
                elif msg.type == "songpos":
                    _enqueue({"type": "spp", "position": msg.pos})

                # MIDI clock — include arrival timestamp for accurate BPM estimation
                elif msg.type == "clock":
                    _enqueue({"type": "clock", "ts": time.time()})

                # ignore other messages
    except Exception as e:
        _enqueue({"type":"error","err":f"MIDI In open failed ({port_name}): {e}"})

    finally:
        DEV.listener_running = False
        DEV.in_port = None

def _health_listener_loop(port_name):
    #"""Listen only for FL ACK CC119=100 on a second MIDI input."""
    mido = _get_mido()
    if not mido:
        return
    try:
        DEV.health_listener_running = True
        with mido.open_input(port_name) as inport:
            DEV.health_in_port = inport
            print("[ScoreSync] Health In opened:", port_name)
            for msg in inport:
                if DEV.health_stop_requested:
                    break

                # FL script ACK
                if msg.type == "control_change" and msg.control == 119 and msg.value == 100:
                    _enqueue({"type": "health_ok"})
    except Exception as e:
        print("[ScoreSync] Health In failed:", e)
    finally:
        DEV.health_listener_running = False
        DEV.health_in_port = None


# ---- Operators --------------------------------------------------------------
class SCORESYNC_OT_refresh_ports(bpy.types.Operator):
    bl_idname = "scoresync.refresh_ports"
    bl_label = "Refresh MIDI Ports"
    def execute(self, context):
        for area in context.screen.areas:
            area.tag_redraw()
        self.report({'INFO'}, "Ports refreshed")
        return {'FINISHED'}

class SCORESYNC_OT_connect(bpy.types.Operator):
    bl_idname = "scoresync.connect"
    bl_label = "(Re)Connect MIDI"
    _thread = None
    def execute(self, context):
        scene = context.scene
        mido = _get_mido()
        if not mido:
            scene.scoresync_status = "Deps missing (Install MIDI Dependencies)"
            self.report({'WARNING'}, "Install dependencies first (mido + python-rtmidi)")
            return {'CANCELLED'}

        in_name = getattr(scene, "scoresync_input_port", "NONE")
        out_name = getattr(scene, "scoresync_output_port", "NONE")

        # Close previous out
        try:
            if DEV.out_port:
                DEV.out_port.close()
        except Exception:
            pass
        DEV.out_port = None
        DEV.out_port_name = None

        # Open output
        if out_name and out_name != "NONE":
            try:
                DEV.out_port = mido.open_output(out_name)
                DEV.out_port_name = out_name
                print("[ScoreSync] MIDI Out opened:", out_name)
                # Start a second input listener on the OUT port name (for FL ACK)
                try:
                    inputs = set(mido.get_input_names())
                except Exception:
                    inputs = set()
                DEV.health_stop_requested = True
                try:
                    if DEV.health_in_port:
                        DEV.health_in_port.close()
                except Exception:
                    pass
                DEV.health_in_port = None
                DEV.health_stop_requested = False


                # If the OUT port name exists as an input too (loopMIDI does this),
                # listen there for CC119=100 so Blender can show "FL Script OK".
                if out_name in inputs and (not DEV.health_listener_running):
                    DEV.health_stop_requested = True
                    try:
                        if DEV.health_in_port:
                            DEV.health_in_port.close()
                    except Exception:
                        pass
                    time.sleep(0.02)
                    DEV.health_stop_requested = False
                    DEV.health_port_name = out_name
                    threading.Thread(
                        target=_health_listener_loop,
                        args=(out_name,),
                        daemon=True
                    ).start()

                # show immediate confirmation in the ui
                scene.scoresync_status = f"Out opened: {out_name} (pick MIDI In to follow DAW)"

            except Exception as e:
                DEV.out_port = None
                scene.scoresync_status = f"Error: failed to open MIDI Out '{out_name}': {e}"
                



        # Start input listener
        DEV.in_port_name = None
        if in_name and in_name != "NONE":
            DEV.in_port_name = in_name
            # stop any previous listener cleanly
            DEV.stop_requested = True
            try:
                if DEV.in_port:
                    DEV.in_port.close()
            except Exception:
                pass
            time.sleep(0.05)
            DEV.stop_requested = False

            DEV.frame_origin = int(scene.frame_current)
            DEV.frame_accum_f = 0.0
            DEV.clock_total = 0
            DEV.clocks_in_bar = 0
            DEV.bar_index = 1
            global _LISTENER_GEN
            _LISTENER_GEN += 1
            gen = _LISTENER_GEN

            self._thread = threading.Thread(
                target=_listener_loop,
                args=(in_name, gen),
                daemon=True
            )
            self._thread.start()
            scene.scoresync_status = f"In: {in_name} | Out: {DEV.out_port_name or 'none'}"

        else:
            scene.scoresync_status = f"In: {in_name} | Out: {DEV.out_port_name or 'none'}"
            self.report({'WARNING'}, "Pick a MIDI In for DAW → Blender listening")

        # Persist port names so they can be restored next session
        try:
            from .prefs import save_last_ports
            save_last_ports(in_name, DEV.out_port_name or "")
        except Exception:
            pass

        # Ensure timer
        if not DEV.timer_registered:
            try:
                bpy.app.timers.register(scoresync_timer, first_interval=0.2)
                DEV.timer_registered = True
            except Exception:
                pass

        return {'FINISHED'}

class SCORESYNC_OT_reconnect_now(bpy.types.Operator):
    bl_idname = "scoresync.reconnect_now"
    bl_label = "Reconnect now"
    def execute(self, context):
        try:
            if DEV.out_port:
                DEV.out_port.close()
        except Exception:
            pass
        DEV.out_port = None
        DEV.health_stop_requested = True
        try:
            if DEV.health_in_port:
                DEV.health_in_port.close()
        except Exception:
            pass
        DEV.health_in_port = None
        DEV.listener_running = False
        self.report({'INFO'}, "Reconnecting…")
        bpy.ops.scoresync.connect()
        return {'FINISHED'}
