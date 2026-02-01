"""
Blender Starter Pack - Displacement-based Lithophane
Uses depth PNG for displacement and original PNG for texture
"""

import bpy
import os
import sys
import argparse
from mathutils import Vector

# ============================================================
# CONFIGURATION
# ============================================================
CARD_WIDTH = 130.0   # mm
CARD_HEIGHT = 170.0  # mm
CARD_THICKNESS = 3.0 # mm

SUBDIVIDE_CUTS = 100  # Number of subdivision cuts
SUBSURF_LEVELS = 4    # Catmull-Clark render levels
DECIMATE_RATIO = 0.3  # Decimate ratio for STL export (0.3 = keep 30% of polygons)
DISPLACEMENT_STRENGTH_FIGURE = 0.010  # Displacement strength for figure (in meters, ~10mm)
DISPLACEMENT_STRENGTH_ACCESSORIES = 0.025  # Displacement strength for accessories (in meters, ~25mm)

# Layout Configuration
UPPER_RATIO = 0.15  # 15% for text/title area at top
FIGURE_WIDTH_RATIO = 3.0 / 5.0  # Figure takes 3/5 of width (left side)
ACC_HEIGHT_RATIO = 2.0 / 3.0  # Accessories column is 2/3 of card height
MARGIN_FIGURE = 5.0  # mm margin around figure
MARGIN_ACCESSORIES = 3.0  # mm margin around accessories
SIZE_BOOST_FIGURE = 1.32  # Target: ~90mm x 135mm
SIZE_BOOST_ACCESSORIES = 1.62  # Target: ~34.5mm x 51.8mm
MESH_PLANE_SINK_DEPTH = 1.0  # How deep to sink mesh plane into card (mm) - deeper to hide from corners

# Text Configuration
TEXT_SIZE_INITIAL = 20.0  # Initial font size (will be scaled to fit)
TEXT_EXTRUDE = 0.8  # Text extrusion depth (mm)
TEXT_LIFT = 0.1  # Lift above card surface (mm)
TEXT_TOP_MARGIN = 10.0  # Margin from top of card (mm)

# Max bounds for text (mm)
TITLE_MAX_WIDTH = 114.0
TITLE_MAX_HEIGHT = 11.7
SUBTITLE_MAX_WIDTH = 64.6
SUBTITLE_MAX_HEIGHT = 7.43

# Predefined colors (RGBA)
TEXT_COLORS = {
    'red': (1.0, 0.0, 0.0, 1.0),
    'blue': (0.0, 0.3, 0.8, 1.0),
    'green': (0.0, 0.6, 0.2, 1.0),
    'white': (1.0, 1.0, 1.0, 1.0),
    'black': (0.0, 0.0, 0.0, 1.0),
    'yellow': (1.0, 0.85, 0.0, 1.0),
    'orange': (1.0, 0.5, 0.0, 1.0),
    'purple': (0.6, 0.2, 0.8, 1.0),
    'pink': (1.0, 0.4, 0.7, 1.0),
    'gold': (0.85, 0.65, 0.13, 1.0),
}

# Background colors (RGB tuple for PIL, 0-255)
BACKGROUND_COLORS = {
    'white': (255, 255, 255),
    'black': (0, 0, 0),
    'red': (255, 0, 0),
    'blue': (0, 77, 204),
    'green': (0, 153, 51),
    'yellow': (255, 217, 0),
    'orange': (255, 128, 0),
    'purple': (153, 51, 204),
    'pink': (255, 102, 178),
    'gray': (128, 128, 128),
    'navy': (0, 0, 128),
    'teal': (0, 128, 128),
    'maroon': (128, 0, 0),
    'olive': (128, 128, 0),
    'silver': (192, 192, 192),
    'transparent': None,  # Keep transparent (no background)
}


# ============================================================
# UTILITY FUNCTIONS
# ============================================================
def clear_scene():
    """Clear everything"""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def select_only(obj):
    """Select only this object"""
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def print_obj_info(obj, label=""):
    """Print object info"""
    bpy.context.view_layer.update()
    dims = obj.dimensions
    print(f"  {label}")
    print(f"    Position: ({obj.location.x*1000:.1f}, {obj.location.y*1000:.1f}, {obj.location.z*1000:.1f}) mm")
    print(f"    Dimensions: {dims.x*1000:.1f} x {dims.y*1000:.1f} x {dims.z*1000:.1f} mm")


# ============================================================
# POSITIONING HELPER FUNCTIONS
# ============================================================
def world_aabb(obj):
    """Get world-space axis-aligned bounding box"""
    bpy.context.view_layer.update()
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


def center_xy(obj):
    """Center object at origin in XY plane"""
    mn, mx = world_aabb(obj)
    cx = 0.5 * (mn.x + mx.x)
    cy = 0.5 * (mn.y + mx.y)
    obj.location.x -= cx
    obj.location.y -= cy
    bpy.context.view_layer.update()


def rest_on_z0(obj):
    """Move object so its bottom rests on Z=0"""
    mn, mx = world_aabb(obj)
    obj.location.z -= mn.z
    bpy.context.view_layer.update()


def top_z(obj):
    """Get top Z coordinate of object"""
    _, mx = world_aabb(obj)
    return float(mx.z)


def bottom_z(obj):
    """Get bottom Z coordinate of object"""
    mn, _ = world_aabb(obj)
    return float(mn.z)


def uniform_fit(obj, target_w, target_h, margin=0.0, size_boost=1.0):
    """
    Uniformly scale object to fit within target_w x target_h minus margin.
    Applies size_boost multiplier after fitting.
    Returns the final world-space depth (Z-size) after scaling.
    """
    eps = 1e-9
    d = world_dims(obj)
    if d.x < eps or d.y < eps:
        return float(d.z)

    # Convert to meters (target_w/h are in mm)
    tw = max(1e-6, float(target_w) / 1000.0 - 2.0 * margin / 1000.0)
    th = max(1e-6, float(target_h) / 1000.0 - 2.0 * margin / 1000.0)

    scale_x = tw / max(d.x, eps)
    scale_y = th / max(d.y, eps)
    s = min(scale_x, scale_y) * size_boost  # Apply size boost

    obj.scale *= s
    bpy.context.view_layer.update()

    # Return new depth
    return float(world_dims(obj).z)


def snap_bottom_to_base_top(obj, base_obj, z_offset=0.0):
    """Move object so its bottom sits on top of base object"""
    target = top_z(base_obj) + float(z_offset)
    dz = target - bottom_z(obj)
    obj.location.z += dz
    bpy.context.view_layer.update()


def match_top_to_height(obj, target_top_z):
    """Move object so its top matches the target Z height"""
    current_top = top_z(obj)
    dz = target_top_z - current_top
    obj.location.z += dz
    bpy.context.view_layer.update()


