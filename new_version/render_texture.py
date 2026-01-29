import bpy
import bmesh
import os
import math
import sys
from mathutils import Vector, Matrix

# Install PIL if needed
try:
    from PIL import Image
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'Pillow'])
    from PIL import Image

# Install rembg for background removal (with onnxruntime)
try:
    import onnxruntime
    from rembg import remove as remove_bg
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'onnxruntime'])
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'rembg'])
    from rembg import remove as remove_bg

def remove_background(input_path, output_path=None):
    """Remove background from image while preserving quality and size"""
    img = Image.open(input_path)
    original_size = img.size

    # Remove background using rembg
    result = remove_bg(img)

    # Ensure output is same size as input
    if result.size != original_size:
        result = result.resize(original_size, Image.Resampling.LANCZOS)

    # Dilate colors into transparent areas to avoid dark edge artifacts
    result = dilate_texture(result)

    # Save or return
    if output_path:
        result.save(output_path)
        print(f"Background removed: {output_path} ({original_size[0]}x{original_size[1]})")
        return output_path
    return result

def dilate_texture(img, iterations=5):
    """Dilate RGB colors into transparent areas to avoid black edge artifacts"""
    import numpy as np
    from scipy import ndimage

    arr = np.array(img)
    rgb = arr[:, :, :3].astype(float)
    alpha = arr[:, :, 3].astype(float) / 255.0

    # Create mask of opaque pixels
    mask = alpha > 0.5

    # For each iteration, expand colors into transparent neighbors
    for _ in range(iterations):
        for c in range(3):
            channel = rgb[:, :, c]
            # Dilate using maximum filter on masked values
            dilated = ndimage.maximum_filter(np.where(mask, channel, 0), size=3)
            # Only update transparent pixels
            rgb[:, :, c] = np.where(mask, channel, dilated)
        # Expand mask
        mask = ndimage.maximum_filter(mask.astype(float), size=3) > 0

    # Reconstruct image
    result = np.zeros_like(arr)
    result[:, :, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    result[:, :, 3] = arr[:, :, 3]  # Keep original alpha

    return Image.fromarray(result, 'RGBA')

def world_aabb(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    M = eo.matrix_world
    pts = [M @ Vector(c) for c in eo.bound_box]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))

def world_dims(obj):
    mn, mx = world_aabb(obj)
    return mx - mn

