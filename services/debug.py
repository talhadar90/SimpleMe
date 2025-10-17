import bpy
import bmesh
import os
from mathutils import Vector
from datetime import datetime
import math

# ========== JOB CONFIGURATION ==========
JOB_ID = "{job_id}"
OUTPUT_DIR = r"{output_abs}"
STYLE = "{style}"

# Create log file for this job
LOG_FILE = os.path.join(OUTPUT_DIR, f"blender_log_{{JOB_ID}}.txt")

# ========== MANUAL OVERRIDE CONTROLS ========== 
# Change these values to test different settings:

# FIGURE CONTROLS
FIGURE_ROTATION_X = 90    # Degrees around X axis (0, 45, 90, 180, 270)
FIGURE_ROTATION_Y = 0     # Degrees around Y axis
FIGURE_ROTATION_Z = 0     # Degrees around Z axis
FIGURE_SCALE = 1.0        # Scale multiplier (0.5 = half size, 2.0 = double size)
FIGURE_Z_POSITION = 5     # Z position above base (in mm)

# ACCESSORY CONTROLS  
ACCESSORY_ROTATION_X = 90 # Degrees around X axis
ACCESSORY_ROTATION_Y = 0  # Degrees around Y axis
ACCESSORY_ROTATION_Z = 0  # Degrees around Z axis
ACCESSORY_SCALE = 1.0     # Scale multiplier
ACCESSORY_Z_POSITION = 5  # Z position above base (in mm)

# ========== COLOR PALETTE FOR {style.upper()} STYLE ==========
COLOR_PALETTE = {{
    "base": {color_palette['base']},
    "title": {color_palette['title']},
    "figure": {color_palette['figure']},
    "accessories": {color_palette['accessories']},
    "material_properties": {color_palette['material_properties']}
}}

