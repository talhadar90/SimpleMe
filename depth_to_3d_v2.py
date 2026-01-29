#!/usr/bin/env python3
"""
Create 2.5D mesh from 2D image + depth map using Displace modifier.
Run with: blender --background --python depth_to_3d_v2.py
"""
import bpy
import bmesh
import os
from math import radians
from mathutils import Vector

# Paths
IMAGE_PATH = "/workspace/SimpleMe/sticker_maker/jobs/eccec884-f439-43f8-92e8-bc6e64504a65/in/base_character_r2d.png"
DEPTH_PATH = "/workspace/SimpleMe/sticker_maker/jobs/eccec884-f439-43f8-92e8-bc6e64504a65/in/lLLu5vRQvfNsZJVtrND3f_8193bd0450604e7d97512948b20c056f.png"
OUTPUT_RENDER = "/workspace/SimpleMe/sticker_maker/jobs/eccec884-f439-43f8-92e8-bc6e64504a65/in/base_character_depth3d.png"
OUTPUT_GLB = "/workspace/SimpleMe/sticker_maker/jobs/eccec884-f439-43f8-92e8-bc6e64504a65/in/base_character_depth3d.glb"

# Settings
RENDER_WIDTH = 1024
RENDER_HEIGHT = 1536
GRID_SIZE = 512  # Grid resolution
DEPTH_STRENGTH = 0.2  # Displacement strength


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in bpy.data.images:
        if block.users == 0:
            bpy.data.images.remove(block)


def create_grid_mesh(width, height, subdivisions):
    """Create a grid mesh using bmesh."""
    bm = bmesh.new()

    # Create grid
    bmesh.ops.create_grid(
        bm,
        x_segments=subdivisions,
        y_segments=int(subdivisions * 1.5),  # Taller to match aspect
        size=1.0
    )

    # Scale to match image aspect (1024x1536)
    for v in bm.verts:
        v.co.y *= 1.5  # Height is 1.5x width

    # Create mesh
    mesh = bpy.data.meshes.new("DepthGrid")
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new("DepthMesh", mesh)
    bpy.context.scene.collection.objects.link(obj)

    # Add UV map - use reset (flat top-down projection for XY plane)
    uv_layer = obj.data.uv_layers.new(name="UVMap")

    # Calculate UVs manually based on vertex XY positions
    bm = bmesh.new()
    bm.from_mesh(obj.data)

    uv_lay = bm.loops.layers.uv.active

    # Get bounds
    min_x = min(v.co.x for v in bm.verts)
    max_x = max(v.co.x for v in bm.verts)
    min_y = min(v.co.y for v in bm.verts)
    max_y = max(v.co.y for v in bm.verts)

    # Map XY to UV (0-1), flip Y to correct orientation
    for face in bm.faces:
        for loop in face.loops:
            x = (loop.vert.co.x - min_x) / (max_x - min_x)
            y = 1.0 - (loop.vert.co.y - min_y) / (max_y - min_y)  # Flip Y
            loop[uv_lay].uv = (x, y)

    bm.to_mesh(obj.data)
    bm.free()

    return obj


def apply_displacement(obj, depth_path, strength):
    """Apply depth map as displacement using modifier."""
    # First rotate mesh to face camera (stand it up from XY to XZ plane)
    # Rotate -90 degrees around X to make Y become Z
    obj.rotation_euler = (radians(-90), 0, 0)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(rotation=True)

    # Load depth image as texture
    depth_img = bpy.data.images.load(depth_path)

    # Create texture
    depth_tex = bpy.data.textures.new("DepthTexture", type='IMAGE')
    depth_tex.image = depth_img

    # Add displace modifier
    disp_mod = obj.modifiers.new(name="Displace", type='DISPLACE')
    disp_mod.texture = depth_tex
    disp_mod.texture_coords = 'UV'
    disp_mod.direction = 'Y'  # Displace along Y (towards camera, after rotation)
    disp_mod.strength = strength
    disp_mod.mid_level = 0.5  # Midpoint of displacement

    # Apply the modifier to bake displacement into geometry
    bpy.ops.object.modifier_apply(modifier=disp_mod.name)

    return obj


