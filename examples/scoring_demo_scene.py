"""
ScoreSync Scoring Demo Scene Generator
Run this script inside Blender (Text Editor → Run Script)

Creates a 10-second cartoon-style scoring demo:
  - Bouncing ball with squash/stretch
  - Camera shake hit on landing
  - Coloured background that flashes on impact
  - 5 clear hit points (ball lands) at bars 1, 2, 3, 4, 5 @ 120 BPM

At 120 BPM each bar = 2 seconds = 48 frames (24fps).
Hit points are at frames: 48, 96, 144, 192, 240

Use ScoreSync to score these hits live:
  - Sampler pad → fire a "thud" sound clip on each landing
  - FX slot → flash emission on impact
  - MIDI mapping → control ball colour via CC knob
"""

import bpy
import math

# ── Settings ──────────────────────────────────────────────────────────────────
FPS        = 24
BPM        = 120
BAR_FRAMES = int(FPS * 60 / BPM * 4)   # 48 frames per bar at 120 BPM
TOTAL_BARS = 5
END_FRAME  = BAR_FRAMES * TOTAL_BARS    # 240 frames = 10 seconds

HIT_FRAMES = [BAR_FRAMES * i for i in range(1, TOTAL_BARS + 1)]  # [48,96,144,192,240]

# ── Scene setup ───────────────────────────────────────────────────────────────
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end   = END_FRAME
scene.render.fps  = FPS

# Clear default objects
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# ── Floor ─────────────────────────────────────────────────────────────────────
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = "Floor"
mat_floor = bpy.data.materials.new("FloorMat")
mat_floor.use_nodes = True
mat_floor.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.15, 0.15, 0.2, 1)
floor.data.materials.append(mat_floor)

# ── Ball ──────────────────────────────────────────────────────────────────────
bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0, 0, 1))
ball = bpy.context.active_object
ball.name = "ScoreSync_Ball"

mat_ball = bpy.data.materials.new("BallMat")
mat_ball.use_nodes = True
nodes = mat_ball.node_tree.nodes
bsdf  = nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value    = (1.0, 0.3, 0.05, 1)  # orange
bsdf.inputs["Emission Color"].default_value = (1.0, 0.3, 0.05, 1)
bsdf.inputs["Emission Strength"].default_value = 0.0
ball.data.materials.append(mat_ball)

# ── Keyframe helpers ──────────────────────────────────────────────────────────
def key_loc(obj, frame, z):
    scene.frame_set(frame)
    obj.location.z = z
    obj.keyframe_insert("location", index=2, frame=frame)

def key_scale(obj, frame, sx, sz):
    scene.frame_set(frame)
    obj.scale.x = sx
    obj.scale.y = sx
    obj.scale.z = sz
    obj.keyframe_insert("scale", frame=frame)

def key_emission(mat, frame, strength):
    scene.frame_set(frame)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Emission Strength"].default_value = strength
    bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=frame)

# ── Animate ball across 5 bounces ─────────────────────────────────────────────
PEAK_Z    = 8.0   # height of bounce arc
GROUND_Z  = 1.0   # resting on floor (radius = 1)
SQUASH_SX = 1.4
SQUASH_SZ = 0.6

prev_hit = 0
for i, hit in enumerate(HIT_FRAMES):
    peak = (prev_hit + hit) // 2   # midpoint between previous landing and this one

    # Rise to peak
    key_loc(ball,   prev_hit + 2, GROUND_Z);  key_scale(ball, prev_hit + 2, 1.0, 1.0)
    key_loc(ball,   peak,         PEAK_Z);     key_scale(ball, peak,         0.9, 1.15)

    # Squash on landing
    key_loc(ball,   hit - 2,  GROUND_Z + 0.5); key_scale(ball, hit - 2,  1.1, 0.9)
    key_loc(ball,   hit,      GROUND_Z - 0.2); key_scale(ball, hit,      SQUASH_SX, SQUASH_SZ)
    key_loc(ball,   hit + 3,  GROUND_Z);        key_scale(ball, hit + 3,  1.0, 1.0)

    # Emission flash on impact
    key_emission(mat_ball, hit - 1, 0.0)
    key_emission(mat_ball, hit,     8.0)
    key_emission(mat_ball, hit + 6, 0.0)

    prev_hit = hit

# Make all keyframes use BEZIER for smooth arcs
for fc in ball.animation_data.action.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = 'BEZIER'

# ── Camera ────────────────────────────────────────────────────────────────────
bpy.ops.object.camera_add(location=(0, -14, 5))
cam = bpy.context.active_object
cam.name = "Camera"
cam.rotation_euler = (math.radians(70), 0, 0)
scene.camera = cam

# Camera shake on each hit
for hit in HIT_FRAMES:
    scene.frame_set(hit)
    cam.location.z = 5.0
    cam.keyframe_insert("location", index=2, frame=hit)
    scene.frame_set(hit + 1)
    cam.location.z = 5.25
    cam.keyframe_insert("location", index=2, frame=hit + 1)
    scene.frame_set(hit + 4)
    cam.location.z = 5.0
    cam.keyframe_insert("location", index=2, frame=hit + 4)

# ── Light ─────────────────────────────────────────────────────────────────────
bpy.ops.object.light_add(type='SUN', location=(5, -5, 10))
sun = bpy.context.active_object
sun.data.energy = 4.0

# ── Markers at each bar ───────────────────────────────────────────────────────
for i, hit in enumerate(HIT_FRAMES):
    m = scene.timeline_markers.new(f"Bar {i+1} Hit", frame=hit)

# ── Drop to frame 1 ───────────────────────────────────────────────────────────
scene.frame_set(1)

print("=" * 60)
print("ScoreSync scoring demo scene created!")
print(f"  {TOTAL_BARS} hit points at frames: {HIT_FRAMES}")
print(f"  BPM: {BPM}  |  FPS: {FPS}  |  Duration: {END_FRAME / FPS:.1f}s")
print()
print("Score this with ScoreSync:")
print("  1. Connect your MIDI controller")
print("  2. Open ScoreSync Editor → Sampler → load a thud/impact SFX")
print("  3. Bind a pad to fire on each ball landing")
print("  4. Right-click ball's Emission Strength → Learn MIDI → bind a CC")
print("  5. Hit play in your DAW — Blender follows the clock")
print("=" * 60)