def apply_shade_auto_smooth(obj, angle=30.0):
    """
    Apply shade smooth with auto smooth based on angle.
    In Blender 4.1+/5.0, uses the mesh smooth_by_angle operator.

    Args:
        obj: The mesh object
        angle: Auto smooth angle in degrees (default 30)
    """
    import math

    print(f"  Applying shade auto smooth (angle: {angle}°)...")

    select_only(obj)

    # In Blender 4.1+/5.0, use the mesh operator in edit mode
    try:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        # This operator sets smooth shading by angle
        bpy.ops.mesh.set_shading_smooth_by_angle(angle=math.radians(angle))
        bpy.ops.object.mode_set(mode='OBJECT')
        print(f"  Applied smooth by angle")
    except Exception as e:
        print(f"  Trying alternative method... ({e})")
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
            # Fallback: just apply smooth shading
            bpy.ops.object.shade_smooth()
            print(f"  Applied smooth shading (no angle)")
        except Exception as e2:
            print(f"  WARNING: Could not apply auto smooth: {e2}")

    bpy.context.view_layer.update()


def sink_mesh_plane_into_card(obj, card_thickness, sink_depth_mm=0.5):
    """
    Push the model down so its mesh plane (flat base) is inside the base plate.
    The mesh plane sits at Z=0 after displacement, so we move it down into the card.

    Args:
        obj: The mesh object
        card_thickness: Thickness of the card in meters
        sink_depth_mm: How deep to sink the mesh plane into the card (in mm)
    """
    sink_depth = sink_depth_mm / 1000.0  # Convert to meters

    print(f"  Sinking mesh plane {sink_depth_mm:.1f}mm into card...")

    select_only(obj)
    bpy.context.view_layer.update()

    # The mesh plane is at the bottom of the displaced mesh
    # Move object down so the mesh plane is inside the card
    current_bottom_z = bottom_z(obj)

    # Target: mesh plane at -sink_depth (inside the card, which goes from Z=0 to Z=-card_thickness)
    move_amount = current_bottom_z - (-sink_depth)
    obj.location.z -= move_amount
    bpy.context.view_layer.update()

    new_bottom = bottom_z(obj)
    print(f"  Moved down {move_amount*1000:.2f}mm (mesh plane now at {new_bottom*1000:.2f}mm, inside card)")

def cut_below_card(obj, card_thickness):
    """
    Cut anything below the card bottom using boolean.
    """
    card_bottom_z = -card_thickness

    select_only(obj)
    bpy.context.view_layer.update()

    # Check if anything is below the card bottom
    current_bottom = bottom_z(obj)
    if current_bottom >= card_bottom_z:
        print(f"  Nothing to cut below (bottom at {current_bottom*1000:.1f}mm, card bottom at {card_bottom_z*1000:.1f}mm)")
        return

    print(f"  Cutting geometry below {card_bottom_z*1000:.1f}mm...")

    # Create a cutter cube that covers everything below card_bottom_z
    obj_bounds = world_aabb(obj)
    cutter_size = max(obj_bounds[1].x - obj_bounds[0].x,
                      obj_bounds[1].y - obj_bounds[0].y) * 2

    # Create cutter below the card
    bpy.ops.mesh.primitive_cube_add(
        size=1,
        location=(obj.location.x, obj.location.y, card_bottom_z - 0.1)
    )
    cutter = bpy.context.object
    cutter.name = "TempCutter"
    cutter.scale = (cutter_size, cutter_size, 0.2)
    bpy.ops.object.transform_apply(scale=True)

    # Apply boolean difference
    select_only(obj)
    bool_mod = obj.modifiers.new(name="CutBottom", type='BOOLEAN')
    bool_mod.operation = 'DIFFERENCE'
    bool_mod.object = cutter
    bool_mod.solver = 'EXACT'

    bpy.ops.object.modifier_apply(modifier="CutBottom")

    # Delete the cutter
    select_only(cutter)
    bpy.ops.object.delete()

    select_only(obj)
    bpy.context.view_layer.update()
    print(f"  Cut below complete")


def trim_to_card_boundaries(obj, card_width, card_height, card_thickness):
    """
    Trim any geometry that extends outside the card boundaries in XY plane.
    Uses boolean intersection with a box matching the card dimensions.
    """
    print(f"  Trimming to card boundaries ({card_width*1000:.0f}x{card_height*1000:.0f}mm)...")

    select_only(obj)
    bpy.context.view_layer.update()

    # Get object bounds to check if trimming is needed
    obj_bounds = world_aabb(obj)
    card_half_w = card_width / 2.0
    card_half_h = card_height / 2.0

    # Check if object extends outside card boundaries
    extends_outside = (
        obj_bounds[0].x < -card_half_w or obj_bounds[1].x > card_half_w or
        obj_bounds[0].y < -card_half_h or obj_bounds[1].y > card_half_h
    )

    if not extends_outside:
        print(f"  Object within card boundaries, no trimming needed")
        return

    # Create a box that matches the card dimensions (for boolean intersection)
    # The box should be tall enough to cover the full Z range of the object
    obj_height = obj_bounds[1].z - obj_bounds[0].z
    box_height = obj_height + 0.02  # Add margin
    box_center_z = (obj_bounds[0].z + obj_bounds[1].z) / 2.0

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, box_center_z))
    trim_box = bpy.context.object
    trim_box.name = "TrimBox"
    trim_box.scale = (card_width, card_height, box_height)
    bpy.ops.object.transform_apply(scale=True)

    # Apply boolean intersection to keep only what's inside the card boundaries
    select_only(obj)
    bool_mod = obj.modifiers.new(name="TrimToCard", type='BOOLEAN')
    bool_mod.operation = 'INTERSECT'
    bool_mod.object = trim_box
    bool_mod.solver = 'EXACT'

    bpy.ops.object.modifier_apply(modifier="TrimToCard")

    # Delete the trim box
    select_only(trim_box)
    bpy.ops.object.delete()

    select_only(obj)
    bpy.context.view_layer.update()
    print(f"  Trimmed to card boundaries")


