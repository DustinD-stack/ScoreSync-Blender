"""
ScoreSync v2 — ops_sampler.py
Visual sampler: pad banks, sample cache, MIDI trigger engine.

Concepts
--------
Bank    — collection of N pads (default 16, templated as 4×4)
Pad     — one sample slot: points to a clip source + playback settings
Sample  — a frame range or video file baked into the cache database
Trigger — MIDI Note On fires a pad; velocity optionally maps to intensity

Output modes (per-pad)
  VSE   — creates/moves a Movie/Image strip in the Video Sequence Editor
  MAT   — drives an Image Texture node on the active material of a target object
  BOTH  — does both

Cache database
  Stored as a JSON file alongside the .blend file (or user-chosen path).
  Each entry: {id, label, source_type, source_path, frame_start, frame_end,
               fps, thumbnail_path, bank, pad}

Data model (Blender CollectionProperty on scene)
  scene.scoresync_banks  → list of SamplerBank
    bank.pads            → list of SamplerPad
      pad.sample_id      → key into the cache DB
      pad.note           → MIDI note (0-127)
      pad.channel        → MIDI channel (0-15)
      pad.output_mode    → VSE | MAT | BOTH
      pad.vse_channel    → VSE channel to use
      pad.mat_target     → object name for material output
      pad.velocity_to_alpha → bool
      pad.color          → UI pad color (RGBA)
      pad.label          → short name shown on pad
"""

import bpy
import json
import os
import time

# ── Runtime trigger state ─────────────────────────────────────────────────────
class _SamplerState:
    # {(channel, note): {"bank": int, "pad": int, "velocity": int, "ts": float}}
    active_triggers: dict = {}
    # Loaded cache: {sample_id: {meta dict}}
    cache: dict = {}
    cache_path: str = ""
    cache_dirty: bool = False

DEV_SAMPLER = _SamplerState()

_DEFAULT_PADS = 16   # 4×4 template
_DEFAULT_BANKS = 4


# ── Cache helpers ─────────────────────────────────────────────────────────────
def _default_cache_path() -> str:
    blend = bpy.data.filepath
    if blend:
        return os.path.splitext(blend)[0] + "_scoresync_cache.json"
    return os.path.join(os.path.expanduser("~"), "scoresync_cache.json")


def load_cache(path: str = "") -> dict:
    p = path or _default_cache_path()
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {entry["id"]: entry for entry in data.get("samples", [])}
    except Exception:
        return {}


def save_cache(cache: dict, path: str = ""):
    p = path or _default_cache_path()
    doc = {"version": 1, "samples": list(cache.values())}
    try:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
    except Exception as e:
        print(f"[ScoreSync Sampler] Cache save failed: {e}")


def _next_sample_id(cache: dict) -> str:
    existing = {int(k.split("_")[-1]) for k in cache if k.startswith("smp_")}
    n = 0
    while n in existing:
        n += 1
    return f"smp_{n:04d}"


# ── Output engines ────────────────────────────────────────────────────────────
def _trigger_vse(scene, pad, sample: dict, velocity: int):
    """Place or update a strip in the VSE for this pad's sample."""
    fps = scene.render.fps / (scene.render.fps_base or 1.0)
    frame_start = scene.frame_current
    src_type = sample.get("source_type", "MOVIE")
    src_path = sample.get("source_path", "")
    s_start  = int(sample.get("frame_start", 1))
    s_end    = int(sample.get("frame_end",   250))
    duration = max(1, s_end - s_start)
    ch       = max(1, int(pad.vse_channel))

    if not scene.sequence_editor:
        scene.sequence_editor_create()
    seq = scene.sequence_editor

    # Remove existing strip on same channel/frame to avoid overlap
    to_remove = [s for s in seq.sequences_all
                 if s.channel == ch and s.frame_final_start == frame_start]
    for s in to_remove:
        seq.sequences.remove(s)

    try:
        if src_type == "IMAGE_SEQUENCE":
            # directory + wildcard
            directory = os.path.dirname(src_path)
            filename  = os.path.basename(src_path)
            strip = seq.sequences.new_image(
                name=pad.label or "SyncPad",
                filepath=src_path,
                channel=ch,
                frame_start=frame_start,
            )
            strip.frame_final_end = frame_start + duration
        else:
            strip = seq.sequences.new_movie(
                name=pad.label or "SyncPad",
                filepath=src_path,
                channel=ch,
                frame_start=frame_start,
            )
            strip.frame_final_end = frame_start + duration

        if pad.velocity_to_alpha:
            strip.blend_alpha = velocity / 127.0

    except Exception as e:
        print(f"[ScoreSync Sampler] VSE trigger failed: {e}")