def create_material(image_path):
    """Create simple textured material."""
    mat = bpy.data.materials.new(name="ImageMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # Load image
    img = bpy.data.images.load(image_path)

    # Create nodes
    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (300, 0)

    # Use emission for flat/unlit look (shows original colors)
    emission = nodes.new('ShaderNodeEmission')
    emission.location = (100, 0)
    emission.inputs['Strength'].default_value = 1.0

    # Image texture
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = img
    tex.location = (-200, 0)

    # Mix shader for alpha
    mix = nodes.new('ShaderNodeMixShader')
    mix.location = (200, 0)

    # Transparent shader
    transp = nodes.new('ShaderNodeBsdfTransparent')
    transp.location = (0, -100)

    # Connect
    links.new(tex.outputs['Color'], emission.inputs['Color'])
    links.new(tex.outputs['Alpha'], mix.inputs['Fac'])
    links.new(transp.outputs['BSDF'], mix.inputs[1])
    links.new(emission.outputs['Emission'], mix.inputs[2])
    links.new(mix.outputs['Shader'], output.inputs['Surface'])

    mat.blend_method = 'CLIP'

    return mat


def setup_camera(obj):
    """Setup orthographic camera based on mesh bounds."""
    # Get mesh bounds after displacement
    min_x = min(v.co.x for v in obj.data.vertices)
    max_x = max(v.co.x for v in obj.data.vertices)
    min_z = min(v.co.z for v in obj.data.vertices)
    max_z = max(v.co.z for v in obj.data.vertices)

    center_x = (min_x + max_x) / 2
    center_z = (min_z + max_z) / 2
    height = max_z - min_z

    print(f"Mesh bounds: X=[{min_x:.2f}, {max_x:.2f}], Z=[{min_z:.2f}, {max_z:.2f}]")
    print(f"Mesh center: ({center_x:.2f}, {center_z:.2f}), height: {height:.2f}")

    cam_data = bpy.data.cameras.new(name='FrontCam')
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = height * 1.08  # Slight padding

    cam_obj = bpy.data.objects.new('FrontCam', cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)

    # Position camera centered on mesh
    cam_obj.location = (center_x, -5, center_z)
    cam_obj.rotation_euler = (radians(90), 0, 0)

    bpy.context.scene.camera = cam_obj
    return cam_obj


def setup_lighting():
    """Setup lighting."""
    light = bpy.data.lights.new(name='Sun', type='SUN')
    light.energy = 2.0
    light_obj = bpy.data.objects.new('Sun', light)
    bpy.context.scene.collection.objects.link(light_obj)
    light_obj.rotation_euler = (radians(45), 0, radians(15))


def main():
    print("=" * 60)
    print("Depth to 2.5D (Modifier Method)")
    print("=" * 60)

    os.makedirs(os.path.dirname(OUTPUT_RENDER), exist_ok=True)
    clear_scene()

    # Create grid mesh
    print(f"\nCreating {GRID_SIZE}x{GRID_SIZE} grid...")
    obj = create_grid_mesh(1.0, 1.5, GRID_SIZE)
    print(f"Vertices: {len(obj.data.vertices)}")

    # Apply displacement from depth map
    print(f"Applying depth displacement (strength={DEPTH_STRENGTH})...")
    apply_displacement(obj, DEPTH_PATH, DEPTH_STRENGTH)

    # Apply material
    print("Applying texture material...")
    mat = create_material(IMAGE_PATH)
    obj.data.materials.append(mat)

    # Setup scene
    setup_camera(obj)
    setup_lighting()

    # Render settings
    scene = bpy.context.scene
    scene.render.resolution_x = RENDER_WIDTH
    scene.render.resolution_y = RENDER_HEIGHT
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True

    # GPU
    scene.cycles.device = 'GPU'
    try:
        prefs = bpy.context.preferences
        cprefs = prefs.addons['cycles'].preferences
        cprefs.compute_device_type = 'OPTIX'
        cprefs.get_devices()
        for d in cprefs.devices:
            if d.type in ['CUDA', 'OPTIX']:
                d.use = True
    except:
        scene.cycles.device = 'CPU'

    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'

    # Render
    print(f"\nRendering: {OUTPUT_RENDER}")
    scene.render.filepath = OUTPUT_RENDER
    bpy.ops.render.render(write_still=True)

    # Export GLB
    print(f"Exporting: {OUTPUT_GLB}")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=OUTPUT_GLB,
        use_selection=True,
        export_format='GLB',
        export_materials='EXPORT'
    )

    print("\n" + "=" * 60)
    print("Done!")
    print(f"  Render: {OUTPUT_RENDER}")
    print(f"  GLB: {OUTPUT_GLB}")
    print("=" * 60)


if __name__ == "__main__":
    main()
