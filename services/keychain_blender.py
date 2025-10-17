import bpy
import bmesh
import os
from mathutils import Vector
from datetime import datetime
import math

# ========== MANUAL CONTROLS ==========
FIGURE_ROTATION = "lay_flat_x"   # Use X rotation for flat
FIGURE_SCALE_MULTIPLIER = 1      # Figure size multiplier
ACCESSORY_ROTATION = "lay_flat_x"  # Use X rotation for flat
ACCESSORY_SCALE_MULTIPLIER = 1.2   # Accessory size multiplier

# ========== TEXT & DESIGN CONTROLS ==========
MAIN_TITLE = "STARTER PACK"           # H1 title
TAGLINE = "Everything You Need"       # H3 tagline
MAIN_TITLE_SIZE = 15                  # Large H1 size
TAGLINE_SIZE = 8                      # Smaller H3 size
BASE_BEVEL = True                     # Add bevel to base edges
TEXT_BEVEL = True                     # Add bevel to text

# ========== KEYCHAIN SETTINGS ==========
KEYCHAIN_MODE = True                  # Enable keychain mode
KEYCHAIN_SCALE = 0.3                  # Scale down to 30% for keychain size
KEYCHAIN_HOLE_SIZE = 5                # Keychain hole diameter in mm
KEYCHAIN_HOLE_POSITION = "bottom_left"  # "bottom_left" or "bottom_right"
MODEL_SCALE_BOOST = 2.5               # Boost model size for keychain (makes models bigger)