def select_only(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def setup_gpu_cycles():
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 512  # Higher samples for less pixelation
    sc.cycles.use_denoising = True
    sc.cycles.device = 'GPU'
    try:
        prefs = bpy.context.preferences
        cprefs = prefs.addons['cycles'].preferences
        for compute_type in ['OPTIX', 'CUDA']:
            try:
                cprefs.compute_device_type = compute_type
                cprefs.get_devices()
                for device in cprefs.devices:
                    if device.type in ['CUDA', 'OPTIX']:
                        device.use = True
                        print(f"GPU: {device.name}")
                if compute_type == 'OPTIX':
                    sc.cycles.denoiser = 'OPTIX'
                return
            except:
                continue
        sc.cycles.device = 'CPU'
    except:
        sc.cycles.device = 'CPU'

def create_uv_project_from_view(obj, direction='Y'):
    """Create UV projection from front view (looking down -Y axis)"""
    select_only(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')

    # Project from front view
    bpy.ops.uv.project_from_view(
        camera_bounds=False,
        correct_aspect=True,
        scale_to_bounds=True
    )

    bpy.ops.object.mode_set(mode='OBJECT')

def sample_alpha_and_delete_faces(obj, image, threshold=0.1):
    """Delete faces where texture alpha is below threshold"""
    select_only(obj)

    # Get mesh data
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)

    # Get UV layer
    uv_layer = bm.loops.layers.uv.verify()

    # Load image pixels
    if image.pixels:
        width = image.size[0]
        height = image.size[1]
        pixels = list(image.pixels[:])

        faces_to_delete = []

        for face in bm.faces:
            # Sample alpha at face center UV
            uv_sum = Vector((0, 0))
            for loop in face.loops:
                uv_sum += loop[uv_layer].uv
            uv_center = uv_sum / len(face.loops)

            # Clamp UV coordinates
            u = max(0, min(1, uv_center.x))
            v = max(0, min(1, uv_center.y))

            # Get pixel coordinates
            px = int(u * (width - 1))
            py = int(v * (height - 1))

            # Get alpha value (RGBA, so alpha is every 4th value starting at index 3)
            pixel_index = (py * width + px) * 4
            if pixel_index + 3 < len(pixels):
                alpha = pixels[pixel_index + 3]
                if alpha < threshold:
                    faces_to_delete.append(face)

        # Delete faces with low alpha
        bmesh.ops.delete(bm, geom=faces_to_delete, context='FACES')

        print(f"Deleted {len(faces_to_delete)} faces with alpha < {threshold}")

    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

# Clear scene
bpy.ops.wm.read_factory_settings(use_empty=True)

# Load texture image first (need it for alpha masking)
tex_path_original = "/workspace/base_character_20260122_212103_nobg.png"

# Check if already has nobg - skip rembg, just dilate
check_img = Image.open(tex_path_original)
if '_nobg' in tex_path_original and check_img.mode == 'RGBA':
    tex_path = "/workspace/texture_dilated.png"
    print(f"Image already has transparency, applying dilation only...")
    dilated = dilate_texture(check_img, iterations=15)
    dilated.save(tex_path)
    print(f"Dilated: {tex_path} ({check_img.size[0]}x{check_img.size[1]})")
else:
    tex_path = "/workspace/texture_nobg.png"
    print(f"Removing background from: {tex_path_original}")
    remove_background(tex_path_original, tex_path)

tex_image = bpy.data.images.load(tex_path)
print(f"Loaded texture: {tex_image.size[0]}x{tex_image.size[1]}")

# Import STL
stl_path = "/workspace/Lithophane_Blended_Layers (3).stl"
bpy.ops.wm.stl_import(filepath=stl_path)

obj = bpy.context.selected_objects[0]
obj.name = "Lithophane"
bpy.context.view_layer.update()

# Get original dimensions
orig_dims = world_dims(obj)
print(f"Original STL: {orig_dims.x:.4f} x {orig_dims.z:.4f}")

# Target dimensions in meters
target_width_m = 0.130
target_height_m = 0.170

# Scale to target size
scale_x = target_width_m / orig_dims.x
scale_z = target_height_m / orig_dims.z

obj.scale.x *= scale_x
obj.scale.z *= scale_z
obj.scale.y *= scale_x

bpy.context.view_layer.update()
select_only(obj)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

# Center at origin
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
obj.location = (0, 0, 0)
bpy.context.view_layer.update()

# Get dimensions before alpha cut
final_dims = world_dims(obj)
final_mn, final_mx = world_aabb(obj)
print(f"Scaled STL: {final_dims.x*1000:.2f}mm x {final_dims.z*1000:.2f}mm")

# Setup camera for UV projection (looking from -Y toward +Y)
bpy.ops.object.camera_add(location=(0, -1, 0))
temp_camera = bpy.context.object
temp_camera.data.type = 'ORTHO'
temp_camera.data.ortho_scale = max(final_dims.x, final_dims.z)
temp_camera.rotation_euler = (math.radians(90), 0, 0)
bpy.context.scene.camera = temp_camera

# Create UV projection for the lithophane
select_only(obj)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')

# Use smart UV project for better coverage
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0)
bpy.ops.object.mode_set(mode='OBJECT')

# Now manually adjust UVs to project from front
mesh = obj.data
mn, mx = final_mn, final_mx

for uv_layer in mesh.uv_layers:
    for poly in mesh.polygons:
        for loop_idx in poly.loop_indices:
            loop = mesh.loops[loop_idx]
            vert = mesh.vertices[loop.vertex_index]
            co = obj.matrix_world @ vert.co

            # Project X and Z to UV (front view projection)
            u = (co.x - mn.x) / (mx.x - mn.x) if (mx.x - mn.x) > 0.0001 else 0.5
            v = (co.z - mn.z) / (mx.z - mn.z) if (mx.z - mn.z) > 0.0001 else 0.5

            uv_layer.data[loop_idx].uv = (u, v)

print("Applied front-view UV projection")

# Create silhouette cutter from alpha channel for clean boolean cut
print("Creating silhouette cutter from alpha...")

# Load alpha image and find contours
from PIL import Image as PILImage
import numpy as np
alpha_img = PILImage.open(tex_path).convert('RGBA')
alpha_array = np.array(alpha_img)[:, :, 3]  # Get alpha channel

