#!/usr/bin/env python3
"""
Render the 3D model using the filled/bled baked texture.
"""
import bpy
import os
from math import radians
from mathutils import Vector, Matrix

GLB_PATH = "/workspace/SimpleMe/sticker_maker/jobs/eccec884-f439-43f8-92e8-bc6e64504a65/in/base_character_3d.glb"
TEXTURE_PATH = "/workspace/SimpleMe/sticker_maker/jobs/eccec884-f439-43f8-92e8-bc6e64504a65/in/base_character_baked_texture_filled.png"
OUTPUT_RENDER = "/workspace/SimpleMe/sticker_maker/jobs/eccec884-f439-43f8-92e8-bc6e64504a65/in/base_character_filled_render.png"

RENDER_WIDTH = 1024
RENDER_HEIGHT = 1536


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def world_aabb(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    M = eo.matrix_world
    pts = [M @ Vector(c) for c in eo.bound_box]
    xs, ys, zs = [p.x for p in pts], [p.y for p in pts], [p.z for p in pts]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


def world_center(obj):
    mn, mx = world_aabb(obj)
    return (mn + mx) * 0.5


def world_sizes(obj):
    mn, mx = world_aabb(obj)
    return mx - mn


def needs_x_roll(obj):
    dx, dy, dz = world_sizes(obj)
    return dy < dz


def roll_about_parallel_world_x(obj, degrees):
    c = world_center(obj)
    T = Matrix.Translation(c)
    R = Matrix.Rotation(radians(degrees), 4, 'X')
    obj.matrix_world = T @ R @ T.inverted() @ obj.matrix_world
    bpy.context.view_layer.update()


def rotate_about_world_y(obj, degrees):
    c = world_center(obj)
    T = Matrix.Translation(c)
    R = Matrix.Rotation(radians(degrees), 4, 'Y')
    obj.matrix_world = T @ R @ T.inverted() @ obj.matrix_world
    bpy.context.view_layer.update()


def center_xy(obj):
    mn, mx = world_aabb(obj)
    obj.location.x -= 0.5 * (mn.x + mx.x)
    obj.location.y -= 0.5 * (mn.y + mx.y)
    bpy.context.view_layer.update()


def rest_on_z0(obj):
    mn, mx = world_aabb(obj)
    obj.location.z -= mn.z
    bpy.context.view_layer.update()


def select_only(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def main():
    print("=" * 60)
    print("Render with Filled Baked Texture")
    print("=" * 60)

    clear_scene()

    # Import GLB
    print(f"Importing: {GLB_PATH}")
    bpy.ops.import_scene.gltf(filepath=GLB_PATH)

    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    obj = meshes[0]
    print(f"Mesh: {obj.name}")

    # Orientation fixes
    if needs_x_roll(obj):
        roll_about_parallel_world_x(obj, -90)
    rotate_about_world_y(obj, -90)

    select_only(obj)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    center_xy(obj)
    rest_on_z0(obj)

    mn, mx = world_aabb(obj)
    center = (mn + mx) * 0.5
    h = mx.y - mn.y

    # Create material with filled texture
    print(f"Loading texture: {TEXTURE_PATH}")
    mat = bpy.data.materials.new(name="FilledTexture")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new('ShaderNodeOutputMaterial')
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.8
    bsdf.inputs['Specular IOR Level'].default_value = 0.0

    tex = nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(TEXTURE_PATH)

    links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

    obj.data.materials.clear()
    obj.data.materials.append(mat)

    # Camera setup
    cam_data = bpy.data.cameras.new(name='RenderCam')
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = h / 0.921

    cam_obj = bpy.data.objects.new('RenderCam', cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)

    y_offset = (0.046 + 0.921 / 2 - 0.5) * cam_data.ortho_scale
    cam_obj.matrix_world = Matrix((
        (1, 0, 0, center.x),
        (0, 1, 0, center.y + y_offset),
        (0, 0, 1, center.z + 50),
        (0, 0, 0, 1),
    ))
    bpy.context.scene.camera = cam_obj

    # Lighting
    light = bpy.data.lights.new(name='Sun', type='SUN')
    light.energy = 3.0
    light_obj = bpy.data.objects.new('Sun', light)
    bpy.context.scene.collection.objects.link(light_obj)

    # Render settings
    scene = bpy.context.scene
    scene.render.resolution_x = RENDER_WIDTH
    scene.render.resolution_y = RENDER_HEIGHT
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 128
    scene.cycles.use_denoising = True
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
    print(f"Rendering: {OUTPUT_RENDER}")
    scene.render.filepath = OUTPUT_RENDER
    bpy.ops.render.render(write_still=True)

    print("Done!")


if __name__ == "__main__":
    main()
