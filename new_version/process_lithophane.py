import bpy
import os
import math
from mathutils import Vector, Matrix

# ----------------------------- Helper functions -----------------------------
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
    """Get world-space dimensions"""
    mn, mx = world_aabb(obj)
    return mx - mn

def select_only(obj):
    """Select only this object"""
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def setup_gpu_cycles():
    """Setup Cycles with GPU acceleration"""
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 64
    sc.cycles.use_denoising = True
    sc.cycles.device = 'GPU'

    try:
        prefs = bpy.context.preferences
        cprefs = prefs.addons['cycles'].preferences

        for compute_type in ['OPTIX', 'CUDA', 'NONE']:
            try:
                cprefs.compute_device_type = compute_type
                cprefs.get_devices()

                gpu_found = False
                for device in cprefs.devices:
                    if device.type in ['CUDA', 'OPTIX']:
                        device.use = True
                        gpu_found = True
                        print(f"Enabled GPU: {device.name} ({device.type})")

                if gpu_found:
                    if compute_type == 'OPTIX':
                        sc.cycles.denoiser = 'OPTIX'
                    print(f"Using {compute_type} for rendering")
                    return
            except Exception as e:
                print(f"{compute_type} not available: {e}")
                continue

        print("Falling back to CPU rendering")
        sc.cycles.device = 'CPU'
    except Exception as e:
        print(f"GPU setup failed: {e}, using CPU")
        sc.cycles.device = 'CPU'

# ----------------------------- Main script -----------------------------

# Clear scene completely
bpy.ops.wm.read_factory_settings(use_empty=True)

# Import the STL
stl_path = "/workspace/Lithophane_Blended_Layers (1).stl"
bpy.ops.wm.stl_import(filepath=stl_path)

# Get the imported object
if not bpy.context.selected_objects:
    print("ERROR: No objects imported!")
    raise RuntimeError("STL import failed")

obj = bpy.context.selected_objects[0]
obj.name = "Lithophane"
bpy.context.view_layer.objects.active = obj

# Force scene update
bpy.context.view_layer.update()

# Get dimensions
dims = world_dims(obj)
mn, mx = world_aabb(obj)

orig_width = dims.x
orig_depth = dims.y
orig_height = dims.z

print(f"Imported dimensions (BU): width={orig_width:.4f}, depth={orig_depth:.4f}, height={orig_height:.4f}")
print(f"Bounding box: min=({mn.x:.4f}, {mn.y:.4f}, {mn.z:.4f}), max=({mx.x:.4f}, {mx.y:.4f}, {mx.z:.4f})")

# Target dimensions in meters (for Blender internal)
target_width_m = 0.130   # 130mm = 0.130m
target_height_m = 0.170  # 170mm = 0.170m

# Calculate scale factors
if orig_width > 0.001 and orig_height > 0.001:
    scale_x = target_width_m / orig_width
    scale_z = target_height_m / orig_height
    print(f"Scale factors: X={scale_x:.6f}, Z={scale_z:.6f}")
else:
    print(f"ERROR: Dimensions too small: {orig_width}, {orig_height}")
    scale_x = 1.0
    scale_z = 1.0

# Apply scaling
obj.scale.x *= scale_x
obj.scale.z *= scale_z
obj.scale.y *= scale_x  # Scale depth proportionally with width

bpy.context.view_layer.update()
select_only(obj)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

# Center the object at origin first
bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
obj.location = (0, 0, 0)
bpy.context.view_layer.update()

# Get final dimensions
final_dims = world_dims(obj)
final_mn, final_mx = world_aabb(obj)

print(f"Final dimensions (m): width={final_dims.x:.4f}, depth={final_dims.y:.4f}, height={final_dims.z:.4f}")
print(f"Final dimensions (mm): width={final_dims.x*1000:.2f}, depth={final_dims.y*1000:.2f}, height={final_dims.z*1000:.2f}")

# For STL export, create a properly positioned copy in mm
select_only(obj)
bpy.ops.object.duplicate()
export_obj = bpy.context.active_object
export_obj.name = "Lithophane_Export"

# Reset position to origin before scaling
export_obj.location = (0, 0, 0)
bpy.context.view_layer.update()

# Scale up by 1000 to convert meters to mm for STL file
export_obj.scale *= 1000
select_only(export_obj)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# Verify export dimensions
export_dims = world_dims(export_obj)
print(f"Export STL dimensions (mm): width={export_dims.x:.2f}, depth={export_dims.y:.2f}, height={export_dims.z:.2f}")

