#!/usr/bin/env python3
"""
Render 3D model from front view to PNG
Run with: blender --background --python render_front_view.py
"""
import bpy
import os
from math import radians

# Paths
JOB_ID = "75520930-b7f2-4196-b111-9b6baba12c90"
GLB_PATH = f"/workspace/SimpleMe/storage/processed/{JOB_ID}/3d_models/base_character_4k_test.glb"
OUTPUT_PNG = f"/workspace/SimpleMe/storage/processed/{JOB_ID}/textures/base_character_front_view.png"

# Render settings - match original image size
RENDER_WIDTH = 1024
RENDER_HEIGHT = 1536


def clear_scene():
    """Remove all objects from scene"""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    # Clear orphan data
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


def setup_camera_front_view(obj):
    """Setup camera to view object from front (looking down -Y axis)"""
    # Get object bounds
    bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]

    min_x = min(v.x for v in bbox)
    max_x = max(v.x for v in bbox)
    min_y = min(v.y for v in bbox)
    max_y = max(v.y for v in bbox)
    min_z = min(v.z for v in bbox)
    max_z = max(v.z for v in bbox)

    center_x = (min_x + max_x) / 2
    center_z = (min_z + max_z) / 2

    obj_width = max_x - min_x
    obj_height = max_z - min_z

    print(f"Object bounds: X=[{min_x:.3f}, {max_x:.3f}], Z=[{min_z:.3f}, {max_z:.3f}]")
    print(f"Object size: {obj_width:.3f} x {obj_height:.3f}")

    # Create camera
    cam_data = bpy.data.cameras.new(name='FrontCamera')
    cam_data.type = 'ORTHO'

    # Set orthographic scale to fit object with some padding
    padding = 1.05
    aspect_ratio = RENDER_WIDTH / RENDER_HEIGHT

    if obj_width / obj_height > aspect_ratio:
        # Object is wider - fit to width
        cam_data.ortho_scale = obj_width * padding
    else:
        # Object is taller - fit to height
        cam_data.ortho_scale = obj_height * padding * aspect_ratio

    cam_obj = bpy.data.objects.new('FrontCamera', cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)

    # Position camera in front of object (looking down -Y)
    cam_obj.location = (center_x, min_y - 2.0, center_z)
    cam_obj.rotation_euler = (radians(90), 0, 0)

    # Set as active camera
    bpy.context.scene.camera = cam_obj

    print(f"Camera ortho scale: {cam_data.ortho_scale:.3f}")

    return cam_obj


def setup_lighting():
    """Setup even lighting for texture capture"""
    # Front light
    light_data = bpy.data.lights.new(name='FrontLight', type='SUN')
    light_data.energy = 3.0
    light_obj = bpy.data.objects.new('FrontLight', light_data)
    bpy.context.scene.collection.objects.link(light_obj)
    light_obj.rotation_euler = (radians(45), 0, 0)

    # Fill light from above
    light_data2 = bpy.data.lights.new(name='TopLight', type='SUN')
    light_data2.energy = 1.5
    light_obj2 = bpy.data.objects.new('TopLight', light_data2)
    bpy.context.scene.collection.objects.link(light_obj2)
    light_obj2.rotation_euler = (0, 0, 0)


def setup_render_settings():
    """Configure render settings for clean texture capture"""
    scene = bpy.context.scene

    # Render resolution
    scene.render.resolution_x = RENDER_WIDTH
    scene.render.resolution_y = RENDER_HEIGHT
    scene.render.resolution_percentage = 100

    # Use Cycles for quality
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 128
    scene.cycles.use_denoising = True

    # Transparent background
    scene.render.film_transparent = True

    # Output format
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'


def main():
    print("=" * 60)
    print("Render Front View")
    print("=" * 60)

    # Need Vector for bounds calculation
    from mathutils import Vector

    # Make Vector available globally for setup_camera_front_view
    import builtins
    builtins.Vector = Vector

    # Create output directory
    os.makedirs(os.path.dirname(OUTPUT_PNG), exist_ok=True)

    # Clear scene
    clear_scene()

    # Import GLB
    print(f"\nImporting: {GLB_PATH}")
    obj = import_glb(GLB_PATH)
    if not obj:
        print("ERROR: No mesh found in GLB")
        return

    print(f"Imported mesh: {obj.name}")

    # Apply rotation for correct orientation
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    obj.rotation_euler = (0, radians(-90), radians(-90))
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    print("Applied rotation: Y=-90, Z=-90")

    # Setup camera
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
