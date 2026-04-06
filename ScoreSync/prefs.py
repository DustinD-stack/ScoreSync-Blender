"""
ScoreSync — Addon preferences and preset system (v0.7.0)

AddonPreferences stores port names that persist across Blender sessions.
BUILTIN_PRESETS defines the three canned configurations.
"""

import bpy

ADDON_NAME = __name__.split(".")[0]   # "ScoreSync"

# ── Built-in presets ──────────────────────────────────────────────────────────
# Each entry is a dict of {scene_prop_name: value} to apply.
BUILTIN_PRESETS = {
    "FL_FOLLOW": {
        "label": "FL Follow",
        "description": "FL Studio drives everything. Blender follows clock + transport only.",
        "props": {
            "scoresync_master_mode":       "FL",
            "scoresync_duplex_mode":       "OFF",
            "scoresync_follow_clock":      True,
            "scoresync_reset_on_start":    True,
            "scoresync_duplex_use_mtc":    False,
        },
    },
    "BLENDER_ASSIST": {
        "label": "Blender Assist",
        "description": "Auto mode: FL leads when playing; scrubbing Blender nudges FL when stopped.",
        "props": {
            "scoresync_master_mode":       "AUTO",
            "scoresync_duplex_mode":       "ASSIST",
            "scoresync_follow_clock":      True,
            "scoresync_reset_on_start":    True,
            "scoresync_master_hold_ms":    2000,
            "scoresync_duplex_rate_hz":    20,
            "scoresync_duplex_debounce_ms": 140,
            "scoresync_duplex_use_mtc":    False,
        },
    },
    "AUTO_MASTER": {
        "label": "Auto Master",
        "description": "Like Blender Assist but with a longer hold and faster scrub rate.",
        "props": {
            "scoresync_master_mode":       "AUTO",
            "scoresync_duplex_mode":       "ASSIST",
            "scoresync_follow_clock":      True,
            "scoresync_reset_on_start":    False,
            "scoresync_master_hold_ms":    4000,
            "scoresync_duplex_rate_hz":    30,
            "scoresync_duplex_debounce_ms": 100,
            "scoresync_duplex_use_mtc":    False,
        },
    },
}


# ── AddonPreferences ──────────────────────────────────────────────────────────
class ScoreSyncPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_NAME

    last_in_port: bpy.props.StringProperty(
        name="Last MIDI In",
        default="",
        description="Port name remembered from the last successful connect",
    )
    last_out_port: bpy.props.StringProperty(
        name="Last MIDI Out",
        default="",
        description="Port name remembered from the last successful connect",
    )
    auto_connect: bpy.props.BoolProperty(
        name="Auto-connect on startup",
        default=True,
        description="Automatically (re)connect last ports when Blender starts or a file loads",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Remembered ports (updated on each successful connect):")
        layout.prop(self, "last_in_port")
        layout.prop(self, "last_out_port")
        layout.prop(self, "auto_connect")


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_prefs() -> ScoreSyncPreferences | None:
    try:
        return bpy.context.preferences.addons[ADDON_NAME].preferences
    except Exception:
        return None


def save_last_ports(in_name: str, out_name: str):
    p = get_prefs()
    if p is None:
        return
    if in_name and in_name != "NONE":
        p.last_in_port = in_name
    if out_name and out_name != "NONE":
        p.last_out_port = out_name


def get_last_ports() -> tuple[str, str]:
    p = get_prefs()
    if p is None:
        return ("", "")
    return (p.last_in_port or "", p.last_out_port or "")


def apply_preset(scene, preset_key: str) -> bool:
    """Apply a built-in preset to scene. Returns True on success."""
    preset = BUILTIN_PRESETS.get(preset_key)
    if preset is None:
        return False
    for prop, value in preset["props"].items():
        try:
            setattr(scene, prop, value)
        except Exception:
            pass
    return True
