#!/usr/bin/env python3
"""
Create 2.5D mesh from 2D image + depth map.
Uses depth map to displace a plane, applies original image as texture.
Run with: blender --background --python depth_to_3d.py
"""
import bpy
import os
from math import radians
from mathutils import Vector, Matrix

# Paths
IMAGE_PATH = "/workspace/SimpleMe/sticker_maker/jobs/eccec884-f439-43f8-92e8-bc6e64504a65/in/base_character_r2d.png"
DEPTH_PATH = "/workspace/SimpleMe/sticker_maker/jobs/eccec884-f439-43f8-92e8-bc6e64504a65/in/lLLu5vRQvfNsZJVtrND3f_8193bd0450604e7d97512948b20c056f.png"
OUTPUT_RENDER = "/workspace/SimpleMe/sticker_maker/jobs/eccec884-f439-43f8-92e8-bc6e64504a65/in/base_character_depth3d.png"
OUTPUT_GLB = "/workspace/SimpleMe/sticker_maker/jobs/eccec884-f439-43f8-92e8-bc6e64504a65/in/base_character_depth3d.glb"

# Settings
RENDER_WIDTH = 1024
RENDER_HEIGHT = 1536
SUBDIVISIONS = 256  # Higher = more detail
DEPTH_STRENGTH = 0.15  # How much depth displacement (adjust for desired 3D effect)


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in bpy.data.images:
        if block.users == 0:
            bpy.data.images.remove(block)
    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)


def create_displaced_plane():
    """Create a highly subdivided plane for displacement."""
    # Create plane
    bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 0))
    plane = bpy.context.active_object
    plane.name = "DepthMesh"

    # Subdivide for smooth displacement
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.subdivide(number_cuts=SUBDIVISIONS)
    bpy.ops.object.mode_set(mode='OBJECT')

    # Scale to match image aspect ratio (1024x1536 = 2:3)
    plane.scale.x = 1.0
    plane.scale.y = 1.5  # 1536/1024 = 1.5
    bpy.ops.object.transform_apply(scale=True)

    return plane


