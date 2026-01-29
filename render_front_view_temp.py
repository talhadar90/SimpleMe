#!/usr/bin/env python3
"""
Render 3D model from front view to PNG using Tripo3D orientation fixes
Run with: blender --background --python render_front_view_temp.py
"""
import bpy
import os
from math import radians
from mathutils import Vector, Matrix

# Paths for this specific job
GLB_PATH = "/workspace/SimpleMe/sticker_maker/jobs/eccec884-f439-43f8-92e8-bc6e64504a65/in/base_character_3d.glb"
OUTPUT_PNG = "/workspace/SimpleMe/sticker_maker/jobs/eccec884-f439-43f8-92e8-bc6e64504a65/in/base_character_front_render.png"

# Render settings - match original image size
RENDER_WIDTH = 1024
RENDER_HEIGHT = 1536


def clear_scene():
    """Remove all objects from scene"""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for block in bpy.data.cameras:
        if block.users == 0:
            bpy.data.cameras.remove(block)
    for block in bpy.data.lights:
        if block.users == 0:
            bpy.data.lights.remove(block)


def import_glb(path):
    """Import GLB and return the main mesh object"""
    bpy.ops.import_scene.gltf(filepath=path)
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            return obj
    return None


def world_aabb(obj):
    """Get world-space axis-aligned bounding box"""
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    M = eo.matrix_world
    pts = [M @ Vector(c) for c in eo.bound_box]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    mn = Vector((min(xs), min(ys), min(zs)))
    mx = Vector((max(xs), max(ys), max(zs)))
    return mn, mx


def world_dims(obj):
    mn, mx = world_aabb(obj)
    return mx - mn


def world_center(obj):
    mn, mx = world_aabb(obj)
    return (mn + mx) * 0.5


def world_sizes(obj):
    mn, mx = world_aabb(obj)
    d = mx - mn
    return Vector((float(d.x), float(d.y), float(d.z)))


def needs_x_roll(obj):
    """Returns True if size along global Y is LESS than size along global Z."""
    dx, dy, dz = world_sizes(obj)
    return dy < dz


def roll_about_parallel_world_x(obj, degrees):
    """Rotate obj about an axis parallel to world X through object's center."""
    c = world_center(obj)
    T = Matrix.Translation(c)
    R = Matrix.Rotation(radians(degrees), 4, 'X')
    obj.matrix_world = T @ R @ T.inverted() @ obj.matrix_world
    bpy.context.view_layer.update()


def rotate_about_world_y(obj, degrees):
    """Rotate obj about the world Y axis through object's center."""
    c = world_center(obj)
    T = Matrix.Translation(c)
    R = Matrix.Rotation(radians(degrees), 4, 'Y')
    obj.matrix_world = T @ R @ T.inverted() @ obj.matrix_world
    bpy.context.view_layer.update()


def center_xy(obj):
    mn, mx = world_aabb(obj)
    cx = 0.5 * (mn.x + mx.x)
    cy = 0.5 * (mn.y + mx.y)
    obj.location.x -= cx
    obj.location.y -= cy
    bpy.context.view_layer.update()


def rest_on_z0(obj):
    mn, mx = world_aabb(obj)
    obj.location.z -= mn.z
    bpy.context.view_layer.update()


def setup_camera_front_view(obj):
    """Setup orthographic camera looking along -Z (top-down XY view)"""
    bpy.context.view_layer.update()

    mn, mx = world_aabb(obj)
    center = (mn + mx) * 0.5

    w = mx.x - mn.x
    h = mx.y - mn.y

    print(f"Object bounds: X=[{mn.x:.3f}, {mx.x:.3f}], Y=[{mn.y:.3f}, {mx.y:.3f}], Z=[{mn.z:.3f}, {mx.z:.3f}]")
    print(f"Object size (XY): {w:.3f} x {h:.3f}")

    # Create orthographic camera
    cam_data = bpy.data.cameras.new(name='FrontCamera')
    cam_data.type = 'ORTHO'

    # Match original image framing:
    # Original: figure takes 92.1% of height, top margin 3.3%, bottom margin 4.6%
    # For ortho camera: ortho_scale = view height in world units
    # We want: figure_height / view_height = 0.921
    # So: view_height = figure_height / 0.921
    target_figure_height_ratio = 0.921
    aspect_ratio = RENDER_WIDTH / RENDER_HEIGHT

    # Calculate ortho scale (view height) to make figure 92.1% of image height
    cam_data.ortho_scale = h / target_figure_height_ratio

    cam_obj = bpy.data.objects.new('FrontCamera', cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)

    # Adjust camera position to match original margins
    # Original: top margin 3.3%, bottom margin 4.6%
    # This means figure center is shifted down by (4.6-3.3)/2 = 0.65% of image height
    # In world units: shift = 0.0065 * ortho_scale / aspect_ratio
    margin_diff = (0.046 - 0.033) / 2  # 0.65%
    y_offset = margin_diff * cam_data.ortho_scale / aspect_ratio

    # Camera looking along -Z (top-down view of XY plane)
    dist = 50.0
    cam_obj.matrix_world = Matrix((
        (1, 0, 0, center.x),
        (0, 1, 0, center.y - y_offset),  # Shift camera up to move figure down in frame
        (0, 0, 1, center.z + dist),
        (0, 0, 0, 1),
    ))

    bpy.context.scene.camera = cam_obj
    print(f"Camera ortho scale: {cam_data.ortho_scale:.3f}")
    print(f"Y offset for margin balance: {y_offset:.4f}")
    return cam_obj