def _trigger_mat(scene, pad, sample: dict, velocity: int):
    """Set an Image Texture node on the target object's active material."""
    obj = bpy.data.objects.get(pad.mat_target)
    if obj is None:
        obj = getattr(bpy.context, "active_object", None)
    if obj is None or not obj.material_slots:
        return
    mat = obj.active_material
    if mat is None or not mat.use_nodes:
        return

    src_path = sample.get("source_path", "")
    if not src_path:
        return

    # Find or create an Image Texture node
    tree = mat.node_tree
    img_node = next((n for n in tree.nodes if n.type == "TEX_IMAGE"), None)
    if img_node is None:
        img_node = tree.nodes.new("ShaderNodeTexImage")

    # Load or reuse image datablock
    img = bpy.data.images.get(os.path.basename(src_path))
    if img is None:
        try:
            img = bpy.data.images.load(src_path)
        except Exception as e:
            print(f"[ScoreSync Sampler] Image load failed: {e}")
            return
    img_node.image = img

    # Velocity → diffuse mix if there's a Principled node
    if pad.velocity_to_alpha:
        alpha = velocity / 127.0
        princ = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if princ:
            princ.inputs["Alpha"].default_value = alpha


# ── Trigger engine (called from main-thread timer) ────────────────────────────
def fire_pad(scene, bank_idx: int, pad_idx: int, velocity: int):
    """Fire a pad: load sample from cache and route to output(s)."""
    banks = getattr(scene, "scoresync_banks", None)
    if banks is None or bank_idx >= len(banks):
        return
    bank = banks[bank_idx]
    if pad_idx >= len(bank.pads):
        return
    pad = bank.pads[pad_idx]
    if not pad.sample_id:
        return

    sample = DEV_SAMPLER.cache.get(pad.sample_id)
    if sample is None:
        print(f"[ScoreSync Sampler] Sample {pad.sample_id!r} not in cache")
        return

    mode = pad.output_mode
    if mode in ("VSE", "BOTH"):
        _trigger_vse(scene, pad, sample, velocity)
    if mode in ("MAT", "BOTH"):
        _trigger_mat(scene, pad, sample, velocity)

    DEV_SAMPLER.active_triggers[(pad.channel, pad.note)] = {
        "bank": bank_idx, "pad": pad_idx,
        "velocity": velocity, "ts": time.time(),
    }


def ingest_pc_for_sampler(channel: int, program: int, scene=None):
    """
    Called from main-thread timer when a MIDI Program Change arrives.
    Switches the active bank if PC→Bank Switch is enabled and the channel matches.
    """
    sc = scene or (bpy.context.scene if bpy.context else None)
    if sc is None:
        return
    if not getattr(sc, "scoresync_sampler_pc_switch", False):
        return
    pc_ch = int(getattr(sc, "scoresync_sampler_pc_channel", 0))
    if channel != pc_ch:
        return
    banks = getattr(sc, "scoresync_banks", None)
    if banks is None:
        return
    target = max(0, min(program, len(banks) - 1))
    sc.scoresync_active_bank = target
    print(f"[ScoreSync Sampler] PC {program} → bank {target}")


def ingest_note_for_sampler(channel: int, note: int, velocity: int, scene=None):
    """
    Called from ops_connection listener (via _enqueue / apply path).
    Finds matching pad across active bank and fires it.
    """
    sc = scene or (bpy.context.scene if bpy.context else None)
    if sc is None:
        return
    active_bank_idx = getattr(sc, "scoresync_active_bank", 0)
    banks = getattr(sc, "scoresync_banks", None)
    if banks is None or active_bank_idx >= len(banks):
        return
    bank = banks[active_bank_idx]
    for pad_idx, pad in enumerate(bank.pads):
        if pad.channel == channel and pad.note == note and pad.enabled:
            if velocity > 0:
                fire_pad(sc, active_bank_idx, pad_idx, velocity)
            break