def create_depth_material(image_path, depth_path):
    """Create material with image texture and depth displacement."""
    mat = bpy.data.materials.new(name="DepthMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # Load images
    color_img = bpy.data.images.load(image_path)
    depth_img = bpy.data.images.load(depth_path)
    depth_img.colorspace_settings.name = 'Non-Color'  # Depth is data, not color

    # Output node
    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (400, 0)

    # Principled BSDF for the color
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (100, 0)
    bsdf.inputs['Roughness'].default_value = 1.0  # Matte finish
    bsdf.inputs['Specular IOR Level'].default_value = 0.0

    # Color texture
    color_tex = nodes.new('ShaderNodeTexImage')
    color_tex.image = color_img
    color_tex.location = (-300, 100)

    # UV coordinates
    uv_node = nodes.new('ShaderNodeTexCoord')
    uv_node.location = (-500, 0)

    # Connect color
    links.new(uv_node.outputs['UV'], color_tex.inputs['Vector'])
    links.new(color_tex.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(color_tex.outputs['Alpha'], bsdf.inputs['Alpha'])
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

    # Displacement setup
    disp_tex = nodes.new('ShaderNodeTexImage')
    disp_tex.image = depth_img
    disp_tex.location = (-300, -200)

    disp_node = nodes.new('ShaderNodeDisplacement')
    disp_node.location = (100, -200)
    disp_node.inputs['Scale'].default_value = DEPTH_STRENGTH
    disp_node.inputs['Midlevel'].default_value = 0.5

    links.new(uv_node.outputs['UV'], disp_tex.inputs['Vector'])
    links.new(disp_tex.outputs['Color'], disp_node.inputs['Height'])
    links.new(disp_node.outputs['Displacement'], output.inputs['Displacement'])

    # Enable alpha blend for transparency
    mat.blend_method = 'CLIP'

    return mat


def setup_camera():
    """Setup orthographic camera for front view."""
    cam_data = bpy.data.cameras.new(name='FrontCam')
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = 3.0  # Adjust to frame the plane (height is 3 units)

    cam_obj = bpy.data.objects.new('FrontCam', cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)

    # Position camera in front (looking along -Y)
    cam_obj.location = (0, -5, 0)
    cam_obj.rotation_euler = (radians(90), 0, 0)

    bpy.context.scene.camera = cam_obj
    return cam_obj


def setup_lighting():
    """Setup even lighting."""
    # Front light
    light_data = bpy.data.lights.new(name='FrontLight', type='SUN')
    light_data.energy = 2.0
    light_obj = bpy.data.objects.new('FrontLight', light_data)
    bpy.context.scene.collection.objects.link(light_obj)
    light_obj.rotation_euler = (radians(45), 0, 0)

    # Fill light
    light_data2 = bpy.data.lights.new(name='FillLight', type='SUN')
    light_data2.energy = 1.0
    light_obj2 = bpy.data.objects.new('FillLight', light_data2)
    bpy.context.scene.collection.objects.link(light_obj2)
    light_obj2.rotation_euler = (radians(60), radians(30), 0)


def main():
    print("=" * 60)
    print("Depth Map to 2.5D Mesh")
    print("=" * 60)

    os.makedirs(os.path.dirname(OUTPUT_RENDER), exist_ok=True)
    clear_scene()

    # Create subdivided plane
    print(f"\nCreating mesh with {SUBDIVISIONS}x{SUBDIVISIONS} subdivisions...")
    plane = create_displaced_plane()
    print(f"Mesh vertices: {len(plane.data.vertices)}")

    # Create and apply material with displacement
    print("Creating depth-displaced material...")
    mat = create_depth_material(IMAGE_PATH, DEPTH_PATH)
    plane.data.materials.append(mat)

    # Add subdivision surface modifier for smooth displacement
    subsurf = plane.modifiers.new(name="Subdivision", type='SUBSURF')
    subsurf.levels = 2
    subsurf.render_levels = 3

    # Setup camera
    print("Setting up camera...")
    setup_camera()

    # Setup lighting
    print("Setting up lighting...")
    setup_lighting()

    # Configure render
    scene = bpy.context.scene
    scene.render.resolution_x = RENDER_WIDTH
    scene.render.resolution_y = RENDER_HEIGHT
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
        for d in cprefs.devices:
            if d.type in ['CUDA', 'OPTIX']:
                d.use = True
    except:
        scene.cycles.device = 'CPU'

    # Transparent background
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'

    # Enable displacement in Cycles (adaptive subdivision)
    try:
        scene.cycles.feature_set = 'EXPERIMENTAL'
        plane.cycles.use_adaptive_subdivision = True
    except AttributeError:
        # Blender 5.x may not have these
        pass

    # Render
    print(f"\nRendering to: {OUTPUT_RENDER}")
    scene.render.filepath = OUTPUT_RENDER
    bpy.ops.render.render(write_still=True)

    # Export GLB
    print(f"\nExporting GLB: {OUTPUT_GLB}")
    # Apply modifiers before export
    bpy.context.view_layer.objects.active = plane
    plane.select_set(True)

    # For GLB export, we need to bake displacement to actual geometry
    # Apply subdivision modifier
    bpy.ops.object.modifier_apply(modifier="Subdivision")

    bpy.ops.export_scene.gltf(
        filepath=OUTPUT_GLB,
        use_selection=True,
        export_format='GLB',
        export_materials='EXPORT'
    )

    print(f"\n" + "=" * 60)
    print("Done!")
    print(f"  Render: {OUTPUT_RENDER}")
    print(f"  GLB: {OUTPUT_GLB}")
    print("=" * 60)


if __name__ == "__main__":
    main()