# Find bounding box of non-transparent pixels
rows = np.any(alpha_array > 25, axis=1)
cols = np.any(alpha_array > 25, axis=0)
if rows.any() and cols.any():
    y_min, y_max = np.where(rows)[0][[0, -1]]
    x_min, x_max = np.where(cols)[0][[0, -1]]
else:
    y_min, y_max, x_min, x_max = 0, alpha_array.shape[0], 0, alpha_array.shape[1]

# Create a simple rectangular cutter based on figure bounds
# Map pixel coords to world coords (matching the lithophane dimensions)
img_h, img_w = alpha_array.shape
lit_width = final_dims.x
lit_height = final_dims.z

# Convert pixel bounds to world coords
world_x_min = final_mn.x + (x_min / img_w) * lit_width
world_x_max = final_mn.x + (x_max / img_w) * lit_width
world_z_min = final_mn.z + ((img_h - y_max) / img_h) * lit_height
world_z_max = final_mn.z + ((img_h - y_min) / img_h) * lit_height

cutter_width = world_x_max - world_x_min
cutter_height = world_z_max - world_z_min
cutter_center_x = (world_x_min + world_x_max) / 2
cutter_center_z = (world_z_min + world_z_max) / 2

print(f"Figure bounds: X({world_x_min*1000:.1f} to {world_x_max*1000:.1f}mm), Z({world_z_min*1000:.1f} to {world_z_max*1000:.1f}mm)")

# Create cutter box that matches the figure silhouette bounds
cutter_depth = final_dims.y * 2  # Deep enough to cut through

bpy.ops.mesh.primitive_cube_add(size=1, location=(cutter_center_x, (final_mn.y + final_mx.y)/2, cutter_center_z))
cutter = bpy.context.object
cutter.name = "SilhouetteCutter"
cutter.scale = (cutter_width, cutter_depth, cutter_height)
select_only(cutter)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
print(f"Cutter size: {cutter_width*1000:.1f}mm x {cutter_height*1000:.1f}mm")

# Use boolean INTERSECT to cut lithophane to silhouette bounds
select_only(obj)
bool_mod = obj.modifiers.new(name="CutSilhouette", type='BOOLEAN')
bool_mod.operation = 'INTERSECT'
bool_mod.object = cutter
bool_mod.solver = 'EXACT'
bpy.ops.object.modifier_apply(modifier="CutSilhouette")

# Remove cutter
bpy.data.objects.remove(cutter, do_unlink=True)

print("Applied silhouette boolean cut")

# Basic mesh cleanup
select_only(obj)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.remove_doubles(threshold=0.0001)
bpy.ops.mesh.delete_loose()
bpy.ops.object.mode_set(mode='OBJECT')

# Apply shade smooth
select_only(obj)
bpy.ops.object.shade_smooth()

# Update dimensions after alpha cut
bpy.context.view_layer.update()
cut_dims = world_dims(obj)
cut_mn, cut_mx = world_aabb(obj)
print(f"After alpha cut: {cut_dims.x*1000:.2f}mm x {cut_dims.z*1000:.2f}mm")

# Position model with bottom at Z=0
obj.location.z = -cut_mn.z
bpy.context.view_layer.update()
cut_mn, cut_mx = world_aabb(obj)

# Create base plane - full 130mm x 170mm, VERTICAL (backdrop behind figure)
base_width = target_width_m   # 130mm
base_height = target_height_m  # 170mm
base_thickness = 0.003  # 3mm thick base

# First, position the figure
obj.location.x = 0
obj.location.y = 0  # Start at origin
figure_center_z = (cut_mn.z + cut_mx.z) / 2
obj.location.z = (base_height / 2) - figure_center_z - 0.079 + 0.16  # Adjusted +160mm on Z

bpy.context.view_layer.update()

# Get updated figure bounds after repositioning
fig_mn, fig_mx = world_aabb(obj)

# Create vertical base plate (standing upright behind figure)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
base = bpy.context.object
base.name = "BasePlane"
base.scale = (base_width, base_thickness, base_height)  # X=width, Y=thickness, Z=height
select_only(base)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

# Calculate figure depth for embedding
fig_depth = fig_mx.y - fig_mn.y
embed_percent = 0.30  # 30% embedded into base plate
embed_distance = fig_depth * embed_percent