# ── Property groups ───────────────────────────────────────────────────────────
class SamplerPad(bpy.types.PropertyGroup):
    label          : bpy.props.StringProperty(name="Label", default="")
    enabled        : bpy.props.BoolProperty(name="Enabled", default=True)
    note           : bpy.props.IntProperty(name="Note", default=0, min=0, max=127)
    channel        : bpy.props.IntProperty(name="Channel", default=0, min=0, max=15)
    sample_id      : bpy.props.StringProperty(name="Sample ID", default="")
    output_mode    : bpy.props.EnumProperty(
        name="Output",
        items=[
            ("VSE",  "VSE",  "Video Sequence Editor strip"),
            ("MAT",  "Material", "Image Texture on object material"),
            ("BOTH", "Both", "VSE + Material"),
        ],
        default="VSE",
    )
    vse_channel    : bpy.props.IntProperty(name="VSE Ch", default=1, min=1, max=128)
    mat_target     : bpy.props.StringProperty(name="Object", default="")
    velocity_to_alpha: bpy.props.BoolProperty(name="Velocity → Alpha", default=False)
    color          : bpy.props.FloatVectorProperty(
        name="Color", subtype='COLOR', size=4,
        default=(0.2, 0.2, 0.8, 1.0), min=0.0, max=1.0,
    )


class SamplerBank(bpy.types.PropertyGroup):
    name           : bpy.props.StringProperty(name="Bank Name", default="Bank")
    pads           : bpy.props.CollectionProperty(type=SamplerPad)
    pad_count      : bpy.props.IntProperty(name="Pads", default=16, min=1, max=64)


# ── Operators ─────────────────────────────────────────────────────────────────
class SCORESYNC_OT_sampler_add_bank(bpy.types.Operator):
    bl_idname = "scoresync.sampler_add_bank"
    bl_label  = "Add Bank"
    bl_description = "Add a new pad bank (16 pads, 4×4 template)"

    pad_count: bpy.props.IntProperty(name="Pads", default=_DEFAULT_PADS, min=1, max=64)

    def execute(self, context):
        scene = context.scene
        bank = scene.scoresync_banks.add()
        bank.name = f"Bank {len(scene.scoresync_banks)}"
        bank.pad_count = self.pad_count
        # Pre-populate pads with sequential notes starting from C3 (note 48)
        base_note = 36  # C2
        for i in range(self.pad_count):
            pad = bank.pads.add()
            pad.label = f"Pad {i+1}"
            pad.note  = (base_note + i) % 128
            # Colour by row (4 per row)
            row = i // 4
            colours = [
                (0.8, 0.2, 0.2, 1.0),
                (0.2, 0.8, 0.2, 1.0),
                (0.2, 0.2, 0.8, 1.0),
                (0.8, 0.8, 0.2, 1.0),
            ]
            pad.color = colours[row % len(colours)]
        scene.scoresync_active_bank = len(scene.scoresync_banks) - 1
        self.report({'INFO'}, f"Added bank '{bank.name}' with {self.pad_count} pads")
        return {'FINISHED'}


class SCORESYNC_OT_sampler_remove_bank(bpy.types.Operator):
    bl_idname = "scoresync.sampler_remove_bank"
    bl_label  = "Remove Bank"

    def execute(self, context):
        scene = context.scene
        idx = scene.scoresync_active_bank
        if 0 <= idx < len(scene.scoresync_banks):
            scene.scoresync_banks.remove(idx)
            scene.scoresync_active_bank = max(0, idx - 1)
        return {'FINISHED'}


class SCORESYNC_OT_sampler_sample_from_timeline(bpy.types.Operator):
    bl_idname  = "scoresync.sampler_sample_from_timeline"
    bl_label   = "Sample from Timeline"
    bl_description = "Bake the current frame range (Start→End) as a sample entry"

    pad_index: bpy.props.IntProperty(default=0)
    label    : bpy.props.StringProperty(name="Sample Label", default="")

    def execute(self, context):
        scene = context.scene
        bank_idx = scene.scoresync_active_bank
        banks = scene.scoresync_banks
        if bank_idx >= len(banks):
            self.report({'WARNING'}, "No active bank.")
            return {'CANCELLED'}
        bank = banks[bank_idx]
        if self.pad_index >= len(bank.pads):
            self.report({'WARNING'}, "Pad index out of range.")
            return {'CANCELLED'}

        # Reload cache from disk
        if not DEV_SAMPLER.cache:
            DEV_SAMPLER.cache = load_cache()

        sample_id = _next_sample_id(DEV_SAMPLER.cache)
        label = self.label or f"Sample {len(DEV_SAMPLER.cache)+1}"

        entry = {
            "id":          sample_id,
            "label":       label,
            "source_type": "RENDER",       # rendered frame range
            "source_path": bpy.data.filepath,
            "frame_start": scene.frame_start,
            "frame_end":   scene.frame_end,
            "fps":         scene.render.fps,
            "bank":        bank_idx,
            "pad":         self.pad_index,
            "thumbnail_path": "",
        }
        DEV_SAMPLER.cache[sample_id] = entry
        DEV_SAMPLER.cache_dirty = True
        save_cache(DEV_SAMPLER.cache)

        # Assign to pad
        pad = bank.pads[self.pad_index]
        pad.sample_id = sample_id
        pad.label     = label

        self.report({'INFO'}, f"Sampled '{label}' ({scene.frame_start}→{scene.frame_end}) → {sample_id}")
        return {'FINISHED'}