def remove_transparent_geometry(obj, color_png_path, alpha_threshold=0.1):
    """
    Apply all modifiers and remove faces where the texture alpha is below threshold.
    This removes the flat mesh plane, leaving only the displaced figure.
    Also fills the bottom face and smooths the boundary edges.
    """
    import bmesh
    from PIL import Image
    import numpy as np

    print(f"  Removing transparent geometry (alpha < {alpha_threshold})...")

    # Load the color image to get alpha channel
    if not os.path.exists(color_png_path):
        print(f"  WARNING: Color PNG not found, skipping geometry removal")
        return

    img = Image.open(color_png_path).convert('RGBA')
    img_width, img_height = img.size
    alpha_data = np.array(img)[:, :, 3] / 255.0  # Normalize to 0-1

    # Apply all modifiers to bake displacement into geometry
    select_only(obj)
    bpy.ops.object.convert(target='MESH')  # This applies all modifiers

    # Get mesh data
    mesh = obj.data
    uv_layer = mesh.uv_layers.active

    if not uv_layer:
        print(f"  WARNING: No UV layer found, skipping geometry removal")
        return

    # Create bmesh for editing
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()

    uv_layer_bm = bm.loops.layers.uv.active
    if not uv_layer_bm:
        print(f"  WARNING: No UV layer in bmesh, skipping geometry removal")
        bm.free()
        return

    # Find faces to delete (where alpha is below threshold)
    faces_to_delete = []

    for face in bm.faces:
        # Get average UV coordinate for this face
        uvs = [loop[uv_layer_bm].uv for loop in face.loops]
        avg_u = sum(uv.x for uv in uvs) / len(uvs)
        avg_v = sum(uv.y for uv in uvs) / len(uvs)

        # Convert UV to pixel coordinates (V is flipped in UV space)
        px = int(avg_u * (img_width - 1))
        py = int((1.0 - avg_v) * (img_height - 1))

        # Clamp to image bounds
        px = max(0, min(px, img_width - 1))
        py = max(0, min(py, img_height - 1))

        # Check alpha value
        alpha = alpha_data[py, px]
        if alpha < alpha_threshold:
            faces_to_delete.append(face)

    # Delete the transparent faces
    print(f"  Deleting {len(faces_to_delete)} transparent faces out of {len(bm.faces)} total...")
    bmesh.ops.delete(bm, geom=faces_to_delete, context='FACES')

    # Update mesh before filling
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    # Smooth edges only - DO NOT fill bottom face here (will be done during extrusion)
    print(f"  Smoothing boundary edges...")
    select_only(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')

    # Smooth the boundary vertices to reduce jaggedness
    bpy.ops.mesh.select_mode(type='VERT')
    bpy.ops.mesh.select_non_manifold(extend=False, use_wire=True, use_boundary=True,
                                      use_multi_face=False, use_non_contiguous=False, use_verts=False)

    # Apply vertex smoothing to boundary (multiple iterations for smoother edges)
    for _ in range(5):
        bpy.ops.mesh.vertices_smooth(factor=0.5)

    bpy.ops.object.mode_set(mode='OBJECT')
    mesh.update()

    print(f"  Geometry cleanup complete. Remaining faces: {len(mesh.polygons)}")


def calculate_layout():
    """
    Calculate slot positions for figure and accessories.
    Returns dict with all layout measurements in meters.
    """
    # Convert to meters
    card_w = CARD_WIDTH / 1000.0
    card_h = CARD_HEIGHT / 1000.0

    # Upper band (for text) and lower band (for content)
    H_upper = card_h * UPPER_RATIO
    H_lower = card_h - H_upper

    # Left (figure) and right (accessories) widths
    W_left = card_w * FIGURE_WIDTH_RATIO  # 3/5
    W_right = card_w - W_left  # 2/5

    # Lower band Y bounds (card centered at origin)
    lower_y_min = -card_h / 2.0
    lower_y_max = lower_y_min + H_lower
    lower_y_center = 0.5 * (lower_y_min + lower_y_max)

    # Figure slot
    fig_slot_w = W_left
    fig_slot_h = H_lower

    # Accessories slot (2/3 of card height, vertically centered in lower band)
    acc_slot_w = W_right
    acc_slot_h = card_h * ACC_HEIGHT_RATIO

    # Accessory cells (3 vertical parts)
    acc_cell_h = acc_slot_h / 3.0

    # X centers
    left_x_center = -card_w / 2.0 + fig_slot_w / 2.0
    right_x_center = card_w / 2.0 - acc_slot_w / 2.0

    # Y centers for 3 accessory slots (top, middle, bottom)
    acc_y_center = lower_y_center
    start_y = acc_y_center + (acc_slot_h / 2.0) - acc_cell_h / 2.0
    acc_centers_y = [start_y - i * acc_cell_h for i in range(3)]

    return {
        'card_w': card_w,
        'card_h': card_h,
        'fig_slot_w': fig_slot_w * 1000,  # Convert back to mm for uniform_fit
        'fig_slot_h': fig_slot_h * 1000,
        'fig_x': left_x_center,
        'fig_y': lower_y_center,
        'acc_slot_w': acc_slot_w * 1000,
        'acc_cell_h': acc_cell_h * 1000,
        'acc_x': right_x_center,
        'acc_centers_y': acc_centers_y,
    }


# ============================================================
# STEP 1: CREATE BASE PLATE
# ============================================================
def create_base_plate():
    """
    Create a 130mm x 170mm base plate.
    Card lies flat on XY plane, centered at origin.
    Top surface at Z=0, extends down to Z=-thickness.
    """
    print("\n=== Step 1: Creating Base Plate ===")

    w = CARD_WIDTH / 1000
    h = CARD_HEIGHT / 1000
    t = CARD_THICKNESS / 1000

    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, -t/2))
    card = bpy.context.object
    card.name = "Card"
    card.scale = (w/2, h/2, t/2)

    select_only(card)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    print_obj_info(card, "Base plate created:")
    return card