# Position base plate: front surface at figure's back minus embed distance
# Base front = base.location.y - base_thickness/2
# We want base front at: fig_mx.y - embed_distance
base.location = (0, (fig_mx.y - embed_distance) + base_thickness / 2, base_height / 2)

bpy.context.view_layer.update()

print(f"Figure depth: {fig_depth*1000:.2f}mm, embedding {embed_percent*100:.0f}% = {embed_distance*1000:.2f}mm into base plate")

# Cut off any part of figure that goes past the back of base plate using boolean
base_back_y = base.location.y + base_thickness / 2

# Create a cutting box behind the base plate
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, base_back_y + 0.5, base_height / 2))
cutter = bpy.context.object
cutter.name = "Cutter"
cutter.scale = (base_width * 2, 1.0, base_height * 2)  # Large box behind base
select_only(cutter)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

# Apply boolean difference to remove figure parts inside cutter
select_only(obj)
bool_mod = obj.modifiers.new(name="CutBack", type='BOOLEAN')
bool_mod.operation = 'DIFFERENCE'
bool_mod.object = cutter
bool_mod.solver = 'EXACT'
bpy.ops.object.modifier_apply(modifier="CutBack")

# Remove cutter
bpy.data.objects.remove(cutter, do_unlink=True)

print(f"Cut off figure parts behind base plate (Y > {base_back_y*1000:.2f}mm)")

# Hide base plate from render (only export to STL, not in texture render)
base.hide_render = True

# Create base material (neutral light gray) - for viewport only
base_mat = bpy.data.materials.new(name="BaseMaterial")
base_mat.use_nodes = True
base_nodes = base_mat.node_tree.nodes
base_links = base_mat.node_tree.links

for node in list(base_nodes):
    base_nodes.remove(node)

base_output = base_nodes.new('ShaderNodeOutputMaterial')
base_bsdf = base_nodes.new('ShaderNodeBsdfDiffuse')
base_bsdf.inputs['Color'].default_value = (0.85, 0.85, 0.85, 1.0)
base_links.new(base_bsdf.outputs['BSDF'], base_output.inputs['Surface'])
base.data.materials.append(base_mat)

print(f"Added base plane: {base_width*1000:.2f}mm x {base_height*1000:.2f}mm x {base_thickness*1000:.2f}mm")

# Create textured material for the lithophane
# Use PRINCIPLED BSDF for realistic rendering
litho_mat = bpy.data.materials.new(name="LithophaneMaterial")
litho_mat.use_nodes = True
nodes = litho_mat.node_tree.nodes
links = litho_mat.node_tree.links

for node in list(nodes):
    nodes.remove(node)

output_node = nodes.new('ShaderNodeOutputMaterial')
output_node.location = (600, 0)

# Use simple EMISSION shader for flat colors
emission_node = nodes.new('ShaderNodeEmission')
emission_node.location = (400, 0)
emission_node.inputs['Strength'].default_value = 1.0

# Texture node
tex_node = nodes.new('ShaderNodeTexImage')
tex_node.location = (0, 0)
tex_node.image = tex_image
tex_node.interpolation = 'Linear'
tex_node.extension = 'EXTEND'  # Extend edge colors instead of black

# Connect texture to emission
links.new(tex_node.outputs['Color'], emission_node.inputs['Color'])
links.new(emission_node.outputs['Emission'], output_node.inputs['Surface'])

# Enable backface culling to hide faces with bad UV (sides/back of mesh)
litho_mat.use_backface_culling = True

obj.data.materials.clear()
obj.data.materials.append(litho_mat)

# Delete temporary camera
bpy.data.objects.remove(temp_camera, do_unlink=True)

# Setup render camera - frame the full base plate
cam_distance = 0.5
scene_center_z = base_height / 2  # Center on the base plate

bpy.ops.object.camera_add(location=(0, -cam_distance, scene_center_z))
camera = bpy.context.object
camera.name = "RenderCamera"
camera.data.type = 'ORTHO'
camera.data.ortho_scale = base_height  # Match base plate height (170mm)
camera.rotation_euler = (math.radians(90), 0, 0)
bpy.context.scene.camera = camera

# Setup EVEN BRIGHT LIGHTING for UV print quality
# Use multiple area lights from different angles for soft, even illumination