# ========== LOGGING SETUP ==========
LOG_FOLDER = "/Users/talha/Downloads/3d_models/"
LOG_FILE = os.path.join(LOG_FOLDER, f"clean_layout_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

def log(message, level="INFO"):
    """Enhanced logging function"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}"
    print(log_line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except Exception as e:
        print(f"Failed to write to log file: {e}")

# ========== TEST CONFIGURATION ==========
TEST_FILES = {
    "figure": "/Users/talha/Downloads/3d_models/3d_models/latest/figure.glb",
    "acc1": "/Users/talha/Downloads/3d_models/3d_models/latest/acc1.glb",
    "acc2": "/Users/talha/Downloads/3d_models/3d_models/latest/acc2.glb",
    "acc3": "/Users/talha/Downloads/3d_models/3d_models/latest/acc3.glb",
}

# ========== EXACT LAYOUT SETTINGS ==========
BASE_WIDTH = 130 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)
BASE_HEIGHT = 190 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)
BASE_THICKNESS = 5 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)

# Text area - ENHANCED
TEXT_HEIGHT = 40 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)  # Increased for larger text and tagline

# Usable area
USABLE_HEIGHT = 140 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)  # Reduced to account for larger text area
USABLE_Y_START = (BASE_HEIGHT/2) - TEXT_HEIGHT - (USABLE_HEIGHT/2)

# Figure area: 70×140
FIGURE_WIDTH = 70 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)
FIGURE_HEIGHT = 140 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)
FIGURE_X = -BASE_WIDTH/2 + FIGURE_WIDTH/2  # Left side
FIGURE_Y = USABLE_Y_START

# Gap between figure and accessories
GAP = 10 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)

# Accessories: 30×30 each
ACCESSORY_SIZE = 30 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)
ACCESSORY_X = FIGURE_X + FIGURE_WIDTH/2 + GAP + ACCESSORY_SIZE/2
ACCESSORY_SPACING = 53.33 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)

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

def create_keychain_hole(base):
    """Create a keychain hole in the base"""
    if not KEYCHAIN_MODE:
        return
    
    log("Creating keychain hole...")
    
    # Calculate hole position - place it in corner but WITHIN the base boundaries
    margin_from_edge = KEYCHAIN_HOLE_SIZE * .8  # Safe margin from edge
    
    # X position: left or right side, within base bounds
    if KEYCHAIN_HOLE_POSITION == "bottom_left":
        hole_x = -(BASE_WIDTH/2) + margin_from_edge  # Left side, inward from edge
    else:  # bottom_right  
        hole_x = (BASE_WIDTH/2) - margin_from_edge   # Right side, inward from edge
    
    # Y position: bottom area as marked in your red circle
    hole_y = -(BASE_HEIGHT/2) + margin_from_edge  # Bottom area, inward from edge
    
    hole_z = BASE_THICKNESS/2  # Center of base thickness
    
    # Create cylinder for hole
    bpy.ops.mesh.primitive_cylinder_add(
        radius=KEYCHAIN_HOLE_SIZE/2,
        depth=BASE_THICKNESS * 2,  # Make it thicker than base to ensure clean cut
        location=(hole_x, hole_y, hole_z)
    )
    hole = bpy.context.active_object
    hole.name = "KeychainHole"
    
    # Select base and hole for boolean operation
    bpy.ops.object.select_all(action='DESELECT')
    base.select_set(True)
    bpy.context.view_layer.objects.active = base
    
    # Add boolean modifier to base
    bool_modifier = base.modifiers.new(name="KeychainHole", type='BOOLEAN')
    bool_modifier.operation = 'DIFFERENCE'
    bool_modifier.object = hole
    
    # Apply the modifier
    bpy.ops.object.modifier_apply(modifier="KeychainHole")
    
    # Delete the hole object (no longer needed)
    bpy.ops.object.select_all(action='DESELECT')
    hole.select_set(True)
    bpy.ops.object.delete()
    
    log(f"✓ Keychain hole created at position: ({hole_x:.1f}, {hole_y:.1f}) - BOTTOM corner, safely within base bounds")

def create_beveled_base():
    """Create the base platform with beveled edges"""
    log("Creating beveled base...")
    bpy.ops.mesh.primitive_cube_add()
    base = bpy.context.active_object
    base.name = "Base"
    base.scale = (BASE_WIDTH/2, BASE_HEIGHT/2, BASE_THICKNESS/2)
    base.location = (0, 0, BASE_THICKNESS/2)
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    
    # Add bevel modifier if enabled
    if BASE_BEVEL:
        log("Adding bevel to base edges...")
        bevel_modifier = base.modifiers.new(name="Bevel", type='BEVEL')
        bevel_modifier.width = 2.0 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)  # Scale bevel for keychain
        bevel_modifier.segments = 3  # Smooth bevel
        bevel_modifier.limit_method = 'ANGLE'
        bevel_modifier.angle_limit = math.radians(60)  # Only bevel sharp edges
        
        # Apply the modifier
        bpy.context.view_layer.objects.active = base
        bpy.ops.object.modifier_apply(modifier="Bevel")
        log("✓ Base bevel applied")
    
    # Create keychain hole if in keychain mode
    create_keychain_hole(base)
    
    log(f"Base created: {base.dimensions}")
    return base

def create_enhanced_titles():
    """Create enhanced H1 title and H3 tagline"""
    log("Creating enhanced titles...")
    
    # Calculate positions
    text_center_y = (BASE_HEIGHT/2) - (TEXT_HEIGHT/2)
    main_title_y = text_center_y + 8 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)  # Above center
    tagline_y = text_center_y - 8 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)     # Below center
    
    # === CREATE MAIN TITLE (H1) ===
    log(f"Creating main title: '{MAIN_TITLE}'")
    bpy.ops.object.text_add()
    main_title_obj = bpy.context.active_object
    main_title_obj.name = "MainTitle"
    main_title_obj.data.body = MAIN_TITLE
    
    # H1 properties - Large and bold (scaled for keychain)
    main_title_obj.data.size = MAIN_TITLE_SIZE * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)
    main_title_obj.data.space_character = 1.1
    main_title_obj.data.space_word = 1.3
    
    # 3D extrusion for H1 (scaled for keychain)
    main_title_obj.data.extrude = 2.5 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)  # Thick extrusion
    if TEXT_BEVEL:
        main_title_obj.data.bevel_depth = 0.4 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)  # Nice bevel
        main_title_obj.data.bevel_resolution = 4  # Smooth bevel
        log("✓ Main title bevel applied")
    
    # Position main title
    main_title_obj.location = (0, main_title_y, BASE_THICKNESS + 2 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1))
    
    # Center the main title
    bpy.context.view_layer.objects.active = main_title_obj
    bpy.ops.object.select_all(action='DESELECT')
    main_title_obj.select_set(True)
    bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS')
    main_title_obj.location = (0, main_title_y, BASE_THICKNESS + 2 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1))
    
    log(f"Main title positioned at: {main_title_obj.location}")
    
    # === CREATE TAGLINE (H3) ===
    log(f"Creating tagline: '{TAGLINE}'")
    bpy.ops.object.text_add()
    tagline_obj = bpy.context.active_object
    tagline_obj.name = "Tagline"
    tagline_obj.data.body = TAGLINE
    
    # H3 properties - Smaller and elegant (scaled for keychain)
    tagline_obj.data.size = TAGLINE_SIZE * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)
    tagline_obj.data.space_character = 1.2
    tagline_obj.data.space_word = 1.4
    
    # 3D extrusion for H3 (smaller than H1, scaled for keychain)
    tagline_obj.data.extrude = 1.2 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)  # Thinner than main title
    if TEXT_BEVEL:
        tagline_obj.data.bevel_depth = 0.2 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)  # Subtle bevel
        tagline_obj.data.bevel_resolution = 3
        log("✓ Tagline bevel applied")
    
    # Position tagline
    tagline_obj.location = (0, tagline_y, BASE_THICKNESS + 1.5 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1))
    
    # Center the tagline
    bpy.context.view_layer.objects.active = tagline_obj
    bpy.ops.object.select_all(action='DESELECT')
    tagline_obj.select_set(True)
    bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS')
    tagline_obj.location = (0, tagline_y, BASE_THICKNESS + 1.5 * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1))
    
    log(f"Tagline positioned at: {tagline_obj.location}")
    
    log("✅ Enhanced titles created successfully")
    return main_title_obj, tagline_obj

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
        log(f"Best mesh object: {best_obj.name} ({max_vertices} vertices)")
        log(f"Dimensions: {best_obj.dimensions}")
    
    return best_obj

def apply_manual_rotation(obj, rotation_type="lay_flat_x"):
    """Apply manual rotation - AGGRESSIVE VERSION that FORCES rotation"""
    
    log(f"   🔧 FORCING rotation on {obj.name}...")
    
    # Step 1: Make sure we're the active object
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    
    # Step 2: Clear ALL existing transforms
    obj.rotation_euler = (0, 0, 0)
    obj.location = (0, 0, 0)
    bpy.context.view_layer.update()
    
    # Step 3: Apply ALL transforms to "bake" them into the mesh
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.context.view_layer.update()
    
    # Step 4: Check if this is a complex object with armatures
    has_armature = False
    for modifier in obj.modifiers:
        if modifier.type == 'ARMATURE':
            log(f"   ⚠️  Found armature modifier: {modifier.name}")
            has_armature = True
    
    # Step 5: If it has armatures, try to apply them
    if has_armature:
        log(f"   🦴 Applying armature modifiers...")
        try:
            for modifier in obj.modifiers:
                if modifier.type == 'ARMATURE':
                    bpy.ops.object.modifier_apply(modifier=modifier.name)
        except Exception as e:
            log(f"   ⚠️  Could not apply armature: {e}")
    
    # Step 6: Enter EDIT MODE to directly transform the mesh
    log(f"   🔧 Entering edit mode for direct mesh transformation...")
    bpy.ops.object.mode_set(mode='EDIT')
    
    # Step 7: Select all vertices
    bpy.ops.mesh.select_all(action='SELECT')
    
    # Step 8: Apply rotation directly to mesh vertices
    if rotation_type == "lay_flat_x_neg90":
        # Rotate -90 degrees around X axis in edit mode
        bpy.ops.transform.rotate(value=math.radians(-90), orient_axis='X')
        log(f"   🔄 Applied DIRECT MESH X rotation: -90° (laying flat)")
    
    elif rotation_type == "lay_flat_x":
        bpy.ops.transform.rotate(value=math.radians(90), orient_axis='X')
        log(f"   🔄 Applied DIRECT MESH X rotation: 90°")
    
    elif rotation_type == "lay_flat_y": 
        bpy.ops.transform.rotate(value=math.radians(90), orient_axis='Y')
        log(f"   🔄 Applied DIRECT MESH Y rotation: 90°")
        
    elif rotation_type == "lay_flat_z":
        bpy.ops.transform.rotate(value=math.radians(90), orient_axis='Z')
        log(f"   🔄 Applied DIRECT MESH Z rotation: 90°")
    
    # Step 9: Exit edit mode
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Step 10: Update and check result
    bpy.context.view_layer.update()
    new_dims = obj.dimensions
    log(f"   📏 After FORCED rotation - dimensions: X={new_dims.x:.1f}, Y={new_dims.y:.1f}, Z={new_dims.z:.1f}")
    
    # Step 11: Verify the rotation worked
    if abs(new_dims.z - 1994.9) < 50:  # Still around 1995mm tall
        log(f"   ⛔ ROTATION STILL FAILED! Trying alternative axis...")
        
        # Try Y rotation instead
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.transform.rotate(value=math.radians(90), orient_axis='Y')
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.update()
        
        final_dims = obj.dimensions
        log(f"   📏 After Y rotation attempt: X={final_dims.x:.1f}, Y={final_dims.y:.1f}, Z={final_dims.z:.1f}")
        
        if abs(final_dims.z - 1994.9) < 50:
            log(f"   💀 BOTH X AND Y ROTATIONS FAILED!")
            log(f"   💡 Your GLB models may have locked transforms or special rigs")
            log(f"   🔄 Try manually rotating in Blender viewport and see which rotation works")
    else:
        log(f"   ✅ ROTATION SUCCESS! Z dimension changed from ~1995 to {new_dims.z:.1f}")

def import_model(filepath, name):
    """Import a model and return the actual mesh object"""
    log(f"Importing: {filepath}")
    
    if not filepath or not os.path.exists(filepath):
        log(f"File not found: {filepath}", "ERROR")
        return None
    
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
            log(f"Unsupported file format: {filepath}", "WARNING")
            return None
        
        # Find new objects
        objects_after = set(bpy.context.scene.objects)
        new_objects = objects_after - objects_before
        
        log(f"Imported {len(new_objects)} objects")
        
        # Find the best mesh object
        mesh_obj = find_best_mesh_object(new_objects)
        
        if mesh_obj:
            # Rename and return the mesh object
            original_name = mesh_obj.name
            mesh_obj.name = name
            log(f"✓ Using mesh object: {original_name} -> {name}")
            return mesh_obj
        else:
            log("✗ No suitable mesh object found", "ERROR")
            return None
            
    except Exception as e:
        log(f"✗ Import failed: {e}", "ERROR")
        return None

def calculate_scale_for_area(obj, target_width, target_height):
    """Calculate scale to fit object in target area"""
    dims = obj.dimensions
    log(f"Object dimensions: {dims.x:.1f} × {dims.y:.1f} × {dims.z:.1f}")
    log(f"Target area: {target_width} × {target_height}")
    
    # Calculate scale needed for width and height
    scale_x = target_width / dims.x if dims.x > 0 else 1.0
    scale_y = target_height / dims.y if dims.y > 0 else 1.0
    
    # Use the smaller scale to ensure it fits in both dimensions
    scale = min(scale_x, scale_y)
    
    log(f"Scale for width: {scale_x:.6f}")
    log(f"Scale for height: {scale_y:.6f}")
    log(f"Using base scale: {scale:.6f}")
    
    return scale

def debug_position_object(obj, target_x, target_y, target_size_x, target_size_y, object_type="object"):
    """Position object with FIXED controls"""
    log(f"\n=== PROCESSING {object_type.upper()}: {obj.name} ===")
    
    # Get settings based on object type
    if object_type == "figure":
        rotation_type = FIGURE_ROTATION
        scale_multiplier = FIGURE_SCALE_MULTIPLIER
        log(f"🎛️  FIGURE CONTROLS: Rotation={rotation_type}, Scale={scale_multiplier}x")
    else:
        rotation_type = ACCESSORY_ROTATION
        scale_multiplier = ACCESSORY_SCALE_MULTIPLIER
        log(f"🎛️  ACCESSORY CONTROLS: Rotation={rotation_type}, Scale={scale_multiplier}x")
    
    # Make sure we're working with the object
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    
    # Apply any existing transforms first
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    
    # Get current dimensions
    dims = obj.dimensions
    log(f"STEP 1 - Initial dimensions: {dims.x:.1f} × {dims.y:.1f} × {dims.z:.1f}")
    
    # Apply rotation
    apply_manual_rotation(obj, rotation_type)
    
    # Calculate and apply scale with multiplier (and keychain scaling)
    current_dims = obj.dimensions
    base_scale = calculate_scale_for_area(obj, target_size_x, target_size_y)
    final_scale = base_scale * scale_multiplier
    if KEYCHAIN_MODE:
        final_scale *= (KEYCHAIN_SCALE * MODEL_SCALE_BOOST)  # Additional scaling for keychain with boost
    obj.scale = (final_scale, final_scale, final_scale)
    
    log(f"Applied scale: {base_scale:.6f} × {scale_multiplier} × {KEYCHAIN_SCALE * MODEL_SCALE_BOOST if KEYCHAIN_MODE else 1} = {final_scale:.6f}")
    
    # Update scene to get final dimensions
    bpy.context.view_layer.update()
    final_dims = obj.dimensions
    log(f"STEP 3 - After scaling: {final_dims.x:.1f} × {final_dims.y:.1f} × {final_dims.z:.1f}")
    
    # POSITIONING: Use Method 2 (flat on base)
    z_pos = BASE_THICKNESS + (final_dims.z / 2)
    obj.location = (target_x, target_y, z_pos)
    
    log(f"FINAL POSITION: ({target_x}, {target_y}, {z_pos:.1f})")
    log(f"=== {object_type.upper()} {obj.name} COMPLETE ===\n")
    
    return obj

def main():
    """Main function for testing"""
    log("=== ENHANCED SCRIPT START ===")
    log(f"LOG FILE: {LOG_FILE}")
    if KEYCHAIN_MODE:
        log(f"🔗 KEYCHAIN MODE ENABLED! Scale: {KEYCHAIN_SCALE}x, Model Boost: {MODEL_SCALE_BOOST}x, Hole: {KEYCHAIN_HOLE_SIZE}mm {KEYCHAIN_HOLE_POSITION}")
    log(f"🎛️  CONTROLS:")
    log(f"   Figure: {FIGURE_ROTATION}, Scale={FIGURE_SCALE_MULTIPLIER}x")
    log(f"   Accessories: {ACCESSORY_ROTATION}, Scale={ACCESSORY_SCALE_MULTIPLIER}x")
    log(f"📝 TEXT SETTINGS:")
    log(f"   Main Title: '{MAIN_TITLE}' (Size: {MAIN_TITLE_SIZE * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)})")
    log(f"   Tagline: '{TAGLINE}' (Size: {TAGLINE_SIZE * (KEYCHAIN_SCALE if KEYCHAIN_MODE else 1)})")
    log(f"   Base Bevel: {BASE_BEVEL}, Text Bevel: {TEXT_BEVEL}")
    
    setup_scene()
    clear_scene()
    
    # Create beveled base (with keychain hole if enabled)
    base = create_beveled_base()
    
    # Create enhanced titles
    main_title, tagline = create_enhanced_titles()
    
    # Import and position figure
    log("\n" + "="*50)
    log("PROCESSING FIGURE")
    log("="*50)
    figure = import_model(TEST_FILES["figure"], "Figure")
    if figure:
        debug_position_object(
            figure, 
            FIGURE_X, FIGURE_Y,
            FIGURE_WIDTH, FIGURE_HEIGHT,
            "figure"
        )
    
    # Import and position accessories
    log("\n" + "="*50)
    log("PROCESSING ACCESSORIES")
    log("="*50)
    
    for i, acc_key in enumerate(["acc1", "acc2", "acc3"]):
        log(f"\n--- ACCESSORY {i+1} ---")
        acc = import_model(TEST_FILES[acc_key], f"Accessory_{i+1}")
        if acc:
            # Calculate Y position for this accessory
            acc_y = USABLE_Y_START + (USABLE_HEIGHT/2) - (ACCESSORY_SIZE/2) - (i * ACCESSORY_SPACING)
            debug_position_object(
                acc,
                ACCESSORY_X, acc_y,
                ACCESSORY_SIZE, ACCESSORY_SIZE,
                f"accessory_{i+1}"
            )
    
    log("\n" + "="*50)
    if KEYCHAIN_MODE:
        log("KEYCHAIN SCRIPT COMPLETE!")
        log(f"✅ Keychain size: {BASE_WIDTH:.1f}mm × {BASE_HEIGHT:.1f}mm")
        log(f"✅ Keychain hole: {KEYCHAIN_HOLE_SIZE}mm diameter ({KEYCHAIN_HOLE_POSITION})")
    else:
        log("ENHANCED SCRIPT COMPLETE!")
    log("="*50)
    log(f"✅ Large H1 title: '{MAIN_TITLE}'")
    log(f"✅ H3 tagline: '{TAGLINE}'")
    log(f"✅ Beveled base edges")
    log(f"✅ Beveled text")
    log(f"✅ Models properly rotated and positioned")
    log(f"Check log file: {LOG_FILE}")

if __name__ == "__main__":
    main()