class SCORESYNC_OT_sampler_load_file(bpy.types.Operator):
    bl_idname  = "scoresync.sampler_load_file"
    bl_label   = "Load Video / Image into Pad"
    bl_description = "Load an external video or image sequence file into the selected pad"

    filepath   : bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(
        default="*.mp4;*.mov;*.avi;*.mkv;*.png;*.jpg;*.exr;*.tif",
        options={'HIDDEN'},
    )
    pad_index  : bpy.props.IntProperty(default=0)

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        scene = context.scene
        bank_idx = scene.scoresync_active_bank
        banks = scene.scoresync_banks
        if bank_idx >= len(banks):
            self.report({'WARNING'}, "No active bank.")
            return {'CANCELLED'}
        bank = banks[bank_idx]
        if self.pad_index >= len(bank.pads):
            self.report({'WARNING'}, "Pad index out of range.")
            return {'CANCELLED'}

        src = bpy.path.abspath(self.filepath)
        ext = os.path.splitext(src)[1].lower()
        src_type = "IMAGE_SEQUENCE" if ext in (".png", ".jpg", ".exr", ".tif") else "MOVIE"

        if not DEV_SAMPLER.cache:
            DEV_SAMPLER.cache = load_cache()

        sample_id = _next_sample_id(DEV_SAMPLER.cache)
        label = os.path.splitext(os.path.basename(src))[0]

        entry = {
            "id":           sample_id,
            "label":        label,
            "source_type":  src_type,
            "source_path":  src,
            "frame_start":  1,
            "frame_end":    250,
            "fps":          scene.render.fps,
            "bank":         bank_idx,
            "pad":          self.pad_index,
            "thumbnail_path": "",
        }
        DEV_SAMPLER.cache[sample_id] = entry
        save_cache(DEV_SAMPLER.cache)

        pad = bank.pads[self.pad_index]
        pad.sample_id = sample_id
        pad.label     = label

        self.report({'INFO'}, f"Loaded '{label}' → pad {self.pad_index+1}")
        return {'FINISHED'}


class SCORESYNC_OT_sampler_fire_pad(bpy.types.Operator):
    """Manually fire a pad from the UI (for testing without hardware)."""
    bl_idname = "scoresync.sampler_fire_pad"
    bl_label  = "Fire Pad"

    bank_index: bpy.props.IntProperty(default=0)
    pad_index : bpy.props.IntProperty(default=0)
    velocity  : bpy.props.IntProperty(default=100, min=1, max=127)

    def execute(self, context):
        if not DEV_SAMPLER.cache:
            DEV_SAMPLER.cache = load_cache()
        fire_pad(context.scene, self.bank_index, self.pad_index, self.velocity)
        return {'FINISHED'}


class SCORESYNC_OT_sampler_export_bank(bpy.types.Operator):
    bl_idname  = "scoresync.sampler_export_bank"
    bl_label   = "Export Bank JSON"
    bl_description = "Save the active bank pad assignments to JSON"

    filepath   : bpy.props.StringProperty(subtype="FILE_PATH")
    filename   : bpy.props.StringProperty(default="scoresync_bank.json")
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        self.filename = "scoresync_bank.json"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        scene = context.scene
        bank_idx = scene.scoresync_active_bank
        banks = scene.scoresync_banks
        if bank_idx >= len(banks):
            self.report({'WARNING'}, "No active bank."); return {'CANCELLED'}
        bank = banks[bank_idx]

        pads_data = []
        for pad in bank.pads:
            pads_data.append({
                "label":    pad.label,
                "note":     pad.note,
                "channel":  pad.channel,
                "sample_id": pad.sample_id,
                "output_mode": pad.output_mode,
                "vse_channel": pad.vse_channel,
                "mat_target":  pad.mat_target,
                "velocity_to_alpha": pad.velocity_to_alpha,
                "color": list(pad.color),
            })
        doc = {"version": 1, "bank_name": bank.name, "pads": pads_data}

        dst = bpy.path.abspath(self.filepath)
        if not dst.endswith(".json"):
            dst = os.path.join(dst, self.filename)
        try:
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2)
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {e}"); return {'CANCELLED'}

        self.report({'INFO'}, f"Bank '{bank.name}' exported to {dst}")
        return {'FINISHED'}