def log(message, level="INFO"):
    """Enhanced logging function"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_line = f"[{{timestamp}}] [{{level}}] {{message}}"
    print(log_line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\\n")
    except Exception as e:
        print(f"Failed to write to log file: {{e}}")

# ========== TEST CONFIGURATION ==========
TEST_FILES = {
    "figure": "/Users/talha/Downloads/3d_models/3d_models/latest/figure.glb",
    "acc1": "/Users/talha/Downloads/3d_models/3d_models/latest/acc1.glb",
    "acc2": "/Users/talha/Downloads/3d_models/3d_models/latest/acc2.glb",
    "acc3": "/Users/talha/Downloads/3d_models/3d_models/latest/acc3.glb",
}

# ========== EXACT LAYOUT SETTINGS ==========
BASE_WIDTH = 130
BASE_HEIGHT = 180
BASE_THICKNESS = 3

# Text area
TEXT_HEIGHT = 20

# Usable area
USABLE_HEIGHT = 160
USABLE_Y_START = (BASE_HEIGHT/2) - TEXT_HEIGHT - (USABLE_HEIGHT/2)

# Figure area: 70×140
FIGURE_WIDTH = 70
FIGURE_HEIGHT = 140
FIGURE_X = -BASE_WIDTH/2 + FIGURE_WIDTH/2  # Left side
FIGURE_Y = USABLE_Y_START

# Gap between figure and accessories
GAP = 10

# Accessories: 50×50 each
ACCESSORY_SIZE = 50
ACCESSORY_X = FIGURE_X + FIGURE_WIDTH/2 + GAP + ACCESSORY_SIZE/2
ACCESSORY_SPACING = 53.33  # (160-50*3)/2 = spacing between accessories

def clear_scene():
    """Clear all objects from scene"""
    log("Clearing scene...")
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False, confirm=False)

def setup_scene():
    """Setup scene for mm units"""
    log("Setting up scene units...")
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 0.001

def create_material(name: str, color: tuple, metallic: float = 0.0, roughness: float = 0.5):
    """Create a material with specified properties"""
    log(f"Creating material: {{name}} with color {{color}}")
    
    # Create new material
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    
    # Clear default nodes
    mat.node_tree.nodes.clear()
    
    # Add Principled BSDF node
    bsdf = mat.node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.location = (0, 0)
    
    # Add Material Output node
    output = mat.node_tree.nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (300, 0)
    
    # Connect nodes
    mat.node_tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    
    # Set material properties
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    
    log(f"✓ Material {{name}} created: Color={{color}}, Metallic={{metallic}}, Roughness={{roughness}}")
    return mat

def apply_material_to_object(obj, material):
    """Apply material to an object"""
    log(f"Applying material {{material.name}} to {{obj.name}}")
    
    # Clear existing materials
    obj.data.materials.clear()
    
    # Add new material
    obj.data.materials.append(material)
    
    log(f"✓ Material applied to {{obj.name}}")

def create_base():
    """Create the base platform with themed color"""
    log("Creating base...")
    bpy.ops.mesh.primitive_cube_add()
    base = bpy.context.active_object
    base.name = "Base"
    base.scale = (BASE_WIDTH/2, BASE_HEIGHT/2, BASE_THICKNESS/2)
    base.location = (0, 0, BASE_THICKNESS/2)
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    
    # Apply themed color
    base_material = create_material("BaseMaterial", COLOR_PALETTE["base"], 0.1, 0.8)
    apply_material_to_object(base, base_material)
    
    log(f"Base created with {{STYLE}} style color: {{base.dimensions}}")
    return base

def create_professional_title():
    """Create professional extruded and beveled STARTER PACK title with themed color"""
    log("Creating professional STARTER PACK title...")
    
    # Add text
    bpy.ops.object.text_add()
    text_obj = bpy.context.active_object
    text_obj.name = "StarterPackTitle"
    text_obj.data.body = "STARTER PACK"
    
    # Set font properties for H1-like appearance
    text_obj.data.size = 15  # Large size
    text_obj.data.space_character = 1.2  # Character spacing
    text_obj.data.space_word = 1.5  # Word spacing
    
    # Position at top center of base
    text_y = (BASE_HEIGHT/2) - (TEXT_HEIGHT/2)
    text_obj.location = (0, text_y, BASE_THICKNESS)
    
    # Make sure object is selected and active
    bpy.context.view_layer.objects.active = text_obj
    bpy.ops.object.select_all(action='DESELECT')
    text_obj.select_set(True)
    
    # Set text properties for 3D extrusion
    log("Adding extrusion and bevel...")
    text_obj.data.extrude = 2.0  # Extrude 2mm
    text_obj.data.bevel_depth = 0.3  # Bevel depth
    text_obj.data.bevel_resolution = 3  # Smooth bevel
    
    # Center the text origin
    bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS')
    
    # Final positioning after centering
    text_obj.location = (0, text_y, BASE_THICKNESS + 1)
    
    # Apply themed color
    title_material = create_material("TitleMaterial", COLOR_PALETTE["title"], 0.2, 0.3)
    apply_material_to_object(text_obj, title_material)
    
    log(f"Title positioned at: {{text_obj.location}}")
    log(f"Title properties: extrude={{text_obj.data.extrude}}, bevel={{text_obj.data.bevel_depth}}")
    log(f"Title colored with {{STYLE}} style")
    
    return text_obj

def find_best_mesh_object(new_objects):
    """Find the best mesh object from imported objects"""
    mesh_objects = [obj for obj in new_objects if obj.type == 'MESH']
    
    if not mesh_objects:
        log("No mesh objects found!", "ERROR")
        return None
    
    # Find the mesh with the most vertices (usually the main object)
    best_obj = None
    max_vertices = 0
    
    for obj in mesh_objects:
        if obj.data and len(obj.data.vertices) > max_vertices:
            max_vertices = len(obj.data.vertices)
            best_obj = obj
    
    if best_obj:
        log(f"Best mesh object: {{best_obj.name}} ({{max_vertices}} vertices)")
        log(f"Dimensions: {{best_obj.dimensions}}")
    
    return best_obj

def inspect_materials(obj):
    """Check what materials/colors an object has - DETAILED INSPECTION"""
    log(f"\\n🔍 DETAILED MATERIAL INSPECTION FOR: {{obj.name}}")
    log("=" * 60)
    
    # Check if object has material slots
    if obj.material_slots:
        log(f"📦 Material slots found: {{len(obj.material_slots)}}")
        
        for i, slot in enumerate(obj.material_slots):
            log(f"\\n--- MATERIAL SLOT {{i}} ---")
            if slot.material:
                mat = slot.material
                log(f"  ✓ Material name: '{{mat.name}}'")
                log(f"  ✓ Material type: {{mat.type if hasattr(mat, 'type') else 'Unknown'}}")
                
                # Check for basic material properties
                if hasattr(mat, 'diffuse_color'):
                    color = mat.diffuse_color
                    log(f"  🎨 Diffuse color: R={{color[0]:.3f}}, G={{color[1]:.3f}}, B={{color[2]:.3f}}, A={{color[3]:.3f}}")
                
                # Check for node-based materials (Shader Editor)
                if mat.use_nodes and mat.node_tree:
                    log(f"  🔗 Uses nodes: YES ({{len(mat.node_tree.nodes)}} nodes)")
                    
                    # List all nodes
                    for node in mat.node_tree.nodes:
                        log(f"    - Node: {{node.type}} ({{node.name}})")
                        
                        # Special handling for common node types
                        if node.type == 'BSDF_PRINCIPLED':
                            if hasattr(node.inputs['Base Color'], 'default_value'):
                                base_color = node.inputs['Base Color'].default_value
                                log(f"      Base Color: R={{base_color[0]:.3f}}, G={{base_color[1]:.3f}}, B={{base_color[2]:.3f}}")
                            if hasattr(node.inputs['Metallic'], 'default_value'):
                                metallic = node.inputs['Metallic'].default_value
                                log(f"      Metallic: {{metallic:.3f}}")
                            if hasattr(node.inputs['Roughness'], 'default_value'):
                                roughness = node.inputs['Roughness'].default_value
                                log(f"      Roughness: {{roughness:.3f}}")
                        
                        elif node.type == 'TEX_IMAGE':
                            if node.image:
                                log(f"      Image texture: {{node.image.name}} ({{node.image.size[0]}}x{{node.image.size[1]}})")
                            else:
                                log(f"      Image texture: No image loaded")
                else:
                    log(f"  🔗 Uses nodes: NO (legacy material)")
                    
            else:
                log(f"  ✗ Material slot {{i}}: EMPTY")
    else:
        log("📦 No material slots found")
    
    # Check for vertex colors
    if hasattr(obj.data, 'vertex_colors') and obj.data.vertex_colors:
        log(f"\\n🎨 VERTEX COLORS:")
        for i, vcol in enumerate(obj.data.vertex_colors):
            log(f"  - Vertex color set {{i}}: '{{vcol.name}}' (active: {{vcol.active}})")
    else:
        log(f"\\n🎨 VERTEX COLORS: None found")
    
    # Check for UV maps
    if hasattr(obj.data, 'uv_layers') and obj.data.uv_layers:
        log(f"\\n🗺️  UV MAPS:")
        for i, uv in enumerate(obj.data.uv_layers):
            log(f"  - UV map {{i}}: '{{uv.name}}' (active: {{uv.active}})")
    else:
        log(f"\\n🗺️  UV MAPS: None found")
    
    log("=" * 60)
    log(f"🔍 MATERIAL INSPECTION COMPLETE FOR: {{obj.name}}\\n")

def analyze_object_orientation(obj):
    """Analyze object orientation to determine if rotation is needed - ENHANCED VERSION"""
    dims = obj.dimensions
    log(f"🔍 Analyzing orientation for {{obj.name}}")
    log(f"   Dimensions: X={{dims.x:.1f}}, Y={{dims.y:.1f}}, Z={{dims.z:.1f}}")
    
    # Find the tallest dimension
    max_dim = max(dims.x, dims.y, dims.z)
    min_dim = min(dims.x, dims.y, dims.z)
    
    log(f"   📐 Tallest: {{max_dim:.1f}}, Shortest: {{min_dim:.1f}}")
    
    # If Z is the tallest dimension, object is standing upright
    if dims.z == max_dim and dims.z > max(dims.x, dims.y) * 1.2:
        log(f"   📐 Object is standing upright (Z={{dims.z:.1f}} is tallest)")
        return True, "lay_down_x"  # Rotate around X axis to lay down
    
    # If Y is tallest, might need different rotation
    elif dims.y == max_dim and dims.y > max(dims.x, dims.z) * 1.2:
        log(f"   📐 Object is oriented vertically in Y (Y={{dims.y:.1f}} is tallest)")
        return True, "lay_down_y"  # Rotate around Z axis
    
    # If X is tallest but object is long/thin
    elif dims.x == max_dim and dims.x > max(dims.y, dims.z) * 2.0:
        log(f"   📐 Object is long horizontally (X={{dims.x:.1f}} is much longer)")
        return False, "none"  # Already laying flat lengthwise
    
    else:
        log(f"   📐 Object appears to be lying flat already")
        return False, "none"

def apply_manual_rotation(obj, rot_x, rot_y, rot_z, object_type="object"):
    """Apply manual rotation values"""
    obj.rotation_euler[0] = math.radians(rot_x)
    obj.rotation_euler[1] = math.radians(rot_y)
    obj.rotation_euler[2] = math.radians(rot_z)
    
    log(f"   🔄 MANUAL rotation applied to {{object_type}}: X={{rot_x}}°, Y={{rot_y}}°, Z={{rot_z}}°")
    
    # Update the scene
    bpy.context.view_layer.update()
    
    # Apply the rotation transform to make it permanent
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    bpy.context.view_layer.update()
    
    # Check result
    new_dims = obj.dimensions
    log(f"   📏 After manual rotation - dimensions: X={{new_dims.x:.1f}}, Y={{new_dims.y:.1f}}, Z={{new_dims.z:.1f}}")

def import_model(filepath, name):
    """Import a model and return the actual mesh object"""
    log(f"Importing: {{filepath}}")
    
    if not filepath or filepath == "None" or not os.path.exists(filepath):
        log(f"File not found: {{filepath}}", "ERROR")
        # Create placeholder cube
        bpy.ops.mesh.primitive_cube_add()
        placeholder = bpy.context.active_object
        placeholder.name = f"{{name}}_PLACEHOLDER"
        placeholder.scale = (5, 5, 5)  # Small placeholder
        log(f"Created placeholder: {{placeholder.name}}")
        return placeholder
    
    # Track objects before import
    objects_before = set(bpy.context.scene.objects)
    
    try:
        # Import based on file extension
        if filepath.lower().endswith(('.glb', '.gltf')):
            bpy.ops.import_scene.gltf(filepath=filepath)
        elif filepath.lower().endswith('.obj'):
            bpy.ops.wm.obj_import(filepath=filepath)
        elif filepath.lower().endswith('.stl'):
            bpy.ops.wm.stl_import(filepath=filepath)
        else:
            log(f"Unsupported file format: {{filepath}}", "WARNING")
            # Try GLTF as fallback
            bpy.ops.import_scene.gltf(filepath=filepath)
        
        # Find new objects
        objects_after = set(bpy.context.scene.objects)
        new_objects = objects_after - objects_before
        
        log(f"Imported {{len(new_objects)}} objects")
        
        # Find the best mesh object
        mesh_obj = find_best_mesh_object(new_objects)
        
        if mesh_obj:
            # Rename and return the mesh object
            original_name = mesh_obj.name
            mesh_obj.name = name
            log(f"✓ Using mesh object: {{original_name}} -> {{name}}")
            
            # INSPECT MATERIALS IMMEDIATELY AFTER IMPORT
            inspect_materials(mesh_obj)
            
            return mesh_obj
        else:
            log("✗ No suitable mesh object found", "ERROR")
            # Create placeholder
            bpy.ops.mesh.primitive_cube_add()
            placeholder = bpy.context.active_object
            placeholder.name = f"{{name}}_PLACEHOLDER"
            placeholder.scale = (5, 5, 5)
            return placeholder
            
    except Exception as e:
        log(f"✗ Import failed: {{e}}", "ERROR")
        # Create placeholder
        bpy.ops.mesh.primitive_cube_add()
        placeholder = bpy.context.active_object
        placeholder.name = f"{{name}}_PLACEHOLDER"
        placeholder.scale = (5, 5, 5)
        return placeholder

def calculate_scale_for_area(obj, target_width, target_height):
    """Calculate scale to fit object in target area"""
    dims = obj.dimensions
    log(f"Object dimensions: {{dims.x:.1f}} × {{dims.y:.1f}} × {{dims.z:.1f}}")
    log(f"Target area: {{target_width}} × {{target_height}}")
    
    # Calculate scale needed for width and height
    scale_x = target_width / dims.x if dims.x > 0 else 1.0
    scale_y = target_height / dims.y if dims.y > 0 else 1.0
    
    # Use the smaller scale to ensure it fits in both dimensions
    scale = min(scale_x, scale_y)
    
    log(f"Scale for width: {{scale_x:.6f}}")
    log(f"Scale for height: {{scale_y:.6f}}")
    log(f"Using scale: {{scale:.6f}}")
    
    return scale

def position_and_scale_figure(obj, target_x, target_y, target_width, target_height):
    """Scale, rotate, and position the figure with MANUAL CONTROLS"""
    log(f"\\n=== PROCESSING FIGURE {{obj.name}} ===")
    log(f"🎛️  USING MANUAL CONTROLS:")
    log(f"   Rotation: X={{FIGURE_ROTATION_X}}°, Y={{FIGURE_ROTATION_Y}}°, Z={{FIGURE_ROTATION_Z}}°")
    log(f"   Scale: {{FIGURE_SCALE}}x")
    log(f"   Z Position: {{FIGURE_Z_POSITION}}mm above base")
    
    # Make sure we're working with the object
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    
    # Apply any existing transforms first
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    
    # Get current dimensions
    dims = obj.dimensions
    log(f"Initial dimensions: {{dims.x:.1f}} × {{dims.y:.1f}} × {{dims.z:.1f}}")
    
    # MANUAL ROTATION: Use the manual controls
    apply_manual_rotation(obj, FIGURE_ROTATION_X, FIGURE_ROTATION_Y, FIGURE_ROTATION_Z, "figure")
    
    # Calculate and apply scale with manual multiplier
    current_dims = obj.dimensions
    base_scale = calculate_scale_for_area(obj, target_width, target_height)
    final_scale = base_scale * FIGURE_SCALE
    obj.scale = (final_scale, final_scale, final_scale)
    
    # Update scene to get final dimensions
    bpy.context.view_layer.update()
    final_dims = obj.dimensions
    log(f"Final scaled dimensions: {{final_dims.x:.1f}} × {{final_dims.y:.1f}} × {{final_dims.z:.1f}}")
    
    # MANUAL POSITIONING: Use manual Z position
    z_pos = BASE_THICKNESS + FIGURE_Z_POSITION
    obj.location = (target_x, target_y, z_pos)
    log(f"Final position: ({{target_x}}, {{target_y}}, {{z_pos:.1f}})")
    
    # APPLY FIGURE COLOR
    figure_props = COLOR_PALETTE["material_properties"]["figure"]
    figure_material = create_material(
        "FigureMaterial", 
        COLOR_PALETTE["figure"], 
        figure_props["metallic"], 
        figure_props["roughness"]
    )
    apply_material_to_object(obj, figure_material)
    log(f"🎨 Applied {{STYLE}} figure color to {{obj.name}}")
    
    log(f"=== FIGURE {{obj.name}} COMPLETE ===\\n")

def position_and_scale_accessory(obj, target_x, target_y, target_size, accessory_index):
    """Scale and position an accessory with MANUAL CONTROLS"""
    log(f"\\n=== PROCESSING ACCESSORY {{obj.name}} ===")
    log(f"🎛️  USING MANUAL CONTROLS:")
    log(f"   Rotation: X={{ACCESSORY_ROTATION_X}}°, Y={{ACCESSORY_ROTATION_Y}}°, Z={{ACCESSORY_ROTATION_Z}}°")
    log(f"   Scale: {{ACCESSORY_SCALE}}x")
    log(f"   Z Position: {{ACCESSORY_Z_POSITION}}mm above base")
    
    # Make sure we're working with the object
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    
    # Apply any existing transforms first
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    
    # Get current dimensions
    dims = obj.dimensions
    log(f"Initial dimensions: {{dims.x:.1f}} × {{dims.y:.1f}} × {{dims.z:.1f}}")
    
    # MANUAL ROTATION: Use the manual controls
    apply_manual_rotation(obj, ACCESSORY_ROTATION_X, ACCESSORY_ROTATION_Y, ACCESSORY_ROTATION_Z, "accessory")
    
    # Calculate and apply scale with manual multiplier
    current_dims = obj.dimensions
    base_scale = calculate_scale_for_area(obj, target_size, target_size)
    final_scale = base_scale * ACCESSORY_SCALE
    obj.scale = (final_scale, final_scale, final_scale)
    
    # Update scene to get final dimensions
    bpy.context.view_layer.update()
    final_dims = obj.dimensions
    log(f"Final scaled dimensions: {{final_dims.x:.1f}} × {{final_dims.y:.1f}} × {{final_dims.z:.1f}}")
    
    # MANUAL POSITIONING: Use manual Z position
    z_pos = BASE_THICKNESS + ACCESSORY_Z_POSITION
    obj.location = (target_x, target_y, z_pos)
    log(f"Final position: ({{target_x}}, {{target_y}}, {{z_pos:.1f}})")
    
    # APPLY ACCESSORY COLOR (cycle through available colors)
    accessory_colors = COLOR_PALETTE["accessories"]
    color_index = accessory_index % len(accessory_colors)
    accessory_color = accessory_colors[color_index]
    
    accessory_props = COLOR_PALETTE["material_properties"]["accessories"]
    accessory_material = create_material(
        f"AccessoryMaterial_{{accessory_index}}", 
        accessory_color, 
        accessory_props["metallic"], 
        accessory_props["roughness"]
    )
    apply_material_to_object(obj, accessory_material)
    log(f"🎨 Applied {{STYLE}} accessory color #{{color_index + 1}} to {{obj.name}}")
    
    log(f"=== ACCESSORY {{obj.name}} COMPLETE ===\\n")

def export_files():
    """Export the final files in 3MF and Blend formats"""
    log("\\n=== EXPORTING FILES ===")
    
    # Export 3MF (replaces STL - supports colors!)
    mf3_filename = f"starter_pack_{{JOB_ID}}.3mf"
    mf3_path = os.path.join(OUTPUT_DIR, mf3_filename)
    try:
        bpy.ops.object.select_all(action='SELECT')
        
        # Check if 3MF export is available
        if hasattr(bpy.ops.export_mesh, 'threemf'):
            bpy.ops.export_mesh.threemf(
                filepath=mf3_path,
                check_existing=False,
                export_materials=True,  # Include materials/colors
                export_colors=True,
                use_mesh_modifiers=True
            )
            log(f"✓ 3MF exported to: {{mf3_path}}")
        else:
            # Fallback to STL if 3MF not available
            log("⚠️  3MF not available, using STL fallback...")
            stl_filename = f"starter_pack_{{JOB_ID}}.stl"
            stl_path = os.path.join(OUTPUT_DIR, stl_filename)
            bpy.ops.wm.stl_export(filepath=stl_path, export_selected_objects=True)
            log(f"✓ STL fallback exported to: {{stl_path}}")
            mf3_path = stl_path  # Update path for verification
        
        # Verify file was created
        if os.path.exists(mf3_path):
            file_size = os.path.getsize(mf3_path)
            file_size_mb = round(file_size / (1024 * 1024), 2)
            log(f"✓ File size: {{file_size}} bytes ({{file_size_mb}} MB)")
        else:
            log("✗ Export file was not created", "ERROR")
            
    except Exception as e:
        log(f"✗ 3MF export failed: {{e}}", "ERROR")
        
        # STL fallback
        try:
            log("Attempting STL fallback...")
            stl_filename = f"starter_pack_{{JOB_ID}}.stl"
            stl_path = os.path.join(OUTPUT_DIR, stl_filename)
            bpy.ops.wm.stl_export(filepath=stl_path, export_selected_objects=True)
            log(f"✓ STL fallback exported to: {{stl_path}}")
        except Exception as stl_error:
            log(f"✗ STL fallback also failed: {{stl_error}}", "ERROR")

    # Save Blender file (preserves colors for viewing)
    blend_filename = f"starter_pack_{{JOB_ID}}.blend"
    blend_path = os.path.join(OUTPUT_DIR, blend_filename)
    try:
        bpy.ops.wm.save_as_mainfile(filepath=blend_path)
        log(f"✓ Blend file saved to: {{blend_path}}")
        
        # Verify file was created
        if os.path.exists(blend_path):
            file_size = os.path.getsize(blend_path)
            file_size_mb = round(file_size / (1024 * 1024), 2)
            log(f"✓ Blend file size: {{file_size}} bytes ({{file_size_mb}} MB)")
        else:
            log("✗ Blend file was not created", "ERROR")
    except Exception as e:
        log(f"✗ Blend file save failed: {{e}}", "ERROR")

def main():
    """Main function"""
    log("=== STARTER PACK LAYOUT GENERATION ===")
    log(f"Job ID: {{JOB_ID}}")
    log(f"Style: {{STYLE}}")
    log(f"Output Directory: {{OUTPUT_DIR}}")
    log(f"Log file: {{LOG_FILE}}")
    log(f"Layout: Base {{BASE_WIDTH}}×{{BASE_HEIGHT}}×{{BASE_THICKNESS}}mm")
    log(f"Figure area: {{FIGURE_WIDTH}}×{{FIGURE_HEIGHT}}mm at ({{FIGURE_X}}, {{FIGURE_Y}})")
    log(f"Accessory area: {{ACCESSORY_SIZE}}×{{ACCESSORY_SIZE}}mm at x={{ACCESSORY_X}}")
    log(f"🎨 Color Palette: {{STYLE}} theme loaded")
    log(f"🎛️  MANUAL CONTROLS ACTIVE:")
    log(f"   Figure: Rot({{FIGURE_ROTATION_X}},{{FIGURE_ROTATION_Y}},{{FIGURE_ROTATION_Z}}) Scale={{FIGURE_SCALE}} Z={{FIGURE_Z_POSITION}}")
    log(f"   Accessories: Rot({{ACCESSORY_ROTATION_X}},{{ACCESSORY_ROTATION_Y}},{{ACCESSORY_ROTATION_Z}}) Scale={{ACCESSORY_SCALE}} Z={{ACCESSORY_Z_POSITION}}")
    
    setup_scene()
    clear_scene()
    
    # Create base and professional title with themed colors
    create_base()
    create_professional_title()
    
    # Import and position figure
    log("\\n" + "="*50)
    log("PROCESSING FIGURE")
    log("="*50)
    figure = import_model(TEST_FILES["figure"], "Figure")
    if figure:
        position_and_scale_figure(
            figure, 
            FIGURE_X, FIGURE_Y,
            FIGURE_WIDTH, FIGURE_HEIGHT
        )
    
    # Import and position accessories
    log("\\n" + "="*50)
    log("PROCESSING ACCESSORIES")
    log("="*50)
    for i, acc_key in enumerate(["acc1", "acc2", "acc3"]):
        log(f"\\n--- ACCESSORY {{i+1}} ---")
        acc = import_model(TEST_FILES[acc_key], f"Accessory_{{i+1}}")
        if acc:
            # Calculate Y position for this accessory
            acc_y = USABLE_Y_START + (USABLE_HEIGHT/2) - (ACCESSORY_SIZE/2) - (i * ACCESSORY_SPACING)
            position_and_scale_accessory(
                acc,
                ACCESSORY_X, acc_y,
                ACCESSORY_SIZE,
                i  # Pass accessory index for color selection
            )
    
    # Export the final files
    export_files()
    
    log("\\n" + "="*50)
    log("STARTER PACK LAYOUT COMPLETE!")
    log("="*50)
    log(f"✓ {{STYLE}} style theme applied")
    log("✓ Professional H1-style title")
    log("✓ MANUAL rotation and scaling applied")
    log("✓ All models positioned with manual controls")
    log("✓ Themed colors applied to all objects")
    log("✓ Files exported successfully")
    log(f"Full log saved to: {{LOG_FILE}}")

if __name__ == "__main__":
    main()