# ============================================================
# STEP 2: CREATE DISPLACED MESH FROM DEPTH IMAGE
# ============================================================
def create_displaced_mesh(depth_png_path, color_png_path, name="Figure", displacement_strength=None):
    """
    Create a mesh plane with displacement from depth image.

    1. Create mesh plane
    2. Subdivide with 100 cuts
    3. Add displacement modifier with depth PNG
    4. Add subdivision surface modifier (Catmull-Clark, level 4)
    5. Add corrective smooth modifier
    6. Add material with color PNG

    Args:
        displacement_strength: Override displacement strength (in meters). If None, uses default.
    """
    if displacement_strength is None:
        displacement_strength = DISPLACEMENT_STRENGTH_FIGURE
    print(f"\n=== Creating Displaced Mesh: {name} ===")
    print(f"  Depth PNG: {depth_png_path}")
    print(f"  Color PNG: {color_png_path}")

    if not os.path.exists(depth_png_path):
        print(f"  ERROR: Depth PNG not found!")
        return None

    # --- Create mesh plane ---
    print("  Creating mesh plane...")
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    plane = bpy.context.object
    plane.name = name

    # Scale plane to reasonable size (will adjust later)
    # Using aspect ratio from a typical figure (width < height)
    plane.scale = (0.08, 0.12, 1)  # ~80mm x 120mm
    select_only(plane)
    bpy.ops.object.transform_apply(scale=True)

    # --- Subdivide with 100 cuts ---
    print(f"  Subdividing with {SUBDIVIDE_CUTS} cuts...")
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.subdivide(number_cuts=SUBDIVIDE_CUTS)

    # Ensure normals point upward (+Z) so displacement goes outward
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')

    # --- Load depth image as texture ---
    print("  Loading depth image...")
    depth_img = bpy.data.images.load(depth_png_path)
    depth_img.name = f"{name}_depth"
    depth_img.colorspace_settings.name = 'Non-Color'

    # Create texture for displacement
    depth_tex = bpy.data.textures.new(name=f"{name}_DepthTexture", type='IMAGE')
    depth_tex.image = depth_img

    # --- Add Subdivision Surface Modifier FIRST ---
    print(f"  Adding subdivision surface modifier (level {SUBSURF_LEVELS})...")
    subsurf_mod = plane.modifiers.new(name="Subdivision", type='SUBSURF')
    subsurf_mod.subdivision_type = 'CATMULL_CLARK'
    subsurf_mod.render_levels = SUBSURF_LEVELS
    subsurf_mod.levels = SUBSURF_LEVELS  # Viewport levels same as render for STL export

    # --- Add Displacement Modifier SECOND ---
    print(f"  Adding displacement modifier (strength: {displacement_strength})...")
    disp_mod = plane.modifiers.new(name="Displacement", type='DISPLACE')
    disp_mod.texture = depth_tex
    disp_mod.texture_coords = 'UV'
    disp_mod.strength = displacement_strength
    disp_mod.mid_level = 0.0  # Black = no displacement, white = full displacement

    # --- Add Corrective Smooth Modifier THIRD ---
    print("  Adding corrective smooth modifier...")
    smooth_mod = plane.modifiers.new(name="CorrectiveSmooth", type='CORRECTIVE_SMOOTH')
    smooth_mod.use_only_smooth = True
    smooth_mod.iterations = 5
    smooth_mod.smooth_type = 'SIMPLE'

    # --- Create Material with Color PNG and proper transparency ---
    print("  Creating material with color texture and alpha...")
    mat = bpy.data.materials.new(name=f"{name}_Material")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    nodes.clear()

    # Create nodes
    output_node = nodes.new('ShaderNodeOutputMaterial')
    output_node.location = (600, 0)

    # Mix Shader to blend between transparent and color
    mix_node = nodes.new('ShaderNodeMixShader')
    mix_node.location = (400, 0)

    # Transparent BSDF for background
    transparent_node = nodes.new('ShaderNodeBsdfTransparent')
    transparent_node.location = (200, 100)

    # Principled BSDF for the actual color
    bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf_node.location = (200, -100)

    # Image texture
    tex_node = nodes.new('ShaderNodeTexImage')
    tex_node.location = (-200, 0)

    # Load color image
    if os.path.exists(color_png_path):
        color_img = bpy.data.images.load(color_png_path)
        color_img.name = f"{name}_color"
        tex_node.image = color_img
    else:
        print(f"  WARNING: Color PNG not found, using default material")

    # Connect nodes
    # Color to Principled BSDF
    links.new(tex_node.outputs['Color'], bsdf_node.inputs['Base Color'])

    # Alpha controls the mix (0 = transparent, 1 = color)
    links.new(tex_node.outputs['Alpha'], mix_node.inputs['Fac'])

    # Transparent shader to first input (shown when alpha = 0)
    links.new(transparent_node.outputs['BSDF'], mix_node.inputs[1])

    # Principled BSDF to second input (shown when alpha = 1)
    links.new(bsdf_node.outputs['BSDF'], mix_node.inputs[2])

    # Mix output to material output
    links.new(mix_node.outputs['Shader'], output_node.inputs['Surface'])

    # Enable alpha blend mode
    mat.blend_method = 'BLEND'

    # Assign material to plane
    plane.data.materials.append(mat)

    # Keep the mesh plane - don't remove transparent geometry
    # The plane will be pushed into the base plate later

    print_obj_info(plane, "Displaced mesh created:")
    return plane


# ============================================================
# POSITIONING FUNCTIONS
# ============================================================
def position_figure(figure, card, layout):
    """Position the figure in its designated slot (left 3/5 of lower area)

    Returns:
        tuple: (figure_top_z, pre_trim_pos, pre_trim_dims) for texture alignment
    """
    print("\n=== Positioning Figure ===")

    # Center at origin first
    center_xy(figure)
    rest_on_z0(figure)

    # Scale to fit in figure slot with size boost
    uniform_fit(figure, layout['fig_slot_w'], layout['fig_slot_h'], margin=MARGIN_FIGURE, size_boost=SIZE_BOOST_FIGURE)
    print(f"  Scaled to fit in {layout['fig_slot_w']:.0f}x{layout['fig_slot_h']:.0f}mm slot (scale: {SIZE_BOOST_FIGURE})")

    # Center again after scaling
    center_xy(figure)

    # Move to figure slot position
    figure.location.x = layout['fig_x']
    figure.location.y = layout['fig_y']

    # Snap to card surface first
    snap_bottom_to_base_top(figure, card)

    # Sink mesh plane into the base plate (so only displaced parts show above card)
    card_thickness = CARD_THICKNESS / 1000.0  # Convert to meters
    card_width = CARD_WIDTH / 1000.0
    card_height = CARD_HEIGHT / 1000.0
    sink_mesh_plane_into_card(figure, card_thickness, MESH_PLANE_SINK_DEPTH)

    # CAPTURE PRE-TRIM position and dimensions for texture alignment
    bpy.context.view_layer.update()
    pre_trim_min, pre_trim_max = world_aabb(figure)
    pre_trim_center_x = (pre_trim_min.x + pre_trim_max.x) / 2.0
    pre_trim_center_y = (pre_trim_min.y + pre_trim_max.y) / 2.0
    pre_trim_pos = (pre_trim_center_x * 1000, pre_trim_center_y * 1000)  # mm
    pre_trim_dims = (figure.dimensions.x * 1000, figure.dimensions.y * 1000)  # mm
    print(f"  Pre-trim: center=({pre_trim_pos[0]:.1f}, {pre_trim_pos[1]:.1f})mm, dims=({pre_trim_dims[0]:.1f}x{pre_trim_dims[1]:.1f})mm")

    # Trim to card boundaries (cut anything outside XY bounds)
    trim_to_card_boundaries(figure, card_width, card_height, card_thickness)

    # Cut anything below card bottom
    cut_below_card(figure, card_thickness)

    # Apply shade auto smooth
    apply_shade_auto_smooth(figure, angle=30.0)

    # Get figure top Z for matching accessory heights
    figure_top_z = top_z(figure)

    print_obj_info(figure, "Figure positioned:")
    return figure_top_z, pre_trim_pos, pre_trim_dims


