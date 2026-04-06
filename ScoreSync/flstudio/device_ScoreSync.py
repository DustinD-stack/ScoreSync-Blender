# name= ScoreSync
# supportedDevices=ScoreSync

# ScoreSync – FL follow for SPP/MTC + transport
# Put this file in:
# C:\Users\<you>\Documents\Image-Line\FL Studio\Settings\Hardware\ScoreSync\device_ScoreSync.py
#
# (This copy is bundled inside the Blender addon for easy export via
#  the "Export FL Script" button in the ScoreSync panel → Tools section.)

import midi
import transport
import ui
import time



# ---------- settings ----------
PPQ = 96          # SPP -> ticks estimate (only used if setSongPosPPQ exists)
USE_MTC = False    # smooth-ish scrub (approx), final land via SPP is best
DEBUG = False      # Set True to log every MIDI message to FL's console (verbose)

# Probe echo (Blender health check)
MAGIC_CC  = 119
MAGIC_REQ = 7     # Blender -> FL
MAGIC_ACK = 100    # FL -> Blender

# ---------- internal state ----------
_last_ping = 0.0
_last_qf = [0] * 8
_have_qf = [False] * 8
_ready = False
_last_locate = 0.0


def _send_cc(ctrl, val, ch=0):
    try:
        status = (midi.MIDI_CONTROLCHANGE | (ch & 0x0F))  # 0xB0 + channel
        midi.OutMsg(status, ctrl & 0x7F, val & 0x7F)
    except Exception:
        pass


def _heartbeat():
    global _last_ping
    now = time.time()
    if now - _last_ping >= 1.0:   # 1 second
        _send_cc(MAGIC_CC, MAGIC_ACK, 0)
        _last_ping = now

def OnIdle():
    if _ready:
        _heartbeat()


def _locate_ticks_from_spp(spp_units):
    # SPP unit = 1/16 note; quarter note = 4 SPP units
    return int(spp_units * (PPQ / 4.0))


def _apply_locate_ticks(ticks):
    # Try PPQ ticks first (newer FL), fallback to beats
    try:
        transport.setSongPosPPQ(ticks)
        return True
    except Exception:
        pass
    try:
        beats = ticks / float(PPQ)
        transport.setSongPos(beats)
        return True
    except Exception:
        pass
    return False


def _apply_locate_from_spp(spp_units):
    return _apply_locate_ticks(_locate_ticks_from_spp(spp_units))


def _apply_play():
    try:
        transport.globalTransport(midi.FPT_Play, 1)
    except Exception:
        pass


def _apply_stop():
    try:
        transport.globalTransport(midi.FPT_Stop, 1)
    except Exception:
        pass


def _apply_continue():
    try:
        transport.globalTransport(midi.FPT_Play, 1)
    except Exception:
        pass


def OnInit():
    global _ready
    _ready = True
    ui.setHintMsg("ScoreSync script loaded ✅ (SPP/MTC ready)")
    print("### ScoreSync script loaded ###")
    print("### ScoreSync OnInit confirmed ###")

def OnDeInit():
    global _ready
    _ready = False


def OnMidiMsg(event):
    global _last_qf, _have_qf, _last_locate

    status = event.status

    # DEBUG: verbose message log (set DEBUG=True at top of file to enable)
    if DEBUG and status in (midi.MIDI_SONGPOS, midi.MIDI_START, midi.MIDI_STOP, midi.MIDI_CONTINUE, midi.MIDI_CLOCK) or (DEBUG and ((status & 0xF0) == midi.MIDI_CONTROLCHANGE)):
        try:
            print("ScoreSync OnMidiMsg:", hex(status), "d1=", event.data1, "d2=", event.data2)
        except Exception:
            pass

    # Ignore high-rate realtime spam (prevents overflow)
    if status in (midi.MIDI_CLOCK, midi.MIDI_ACTIVE_SENSING):
        event.handled = True
        return

    # Probe echo
    if (status & 0xF0) == midi.MIDI_CONTROLCHANGE:
        if event.data1 == MAGIC_CC and event.data2 == MAGIC_REQ:
            _send_cc(MAGIC_CC, MAGIC_ACK, 0)
            ui.setHintMsg("ScoreSync: probe ✅  ACK sent to Blender")
            event.handled = True
            return

    # Transport
    if status == midi.MIDI_START:
        _apply_play()
        ui.setHintMsg("ScoreSync: START from Blender ▶")
        event.handled = True
        return
    if status == midi.MIDI_CONTINUE:
        _apply_continue()
        ui.setHintMsg("ScoreSync: CONTINUE from Blender ▶")
        event.handled = True
        return
    if status == midi.MIDI_STOP:
        _apply_stop()
        ui.setHintMsg("ScoreSync: STOP from Blender ■")
        event.handled = True
        return

    # SPP locate (throttled) — ignored while FL is playing (FL is master)
    if status == midi.MIDI_SONGPOS:
        try:
            if transport.isPlaying():
                event.handled = True
                return
        except Exception:
            pass
        now = time.time()
        if now - _last_locate < 0.03:
            event.handled = True
            return
        _last_locate = now

        spp_units = (event.data2 << 7) | event.data1
        ok = _apply_locate_from_spp(spp_units)

        try:
            if ok:
                ui.setHintMsg(f"ScoreSync: SPP {spp_units} → locate OK ✅")
            else:
                ui.setHintMsg(f"ScoreSync: SPP {spp_units} → locate FAILED ❌")
            if DEBUG:
                print("SPP locate", spp_units, "OK" if ok else "FAIL")
        except Exception:
            pass

        event.handled = True
        return

    # MTC (optional, throttled)
    if USE_MTC and status == midi.MIDI_QFRAME:
        now = time.time()
        if now - _last_locate < 0.03:
            event.handled = True
            return
        _last_locate = now

        ft = (event.data1 >> 4) & 0x07
        val = event.data1 & 0x0F
        _last_qf[ft] = val
        _have_qf[ft] = True

        if all(_have_qf):
            ff = (_last_qf[1] << 4) | _last_qf[0]
            ss = (_last_qf[3] << 4) | _last_qf[2]
            mm = (_last_qf[5] << 4) | _last_qf[4]
            hh_low = _last_qf[6] & 0x0F
            hh_high = _last_qf[7] & 0x01
            hh = (hh_high << 4) | hh_low

            fps_flag = (_last_qf[7] >> 1) & 0x03
            fps = 24 if fps_flag == 0 else (25 if fps_flag == 1 else 30)

            total_seconds = (hh * 3600) + (mm * 60) + ss + (ff / float(fps))
            beats_approx = total_seconds * 2.0
            ticks = int(beats_approx * PPQ)
            _apply_locate_ticks(ticks)
            _have_qf = [False] * 8

        event.handled = True
        return