# Front light (main)
bpy.ops.object.light_add(type='AREA', location=(0, -0.4, scene_center_z))
front_light = bpy.context.object
front_light.name = "FrontLight"
front_light.data.energy = 1
front_light.data.size = 0.2
front_light.rotation_euler = (math.radians(90), 0, 0)

# Top light
bpy.ops.object.light_add(type='AREA', location=(0, -0.1, cut_mx.z + 0.3))
top_light = bpy.context.object
top_light.name = "TopLight"
top_light.data.energy = 1
top_light.data.size = 0.4
top_light.rotation_euler = (0, 0, 0)

# Left fill light
bpy.ops.object.light_add(type='AREA', location=(-0.3, -0.2, scene_center_z))
left_light = bpy.context.object
left_light.name = "LeftFill"
left_light.data.energy = 1
left_light.data.size = 0.2
left_light.rotation_euler = (math.radians(90), 0, math.radians(-45))

# Right fill light
bpy.ops.object.light_add(type='AREA', location=(0.3, -0.2, scene_center_z))
right_light = bpy.context.object
right_light.name = "RightFill"
right_light.data.energy = 1
right_light.data.size = 0.2
right_light.rotation_euler = (math.radians(90), 0, math.radians(45))

# Bottom fill (reduces harsh shadows)
bpy.ops.object.light_add(type='AREA', location=(0, -0.2, -0.1))
bottom_light = bpy.context.object
bottom_light.name = "BottomFill"
bottom_light.data.energy = 1
bottom_light.data.size = 0.2
bottom_light.rotation_euler = (math.radians(180), 0, 0)

print("Added 5-point even lighting setup")

# Setup world background - pure black (transparent in final render)
world = bpy.data.worlds.new(name="CleanWorld")
bpy.context.scene.world = world
world.use_nodes = True
world_nodes = world.node_tree.nodes
world_links = world.node_tree.links

for node in list(world_nodes):
    world_nodes.remove(node)

world_output = world_nodes.new('ShaderNodeOutputWorld')
world_bg = world_nodes.new('ShaderNodeBackground')
world_bg.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0)  # Black - will be transparent
world_bg.inputs['Strength'].default_value = 0.0  # No ambient light
world_links.new(world_bg.outputs['Background'], world_output.inputs['Surface'])

# Render settings - match base plate dimensions (130x170mm)
pixels_per_mm = 8  # Match input resolution (no upscaling, crisp output)
render_width = int(base_width * 1000 * pixels_per_mm)   # 130mm * 20 = 2600px
render_height = int(base_height * 1000 * pixels_per_mm)  # 170mm * 20 = 3400px

print(f"Render size: {render_width} x {render_height} pixels")

bpy.context.scene.render.resolution_x = render_width
bpy.context.scene.render.resolution_y = render_height
bpy.context.scene.render.resolution_percentage = 100
bpy.context.scene.render.film_transparent = True  # Transparent background for UV print
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.image_settings.color_mode = 'RGBA'  # Include alpha channel

# Setup GPU rendering with higher quality
setup_gpu_cycles()

# Instead of rendering from 3D mesh (which has UV artifacts), use the clean original 2D image
# and position it to match the STL figure bounds on the 130x170mm canvas

output_render = "/workspace/texture_render_130x170.png"

# Get final figure bounds after all positioning
fig_final_mn, fig_final_mx = world_aabb(obj)

# Figure position on base plate (convert to mm)
# Base plate: 130mm wide (centered at X=0), 170mm tall (Z from 0 to 170mm)
fig_x_min_mm = (fig_final_mn.x + base_width/2) * 1000  # Offset from left edge
fig_x_max_mm = (fig_final_mx.x + base_width/2) * 1000
fig_z_min_mm = fig_final_mn.z * 1000  # Z position (bottom of figure)
fig_z_max_mm = fig_final_mx.z * 1000  # Z position (top of figure)

fig_width_mm = fig_x_max_mm - fig_x_min_mm
fig_height_mm = fig_z_max_mm - fig_z_min_mm

print(f"Figure position on canvas: X({fig_x_min_mm:.1f} to {fig_x_max_mm:.1f}mm), Z({fig_z_min_mm:.1f} to {fig_z_max_mm:.1f}mm)")
print(f"Figure size: {fig_width_mm:.1f}mm x {fig_height_mm:.1f}mm")