def position_accessory(acc, card, layout, index, figure_top_z=None):
    """Position an accessory in its designated slot (right 2/5, stacked vertically)"""
    print(f"\n=== Positioning Accessory {index + 1} ===")

    # Center at origin first
    center_xy(acc)
    rest_on_z0(acc)

    # Scale to fit in accessory cell with size boost
    uniform_fit(acc, layout['acc_slot_w'], layout['acc_cell_h'], margin=MARGIN_ACCESSORIES, size_boost=SIZE_BOOST_ACCESSORIES)
    print(f"  Scaled to fit in {layout['acc_slot_w']:.0f}x{layout['acc_cell_h']:.0f}mm cell (scale: {SIZE_BOOST_ACCESSORIES})")

    # Center again after scaling
    center_xy(acc)

    # Move to accessory slot position
    acc.location.x = layout['acc_x']
    acc.location.y = layout['acc_centers_y'][index]

    # Snap to card surface first
    snap_bottom_to_base_top(acc, card)

    # Sink mesh plane into the base plate (so only displaced parts show above card)
    card_thickness = CARD_THICKNESS / 1000.0
    card_width = CARD_WIDTH / 1000.0
    card_height = CARD_HEIGHT / 1000.0
    sink_mesh_plane_into_card(acc, card_thickness, MESH_PLANE_SINK_DEPTH)

    # Trim to card boundaries (cut anything outside XY bounds)
    trim_to_card_boundaries(acc, card_width, card_height, card_thickness)

    # Cut anything below card bottom
    cut_below_card(acc, card_thickness)

    # Apply shade auto smooth
    apply_shade_auto_smooth(acc, angle=30.0)

    print_obj_info(acc, f"Accessory {index + 1} positioned:")


# ============================================================
# TEXT FUNCTIONS
# ============================================================
def create_text_material(name, color_rgba, emission=True):
    """Create a solid color material for text"""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    nodes.clear()

    output_node = nodes.new('ShaderNodeOutputMaterial')
    output_node.location = (300, 0)

    if emission:
        # Use emission for flat, visible color
        emit_node = nodes.new('ShaderNodeEmission')
        emit_node.location = (0, 0)
        emit_node.inputs['Color'].default_value = color_rgba
        emit_node.inputs['Strength'].default_value = 1.0
        links.new(emit_node.outputs['Emission'], output_node.inputs['Surface'])
    else:
        # Use principled BSDF
        bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
        bsdf_node.location = (0, 0)
        bsdf_node.inputs['Base Color'].default_value = color_rgba
        links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

    return mat


def create_text_object(text, size, extrude, font_path=""):
    """Create a 3D text object lying flat on XY plane (facing +Z for top-down camera)"""
    # Create text curve
    curve = bpy.data.curves.new(name=f"Text_{text[:20]}", type='FONT')
    curve.body = text
    curve.size = size / 1000.0  # Convert mm to meters
    curve.extrude = extrude / 1000.0  # Convert mm to meters
    curve.align_x = 'CENTER'
    curve.align_y = 'CENTER'

    # Load custom font if provided
    if font_path and os.path.exists(font_path):
        try:
            curve.font = bpy.data.fonts.load(font_path)
        except Exception as e:
            print(f"  WARNING: Could not load font {font_path}: {e}")

    # Create object
    text_obj = bpy.data.objects.new(curve.name, curve)
    bpy.context.scene.collection.objects.link(text_obj)

    # Text lies flat on XY plane by default, facing +Z (readable from top-down camera)
    # No rotation needed - text is already in correct orientation
    text_obj.rotation_euler = (0, 0, 0)

    bpy.context.view_layer.update()
    return text_obj


def scale_text_to_fit(text_obj, max_width_mm, max_height_mm):
    """
    Scale text object uniformly to fit within max bounds.
    Returns the final dimensions in mm.
    """
    bpy.context.view_layer.update()

    # Get current dimensions
    dims = text_obj.dimensions
    current_w = dims.x * 1000  # Convert to mm
    current_h = dims.y * 1000  # Convert to mm

    if current_w <= 0 or current_h <= 0:
        return current_w, current_h

    # Calculate scale factors
    scale_w = max_width_mm / current_w if current_w > 0 else 1.0
    scale_h = max_height_mm / current_h if current_h > 0 else 1.0

    # Use the smaller scale to fit within both bounds
    scale = min(scale_w, scale_h, 1.0)  # Don't scale up, only down if needed

    if scale < 1.0:
        text_obj.scale *= scale
        bpy.context.view_layer.update()

    # Return final dimensions
    final_dims = text_obj.dimensions
    return final_dims.x * 1000, final_dims.y * 1000


def add_title_and_subtitle(card, title, subtitle, color_name='red', font_path=""):
    """
    Add title and subtitle text to the top of the card.
    Text lies flat on the card (facing up for Z camera).
    Dynamically scaled to fit within max bounds.
    """
    print(f"\n=== Adding Text: '{title}' / '{subtitle}' ===")

    # Get color
    color_rgba = TEXT_COLORS.get(color_name.lower(), TEXT_COLORS['red'])
    print(f"  Color: {color_name} -> {color_rgba}")

    # Create material
    text_mat = create_text_material("TextMaterial", color_rgba, emission=True)

    # Calculate position (upper area of card)
    card_h = CARD_HEIGHT / 1000.0  # meters
    upper_area_height = card_h * UPPER_RATIO
    upper_y_max = card_h / 2.0  # Top of card
    upper_y_min = upper_y_max - upper_area_height  # Bottom of upper area

    text_objects = []

    # Create title
    title_obj = None
    if title:
        title_obj = create_text_object(title, TEXT_SIZE_INITIAL, TEXT_EXTRUDE, font_path)
        title_obj.name = "Title"
        title_obj.data.materials.append(text_mat)

        # Scale to fit within max bounds
        final_w, final_h = scale_text_to_fit(title_obj, TITLE_MAX_WIDTH, TITLE_MAX_HEIGHT)
        print(f"  Title '{title}': {final_w:.1f}mm x {final_h:.1f}mm (max: {TITLE_MAX_WIDTH}x{TITLE_MAX_HEIGHT})")

        text_objects.append(title_obj)

    # Create subtitle
    sub_obj = None
    if subtitle:
        sub_obj = create_text_object(subtitle, TEXT_SIZE_INITIAL * 0.7, TEXT_EXTRUDE, font_path)
        sub_obj.name = "Subtitle"
        sub_obj.data.materials.append(text_mat)

        # Scale to fit within max bounds
        final_w, final_h = scale_text_to_fit(sub_obj, SUBTITLE_MAX_WIDTH, SUBTITLE_MAX_HEIGHT)
        print(f"  Subtitle '{subtitle}': {final_w:.1f}mm x {final_h:.1f}mm (max: {SUBTITLE_MAX_WIDTH}x{SUBTITLE_MAX_HEIGHT})")

        text_objects.append(sub_obj)

    # Position text objects
    bpy.context.view_layer.update()

    # Get heights for positioning
    title_height = title_obj.dimensions.y if title_obj else 0
    sub_height = sub_obj.dimensions.y if sub_obj else 0
    gap = 0.002  # 2mm gap between title and subtitle
    top_margin = TEXT_TOP_MARGIN / 1000.0  # Convert to meters

    # Position from top of card with margin
    card_top_y = CARD_HEIGHT / 2.0 / 1000.0  # Top edge of card in meters

    # Position title below top margin
    if title_obj:
        title_obj.location.x = 0
        title_obj.location.y = card_top_y - top_margin - title_height / 2.0
        title_obj.location.z = TEXT_LIFT / 1000.0
        print(f"  Title position: Y={title_obj.location.y*1000:.1f}mm (margin: {TEXT_TOP_MARGIN}mm from top)")

    # Position subtitle below title
    if sub_obj:
        if title_obj:
            sub_obj.location.y = title_obj.location.y - title_height / 2.0 - gap - sub_height / 2.0
        else:
            sub_obj.location.y = card_top_y - top_margin - sub_height / 2.0
        sub_obj.location.x = 0
        sub_obj.location.z = TEXT_LIFT / 1000.0
        print(f"  Subtitle position: Y={sub_obj.location.y*1000:.1f}mm")

    bpy.context.view_layer.update()
    return text_objects