class SCORESYNC_OT_sampler_import_bank(bpy.types.Operator):
    bl_idname  = "scoresync.sampler_import_bank"
    bl_label   = "Import Bank JSON"
    bl_description = "Load a saved bank into a new bank slot"

    filepath   : bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        scene = context.scene
        src = bpy.path.abspath(self.filepath)
        try:
            with open(src, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {e}"); return {'CANCELLED'}

        bank = scene.scoresync_banks.add()
        bank.name = doc.get("bank_name", "Imported Bank")
        for pd in doc.get("pads", []):
            pad = bank.pads.add()
            pad.label    = pd.get("label", "")
            pad.note     = pd.get("note", 0)
            pad.channel  = pd.get("channel", 0)
            pad.sample_id= pd.get("sample_id", "")
            pad.output_mode = pd.get("output_mode", "VSE")
            pad.vse_channel = pd.get("vse_channel", 1)
            pad.mat_target  = pd.get("mat_target", "")
            pad.velocity_to_alpha = pd.get("velocity_to_alpha", False)
            col = pd.get("color", [0.2, 0.2, 0.8, 1.0])
            pad.color = col[:4]

        scene.scoresync_active_bank = len(scene.scoresync_banks) - 1
        self.report({'INFO'}, f"Imported bank '{bank.name}' with {len(bank.pads)} pads")
        return {'FINISHED'}


class SCORESYNC_OT_sampler_select_pad(bpy.types.Operator):
    """Select a pad for editing (does not fire it)."""
    bl_idname = "scoresync.sampler_select_pad"
    bl_label  = "Select Pad"

    index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        context.scene.scoresync_active_pad = self.index
        return {'FINISHED'}


class SCORESYNC_OT_sampler_set_active_bank(bpy.types.Operator):
    bl_idname = "scoresync.sampler_set_active_bank"
    bl_label  = "Select Bank"
    bl_description = "Switch to this pad bank"

    index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        context.scene.scoresync_active_bank = self.index
        return {'FINISHED'}


class SCORESYNC_OT_sampler_reload_cache(bpy.types.Operator):
    bl_idname = "scoresync.sampler_reload_cache"
    bl_label  = "Reload Cache"
    bl_description = "Reload the sample cache database from disk"

    def execute(self, context):
        DEV_SAMPLER.cache = load_cache()
        self.report({'INFO'}, f"Cache reloaded: {len(DEV_SAMPLER.cache)} samples")
        return {'FINISHED'}


class SCORESYNC_OT_sampler_reset_pad(bpy.types.Operator):
    """Clear this pad back to its default empty state"""
    bl_idname   = "scoresync.sampler_reset_pad"
    bl_label    = "Reset Pad"
    bl_options  = {'REGISTER', 'UNDO'}

    pad_index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        scene    = context.scene
        banks    = scene.scoresync_banks
        bank_idx = scene.scoresync_active_bank
        if bank_idx >= len(banks):
            return {'CANCELLED'}
        bank = banks[bank_idx]
        if self.pad_index >= len(bank.pads):
            return {'CANCELLED'}

        pad           = bank.pads[self.pad_index]
        pad.label     = f"Pad {self.pad_index + 1}"
        pad.sample_id = ""
        pad.enabled   = True
        self.report({'INFO'}, f"Pad {self.pad_index + 1} reset")
        return {'FINISHED'}


# ── Registration list ─────────────────────────────────────────────────────────
sampler_classes = (
    SamplerPad,
    SamplerBank,
    SCORESYNC_OT_sampler_add_bank,
    SCORESYNC_OT_sampler_remove_bank,
    SCORESYNC_OT_sampler_select_pad,
    SCORESYNC_OT_sampler_set_active_bank,
    SCORESYNC_OT_sampler_sample_from_timeline,
    SCORESYNC_OT_sampler_load_file,
    SCORESYNC_OT_sampler_fire_pad,
    SCORESYNC_OT_sampler_export_bank,
    SCORESYNC_OT_sampler_import_bank,
    SCORESYNC_OT_sampler_reload_cache,
    SCORESYNC_OT_sampler_reset_pad,
)