# Load original clean image
original_img = Image.open(tex_path_original).convert('RGBA')
orig_w, orig_h = original_img.size

# Find content bounds in original image (non-transparent pixels)
import numpy as np
alpha_arr = np.array(original_img)[:, :, 3]
rows = np.any(alpha_arr > 25, axis=1)
cols = np.any(alpha_arr > 25, axis=0)
y_min, y_max = np.where(rows)[0][[0, -1]]
x_min, x_max = np.where(cols)[0][[0, -1]]

# Crop to content
content_img = original_img.crop((x_min, y_min, x_max + 1, y_max + 1))
content_w, content_h = content_img.size
print(f"Original image content bounds: ({x_min}, {y_min}) to ({x_max}, {y_max})")

# Calculate target size in pixels on canvas
fig_width_px = int(fig_width_mm * pixels_per_mm)
fig_height_px = int(fig_height_mm * pixels_per_mm)

# Resize content to match figure size on canvas
resized_img = content_img.resize((fig_width_px, fig_height_px), Image.Resampling.LANCZOS)

# Create canvas (130mm x 170mm)
canvas = Image.new('RGBA', (render_width, render_height), (0, 0, 0, 0))

# Calculate paste position (canvas Y=0 is top, so flip Z)
paste_x = int(fig_x_min_mm * pixels_per_mm)
paste_y = int((base_height * 1000 - fig_z_max_mm) * pixels_per_mm)  # Flip Y axis

# Paste figure onto canvas
canvas.paste(resized_img, (paste_x, paste_y), resized_img)

# Save with correct DPI
dpi = int(pixels_per_mm * 25.4)
canvas.save(output_render, dpi=(dpi, dpi))

print(f"Created clean texture from original 2D image: {output_render}")
print(f"Size: {render_width}x{render_height} pixels, DPI: {dpi} (130mm x 170mm)")

# Export the modified STL (with alpha cutout)
select_only(obj)

# Create export copy scaled to mm
bpy.ops.object.duplicate()
export_obj = bpy.context.active_object
export_obj.name = "Lithophane_Export"
export_obj.location *= 1000  # Scale location to mm
export_obj.scale *= 1000  # Convert mesh to mm
select_only(export_obj)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

output_stl = "/workspace/lithophane_alpha_cut.stl"
bpy.ops.wm.stl_export(filepath=output_stl, export_selected_objects=True)
print(f"Exported STL to: {output_stl}")

# Also export base
select_only(base)
bpy.ops.object.duplicate()
base_export = bpy.context.active_object
base_export.name = "Base_Export"
base_export.location *= 1000  # Scale location to mm
base_export.scale *= 1000  # Convert mesh to mm
select_only(base_export)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

output_base_stl = "/workspace/lithophane_base.stl"
bpy.ops.wm.stl_export(filepath=output_base_stl, export_selected_objects=True)
print(f"Exported base STL to: {output_base_stl}")

# Export COMBINED STL (figure + base plate together) - 130mm x 170mm
# Use boolean UNION to properly merge meshes (fixes "floating regions" warning)
select_only(export_obj)
bool_union = export_obj.modifiers.new(name="UnionBase", type='BOOLEAN')
bool_union.operation = 'UNION'
bool_union.object = base_export
bool_union.solver = 'EXACT'
bpy.ops.object.modifier_apply(modifier="UnionBase")

# Remove the base_export since it's now merged
bpy.data.objects.remove(base_export, do_unlink=True)

export_obj.name = "Combined_Export"

output_combined_stl = "/workspace/lithophane_combined_130x170.stl"
bpy.ops.wm.stl_export(filepath=output_combined_stl, export_selected_objects=True)
print(f"Exported combined STL to: {output_combined_stl}")

# Clean up
bpy.data.objects.remove(export_obj, do_unlink=True)

# Save blend file
bpy.ops.wm.save_as_mainfile(filepath="/workspace/lithophane_project.blend")

print("\n=== COMPLETE ===")
print(f"- Combined STL (figure + base): {output_combined_stl} (130mm x 170mm)")
print(f"- Figure only STL: {output_stl}")
print(f"- Base plate only STL: {output_base_stl}")
print(f"- Texture render: {output_render} (130mm x 170mm at 20px/mm)")
print(f"- Blender project: /workspace/lithophane_project.blend")