# ============================================================
# EXPORT AND RENDER FUNCTIONS
# ============================================================
def export_stl(card, figure, accessories, stl_path, text_objects=None):
    """
    Export all objects as a single STL file.
    Joins card, figure, accessories, and text into one mesh for export.
    """
    print("\n=== Exporting STL ===")

    # Select all objects to export
    bpy.ops.object.select_all(action='DESELECT')

    objects_to_join = [card]
    if figure:
        objects_to_join.append(figure)
    objects_to_join.extend(accessories)

    # Make copies for joining (to preserve originals)
    copies = []
    for obj in objects_to_join:
        select_only(obj)
        bpy.ops.object.duplicate()
        copy = bpy.context.object
        copy.name = f"{obj.name}_copy"

        # Apply all modifiers on the copy
        for mod in copy.modifiers[:]:
            try:
                bpy.ops.object.modifier_apply(modifier=mod.name)
            except:
                pass

        # Add decimate modifier to reduce polygon count (preserves shape)
        if copy.type == 'MESH' and len(copy.data.polygons) > 1000:
            decimate = copy.modifiers.new(name="Decimate", type='DECIMATE')
            decimate.decimate_type = 'COLLAPSE'
            decimate.ratio = DECIMATE_RATIO
            select_only(copy)
            bpy.ops.object.modifier_apply(modifier="Decimate")
            print(f"  Decimated {obj.name}: {DECIMATE_RATIO*100:.0f}% polygons kept")

        copies.append(copy)

    # Convert text objects to mesh and add to copies
    if text_objects:
        for text_obj in text_objects:
            if text_obj and text_obj.name in bpy.data.objects:
                # Duplicate text object
                select_only(text_obj)
                bpy.ops.object.duplicate()
                text_copy = bpy.context.object
                text_copy.name = f"{text_obj.name}_copy"

                # Convert curve/font to mesh
                select_only(text_copy)
                bpy.ops.object.convert(target='MESH')

                copies.append(text_copy)
                print(f"  Converted text '{text_obj.name}' to mesh")

    # Select all copies and join them
    bpy.ops.object.select_all(action='DESELECT')
    for copy in copies:
        copy.select_set(True)
    bpy.context.view_layer.objects.active = copies[0]
    bpy.ops.object.join()

    joined = bpy.context.object
    joined.name = "ExportMesh"

    # Export STL
    select_only(joined)
    bpy.ops.wm.stl_export(
        filepath=stl_path,
        export_selected_objects=True,
        global_scale=1000.0,  # Convert meters to mm for STL
        ascii_format=False
    )

    print(f"  Exported STL: {stl_path}")

    # Delete the joined copy
    bpy.ops.object.delete()

    # Reselect original card
    select_only(card)


def render_texture_top_down(card, texture_path, dpi=300):
    """
    Render a top-down orthographic view of the card with textures.
    Output is exactly 130mm x 170mm at specified DPI for UV printing.
    """
    print("\n=== Rendering Texture (Top-Down) ===")

    # Calculate render resolution based on card size and DPI
    # 1 inch = 25.4mm
    card_width_inches = CARD_WIDTH / 25.4
    card_height_inches = CARD_HEIGHT / 25.4
    render_width = int(card_width_inches * dpi)
    render_height = int(card_height_inches * dpi)

    print(f"  Card size: {CARD_WIDTH}mm x {CARD_HEIGHT}mm")
    print(f"  Resolution: {render_width} x {render_height} pixels ({dpi} DPI)")

    # Create orthographic camera
    bpy.ops.object.camera_add(location=(0, 0, 0.5))  # 500mm above
    camera = bpy.context.object
    camera.name = "TopDownCamera"
    camera.data.type = 'ORTHO'

    # Set orthographic scale to match card height (in meters)
    camera.data.ortho_scale = CARD_HEIGHT / 1000.0

    # Point camera straight down
    camera.rotation_euler = (0, 0, 0)  # Looking down -Z

    # Set as active camera
    bpy.context.scene.camera = camera

    # Configure render settings
    scene = bpy.context.scene
    scene.render.resolution_x = render_width
    scene.render.resolution_y = render_height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = True  # Transparent background

    # Set up lighting for flat, even illumination
    # Remove existing lights
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT':
            bpy.data.objects.remove(obj)

    # Add a sun light from above
    bpy.ops.object.light_add(type='SUN', location=(0, 0, 1))
    sun = bpy.context.object
    sun.name = "TopLight"
    sun.data.energy = 3.0
    sun.rotation_euler = (0, 0, 0)  # Pointing down

    # Set render engine to Cycles with GPU
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = 128

    # Enable GPU compute
    prefs = bpy.context.preferences
    cycles_prefs = prefs.addons['cycles'].preferences
    cycles_prefs.compute_device_type = 'CUDA'
    cycles_prefs.get_devices()
    for device in cycles_prefs.devices:
        device.use = True

    # Render
    scene.render.filepath = texture_path
    bpy.ops.render.render(write_still=True)

    print(f"  Rendered texture: {texture_path}")

    # Clean up - delete camera and light
    bpy.data.objects.remove(camera)
    bpy.data.objects.remove(sun)