# Export the STL
output_stl = "/workspace/lithophane_130x170.stl"
select_only(export_obj)
bpy.ops.wm.stl_export(filepath=output_stl, export_selected_objects=True)
print(f"Exported STL to: {output_stl}")

# Delete export copy
bpy.data.objects.remove(export_obj, do_unlink=True)

# Position the original object for rendering (bottom at Z=0, centered on XY)
obj.location = (0, 0, final_dims.z / 2)
bpy.context.view_layer.update()

# Now setup camera for texture rendering
# Camera looking at front face (from -Y direction toward +Y)
cam_distance = 0.5  # 0.5m away from object

bpy.ops.object.camera_add(location=(0, -cam_distance, final_dims.z / 2))
camera = bpy.context.object
camera.name = "RenderCamera"
camera.data.type = 'ORTHO'
camera.data.ortho_scale = target_height_m  # Height is the larger dimension
camera.rotation_euler = (math.radians(90), 0, 0)
bpy.context.scene.camera = camera

# Set render resolution (20 pixels per mm)
render_width = 2600   # 130mm * 20
render_height = 3400  # 170mm * 20

bpy.context.scene.render.resolution_x = render_width
bpy.context.scene.render.resolution_y = render_height
bpy.context.scene.render.resolution_percentage = 100
bpy.context.scene.render.film_transparent = True
bpy.context.scene.render.image_settings.file_format = 'PNG'
bpy.context.scene.render.image_settings.color_mode = 'RGBA'

# Load texture image
tex_path = "/workspace/base_character_20260122_212103_nobg.png"
tex_image = bpy.data.images.load(tex_path)

# Hide the lithophane for texture-only render
obj.hide_render = True
obj.hide_viewport = True

# Create a plane that exactly matches the camera view for texture rendering
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, target_height_m / 2))
plane = bpy.context.object
plane.name = "TexturePlane"

# Scale plane to target size and rotate to face camera
plane.scale.x = target_width_m
plane.scale.y = target_height_m
plane.rotation_euler = (math.radians(90), 0, 0)

select_only(plane)
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

# Create emission material for clean texture render with proper transparency
mat = bpy.data.materials.new(name="TextureMaterial")
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links

# Clear and rebuild nodes
for node in list(nodes):
    nodes.remove(node)

output_node = nodes.new('ShaderNodeOutputMaterial')
output_node.location = (400, 0)

emission_node = nodes.new('ShaderNodeEmission')
emission_node.location = (200, 100)
emission_node.inputs['Strength'].default_value = 1.0

transparent_node = nodes.new('ShaderNodeBsdfTransparent')
transparent_node.location = (200, -100)

mix_node = nodes.new('ShaderNodeMixShader')
mix_node.location = (300, 0)

tex_node = nodes.new('ShaderNodeTexImage')
tex_node.location = (0, 0)
tex_node.image = tex_image

# Connect for transparent background
links.new(tex_node.outputs['Color'], emission_node.inputs['Color'])
links.new(tex_node.outputs['Alpha'], mix_node.inputs['Fac'])
links.new(transparent_node.outputs['BSDF'], mix_node.inputs[1])
links.new(emission_node.outputs['Emission'], mix_node.inputs[2])
links.new(mix_node.outputs['Shader'], output_node.inputs['Surface'])

mat.blend_method = 'BLEND'
plane.data.materials.append(mat)

# Setup GPU-accelerated Cycles rendering
setup_gpu_cycles()

# Add simple lighting
bpy.ops.object.light_add(type='SUN', location=(0, -0.2, 0.2))
sun = bpy.context.object
sun.data.energy = 1

# Render the texture
output_render = "/workspace/texture_render_130x170.png"
bpy.context.scene.render.filepath = output_render
bpy.ops.render.render(write_still=True)
print(f"Rendered texture to: {output_render}")

# Save blend file
bpy.ops.wm.save_as_mainfile(filepath="/workspace/lithophane_project.blend")
print("Saved project file")

print("\n=== COMPLETE ===")
print(f"STL file: {output_stl} (dimensions: 130mm x 170mm)")
print(f"Texture render: {output_render} ({render_width}x{render_height} pixels)")
print(f"Physical size: 130mm x 170mm")
print(f"The texture PNG and STL are aligned for UV printing on 3D printed model")