def setup_lighting():
    """Setup lighting for texture capture"""
    # Front light (from +Z direction)
    light_data = bpy.data.lights.new(name='FrontLight', type='SUN')
    light_data.energy = 3.0
    light_obj = bpy.data.objects.new('FrontLight', light_data)
    bpy.context.scene.collection.objects.link(light_obj)
    light_obj.rotation_euler = (0, 0, 0)  # Pointing down

    # Fill light
    light_data2 = bpy.data.lights.new(name='FillLight', type='SUN')
    light_data2.energy = 1.5
    light_obj2 = bpy.data.objects.new('FillLight', light_data2)
    bpy.context.scene.collection.objects.link(light_obj2)
    light_obj2.rotation_euler = (radians(45), 0, radians(45))


def setup_render_settings():
    """Configure render settings"""
    scene = bpy.context.scene
    scene.render.resolution_x = RENDER_WIDTH
    scene.render.resolution_y = RENDER_HEIGHT
    scene.render.resolution_percentage = 100

    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 128
    scene.cycles.use_denoising = True

    # Enable GPU
    scene.cycles.device = 'GPU'
    try:
        prefs = bpy.context.preferences
        cprefs = prefs.addons['cycles'].preferences
        cprefs.compute_device_type = 'OPTIX'
        cprefs.get_devices()
        for device in cprefs.devices:
            if device.type in ['CUDA', 'OPTIX']:
                device.use = True
    except:
        scene.cycles.device = 'CPU'

    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'


def main():
    print("=" * 60)
    print("Render Front View (Tripo3D orientation)")
    print("=" * 60)

    os.makedirs(os.path.dirname(OUTPUT_PNG), exist_ok=True)
    clear_scene()

    # Import GLB
    print(f"\nImporting: {GLB_PATH}")
    obj = import_glb(GLB_PATH)
    if not obj:
        print("ERROR: No mesh found in GLB")
        return

    print(f"Imported mesh: {obj.name}")

    # Apply Tripo3D orientation fixes (from blender2.py)
    needs_roll = needs_x_roll(obj)
    print(f"Needs X roll: {needs_roll}")

    # Step 1: Roll to stand upright (if needed)
    if needs_roll:
        roll_about_parallel_world_x(obj, -90)
        print("Applied roll: X=-90")

    # Step 2: Rotate around Y to face camera (camera looks along -Z)
    rotate_about_world_y(obj, -90)
    print("Applied rotation: Y=-90")

    # Center and position
    center_xy(obj)
    rest_on_z0(obj)
    print("Centered on XY, resting on Z=0")

    # Setup camera (looking down -Z at XY plane)
    print(f"\nSetting up camera...")
    setup_camera_front_view(obj)

    # Setup lighting
    print("Setting up lighting...")
    setup_lighting()

    # Setup render
    print("Configuring render settings...")
    setup_render_settings()

    # Render
    print(f"\nRendering to: {OUTPUT_PNG}")
    bpy.context.scene.render.filepath = OUTPUT_PNG
    bpy.ops.render.render(write_still=True)

    print(f"\n" + "=" * 60)
    print(f"Done! Front view rendered to:")
    print(f"  {OUTPUT_PNG}")
    print(f"  Size: {RENDER_WIDTH} x {RENDER_HEIGHT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