def create_uv_print_texture(texture_path, figure_img_path, figure_pos, figure_dims,
                            acc_images, acc_positions, acc_dims, text_objects, dpi=300,
                            background_type='transparent', background_color='white', background_image=None):
    """
    Create a UV print texture by compositing:
    - Background layer (solid color OR image OR transparent)
    - Original 2D images at the exact positions of 3D models
    - Rendered text

    Args:
        texture_path: Output path for the texture
        figure_img_path: Path to original figure 2D image
        figure_pos: (x, y) position of figure center in mm
        figure_dims: (width, height) of figure in mm
        acc_images: List of paths to accessory 2D images
        acc_positions: List of (x, y) positions for accessories in mm
        acc_dims: List of (width, height) for accessories in mm
        text_objects: List of text objects to render
        dpi: Output DPI (default 300)
        background_type: 'transparent', 'solid', or 'image'
        background_color: Color name for solid background (from BACKGROUND_COLORS)
        background_image: Path to background image (for 'image' type)
    """
    from PIL import Image

    print("\n=== Creating UV Print Texture ===")
    print(f"  Background type: {background_type}")

    # Calculate canvas size in pixels
    # 1 inch = 25.4mm
    canvas_width = int((CARD_WIDTH / 25.4) * dpi)
    canvas_height = int((CARD_HEIGHT / 25.4) * dpi)
    px_per_mm = dpi / 25.4

    print(f"  Canvas: {canvas_width} x {canvas_height} pixels ({dpi} DPI)")
    print(f"  Scale: {px_per_mm:.2f} pixels/mm")

    # Create canvas based on background type
    if background_type == 'solid' and background_color != 'transparent':
        bg_rgb = BACKGROUND_COLORS.get(background_color.lower(), BACKGROUND_COLORS['white'])
        if bg_rgb is None:
            # transparent option selected
            canvas = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
            print(f"  Background: transparent")
        else:
            # Solid color with full opacity
            canvas = Image.new('RGBA', (canvas_width, canvas_height), (*bg_rgb, 255))
            print(f"  Background: solid {background_color} -> RGB{bg_rgb}")
    elif background_type == 'image' and background_image and os.path.exists(background_image):
        # Load and resize background image to fill canvas
        try:
            bg_img = Image.open(background_image).convert('RGBA')
            # Resize to cover entire canvas (may crop if aspect ratio differs)
            bg_img = bg_img.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
            canvas = bg_img
            print(f"  Background: image from {background_image}")
        except Exception as e:
            print(f"  WARNING: Failed to load background image: {e}")
            print(f"  Falling back to transparent background")
            canvas = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
    else:
        # Transparent background (default)
        canvas = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
        print(f"  Background: transparent")

    def mm_to_px(x_mm, y_mm):
        """Convert mm coordinates (origin at center) to pixel coordinates (origin at top-left)"""
        # Card is centered at origin, so x_mm=0 is center
        # Pixel origin is top-left, Y increases downward
        px_x = int((x_mm + CARD_WIDTH / 2.0) * px_per_mm)
        px_y = int((CARD_HEIGHT / 2.0 - y_mm) * px_per_mm)  # Flip Y
        return px_x, px_y

    def place_image(img_path, center_x_mm, center_y_mm, width_mm, height_mm, label=""):
        """Place an image on the canvas at the specified position and size"""
        if not os.path.exists(img_path):
            print(f"  WARNING: Image not found: {img_path}")
            return

        # Load image
        img = Image.open(img_path).convert('RGBA')
        orig_w, orig_h = img.size

        # Calculate target size in pixels
        target_w_px = int(width_mm * px_per_mm)
        target_h_px = int(height_mm * px_per_mm)

        # Scale image to fit within target size while maintaining aspect ratio
        scale_w = target_w_px / orig_w
        scale_h = target_h_px / orig_h
        scale = min(scale_w, scale_h)

        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)

        img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Calculate paste position (top-left corner)
        center_px_x, center_px_y = mm_to_px(center_x_mm, center_y_mm)
        paste_x = center_px_x - new_w // 2
        paste_y = center_px_y - new_h // 2

        # Paste with alpha compositing
        canvas.paste(img_resized, (paste_x, paste_y), img_resized)

        print(f"  Placed {label}: {new_w}x{new_h}px at ({paste_x}, {paste_y})")

    # Place figure image
    if figure_img_path and figure_pos and figure_dims:
        place_image(figure_img_path, figure_pos[0], figure_pos[1],
                   figure_dims[0], figure_dims[1], "Figure")

    # Place accessory images
    for i, (img_path, pos, dims) in enumerate(zip(acc_images, acc_positions, acc_dims)):
        if img_path and pos and dims:
            place_image(img_path, pos[0], pos[1], dims[0], dims[1], f"Accessory_{i+1}")

    # Render text separately and composite
    if text_objects:
        text_render_path = texture_path.replace('.png', '_text_temp.png')
        render_text_only(text_objects, text_render_path, canvas_width, canvas_height)

        if os.path.exists(text_render_path):
            text_img = Image.open(text_render_path).convert('RGBA')
            canvas = Image.alpha_composite(canvas, text_img)
            os.remove(text_render_path)  # Clean up temp file
            print(f"  Composited text layer")

    # Save final texture with correct DPI metadata (300 DPI)
    # PIL uses pixels per inch for DPI
    canvas.save(texture_path, 'PNG', dpi=(dpi, dpi))
    print(f"  Saved UV print texture: {texture_path} ({dpi} DPI = {CARD_WIDTH}mm x {CARD_HEIGHT}mm)")

    return canvas_width, canvas_height


def render_text_only(text_objects, output_path, width, height):
    """Render only the text objects to a transparent PNG"""
    print(f"  Rendering text layer...")

    # Hide all objects except text
    all_objects = list(bpy.data.objects)
    prev_hide = {}
    for obj in all_objects:
        prev_hide[obj.name] = obj.hide_render
        obj.hide_render = True

    # Show only text objects
    for text_obj in text_objects:
        if text_obj and text_obj.name in bpy.data.objects:
            bpy.data.objects[text_obj.name].hide_render = False

    # Create camera for text render
    bpy.ops.object.camera_add(location=(0, 0, 0.5))
    camera = bpy.context.object
    camera.name = "TextCamera"
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = CARD_HEIGHT / 1000.0
    camera.rotation_euler = (0, 0, 0)

    # Configure render
    scene = bpy.context.scene
    scene.camera = camera
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = True

    # Use Cycles for text
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'GPU'
    scene.cycles.samples = 64

    # Add light
    bpy.ops.object.light_add(type='SUN', location=(0, 0, 1))
    sun = bpy.context.object
    sun.name = "TextLight"
    sun.data.energy = 3.0

    # Render
    scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)

    # Cleanup
    bpy.data.objects.remove(camera)
    bpy.data.objects.remove(sun)

    # Restore visibility
    for obj_name, hide_state in prev_hide.items():
        if obj_name in bpy.data.objects:
            bpy.data.objects[obj_name].hide_render = hide_state

    print(f"  Text layer rendered")


# ============================================================
# MAIN
# ============================================================
def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]

    p = argparse.ArgumentParser()
    p.add_argument("--figure_depth", required=True, help="Path to figure depth PNG")
    p.add_argument("--figure_img", required=True, help="Path to figure color PNG")
    p.add_argument("--acc1_depth", help="Path to accessory 1 depth PNG")
    p.add_argument("--acc1_img", help="Path to accessory 1 color PNG")
    p.add_argument("--acc2_depth", help="Path to accessory 2 depth PNG")
    p.add_argument("--acc2_img", help="Path to accessory 2 color PNG")
    p.add_argument("--acc3_depth", help="Path to accessory 3 depth PNG")
    p.add_argument("--acc3_img", help="Path to accessory 3 color PNG")
    p.add_argument("--output_dir", required=True, help="Output directory")
    p.add_argument("--job_id", default="test", help="Job ID for filenames")

    # Text arguments
    p.add_argument("--title", type=str, default="", help="Main title text at top of card")
    p.add_argument("--subtitle", type=str, default="", help="Subtitle text below title")
    p.add_argument("--text_color", type=str, default="red",
                   choices=['red', 'blue', 'green', 'white', 'black', 'yellow', 'orange', 'purple', 'pink', 'gold'],
                   help="Color of the text")
    p.add_argument("--font", type=str, default="", help="Optional path to TTF/OTF font file")

    # Background arguments
    p.add_argument("--background_type", type=str, default="transparent",
                   choices=['transparent', 'solid', 'image'],
                   help="Type of background: transparent, solid color, or image")
    p.add_argument("--background_color", type=str, default="white",
                   choices=['white', 'black', 'red', 'blue', 'green', 'yellow', 'orange', 'purple',
                           'pink', 'gray', 'navy', 'teal', 'maroon', 'olive', 'silver', 'transparent'],
                   help="Color for solid background")
    p.add_argument("--background_image", type=str, default="",
                   help="Path to background image (for 'image' background type)")

    return p.parse_args(argv)


def main():
    args = parse_args()

    print("=" * 60)
    print("STARTER PACK - DISPLACEMENT METHOD")
    print("=" * 60)

    clear_scene()
    os.makedirs(args.output_dir, exist_ok=True)

    # Calculate layout for positioning
    layout = calculate_layout()
    print("\n=== Layout Calculated ===")
    print(f"  Figure slot: {layout['fig_slot_w']:.0f}x{layout['fig_slot_h']:.0f}mm at ({layout['fig_x']*1000:.0f}, {layout['fig_y']*1000:.0f})mm")
    print(f"  Accessory cells: {layout['acc_slot_w']:.0f}x{layout['acc_cell_h']:.0f}mm at x={layout['acc_x']*1000:.0f}mm")

    # Step 1: Create base plate
    card = create_base_plate()

    # Step 1b: Add title and subtitle text (if provided)
    text_objects = []
    if args.title or args.subtitle:
        text_objects = add_title_and_subtitle(
            card,
            title=args.title,
            subtitle=args.subtitle,
            color_name=args.text_color,
            font_path=args.font
        )

    # Step 2: Create and position figure
    figure_top_z = None
    figure = create_displaced_mesh(args.figure_depth, args.figure_img, name="Figure")
    figure_pos = None
    figure_dims = None
    if figure:
        figure_top_z, figure_pos, figure_dims = position_figure(figure, card, layout)
        print(f"  Figure top Z: {figure_top_z*1000:.1f}mm")
        # Use PRE-TRIM position and dimensions for texture alignment
        # This ensures the 2D texture matches the full figure, not the trimmed 3D model
        print(f"  Using pre-trim dims for texture: ({figure_pos[0]:.1f}, {figure_pos[1]:.1f})mm, {figure_dims[0]:.1f}x{figure_dims[1]:.1f}mm")

    # Step 3: Create and position accessories (with higher displacement strength)
    accessories = []
    acc_positions = []
    acc_dims_list = []
    acc_img_paths = []
    for i, (depth, img) in enumerate([
        (args.acc1_depth, args.acc1_img),
        (args.acc2_depth, args.acc2_img),
        (args.acc3_depth, args.acc3_img)
    ]):
        if depth and img and os.path.exists(depth) and os.path.exists(img):
            acc = create_displaced_mesh(depth, img, name=f"Accessory_{i+1}",
                                        displacement_strength=DISPLACEMENT_STRENGTH_ACCESSORIES)
            if acc:
                position_accessory(acc, card, layout, i, figure_top_z)
                accessories.append(acc)
                # Store BOUNDING BOX center and dimensions for UV print texture
                acc_min, acc_max = world_aabb(acc)
                acc_center_x = (acc_min.x + acc_max.x) / 2.0
                acc_center_y = (acc_min.y + acc_max.y) / 2.0
                acc_positions.append((acc_center_x * 1000, acc_center_y * 1000))
                acc_dims_list.append((acc.dimensions.x * 1000, acc.dimensions.y * 1000))
                acc_img_paths.append(img)

    # Save blend file
    blend_path = os.path.join(args.output_dir, f"{args.job_id}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"\nSaved: {blend_path}")

    # Export STL (includes text)
    stl_path = os.path.join(args.output_dir, f"{args.job_id}.stl")
    export_stl(card, figure, accessories, stl_path, text_objects=text_objects)

    # Create UV print texture (with background options)
    texture_path = os.path.join(args.output_dir, f"{args.job_id}_texture.png")
    create_uv_print_texture(
        texture_path=texture_path,
        figure_img_path=args.figure_img,
        figure_pos=figure_pos,
        figure_dims=figure_dims,
        acc_images=acc_img_paths,
        acc_positions=acc_positions,
        acc_dims=acc_dims_list,
        text_objects=text_objects,
        dpi=300,
        background_type=args.background_type,
        background_color=args.background_color,
        background_image=args.background_image if args.background_image else None
    )

    print("\n" + "=" * 60)
    print(f"DONE - Created and positioned figure + {len(accessories)} accessories")
    print(f"  Blend: {blend_path}")
    print(f"  STL: {stl_path}")
    print(f"  Texture: {texture_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
