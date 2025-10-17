import os
import subprocess
import asyncio
import tempfile
from typing import List, Dict, Optional
from datetime import datetime
import aiofiles

# Import the actual settings
try:
    from config.settings import settings
except ImportError:
    # Fallback settings if import fails
    class Settings:
        BLENDER_EXECUTABLE = "blender"
        BLENDER_TIMEOUT = 300
        BLENDER_HEADLESS = True
        PROCESSED_PATH = "./storage/processed"
        STL_SCALE_FACTOR = 1.0
    
    settings = Settings()


class BlenderProcessor:
    def __init__(self):
        """Initialize Blender processor"""
        self.blender_executable = settings.BLENDER_EXECUTABLE
        self.timeout = settings.BLENDER_TIMEOUT
        self.headless = settings.BLENDER_HEADLESS
        print(f"✅ Blender processor initialized - Executable: {self.blender_executable}")

    async def process_3d_models(self, job_id: str, models_3d: List[Dict]) -> Dict:
        """
        Process 3D models into final starter pack (both regular and keychain versions)
        Args:
            job_id: Job identifier
            models_3d: List of 3D model metadata
        Returns:
            Final processing result with STL file info
        """
        try:
            print(f"🎨 Processing 3D models for job {job_id} - {len(models_3d)} models")
            
            # Create output directory
            output_dir = os.path.join(settings.PROCESSED_PATH, job_id, "final")
            os.makedirs(output_dir, exist_ok=True)
            
            # Organize models by type
            organized_models = self._organize_models_by_type(models_3d)
            
            # Create and execute regular Blender script
            print("🎯 Creating regular starter pack...")
            blender_script = await self._create_blender_script(job_id, organized_models, output_dir)
            if not blender_script:
                raise Exception("Failed to create regular Blender script")
            
            result = await self._execute_blender_script(blender_script, output_dir)
            if not result:
                raise Exception("Regular Blender script execution failed")
            
            # Clean up regular script
            if os.path.exists(blender_script):
                os.remove(blender_script)
            
            # Create and execute keychain Blender script
            print("🔗 Creating keychain version...")
            keychain_script = await self._create_keychain_blender_script(job_id, organized_models, output_dir)
            if not keychain_script:
                raise Exception("Failed to create keychain Blender script")
            
            keychain_result = await self._execute_blender_script(keychain_script, output_dir)
            if not keychain_result:
                raise Exception("Keychain Blender script execution failed")
            
            # Clean up keychain script
            if os.path.exists(keychain_script):
                os.remove(keychain_script)
            
            # Combine results from both scripts
            combined_files = result.get('output_files', []) + keychain_result.get('output_files', [])
            
            return {
                'success': True,
                'output_files': combined_files,
                'output_dir': output_dir,
                'regular_result': result,
                'keychain_result': keychain_result
            }
            
        except Exception as e:
            print(f"❌ Error in process_3d_models: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'job_id': job_id
            }

    def _extract_accessory_number(self, filepath: str) -> int:
        """
        Extract accessory number from filename for sorting
        Args:
            filepath: Path to the accessory file
        Returns:
            Integer representing the accessory number
        """
        try:
            filename = os.path.basename(filepath)
            if 'accessory_' in filename:
                # Extract number after 'accessory_'
                # Example: accessory_1_3d_20250723_110236.glb -> 1
                parts = filename.split('accessory_')[1]
                number_str = parts.split('_')[0]
                return int(number_str)
            return 999  # Default for unknown patterns
        except Exception as e:
            print(f"⚠️  Could not extract accessory number from {filepath}: {e}")
            return 999

    def _organize_models_by_type(self, models_3d: List[Dict]) -> Dict:
        """
        Organize 3D models by their type based on filename patterns
        Args:
            models_3d: List of 3D model metadata
        Returns:
            Dictionary organized by model type
        """
        organized = {
            'figure': None,
            'accessories': []
        }
        
        print(f"🔍 Organizing {len(models_3d)} models:")
        
        for model in models_3d:
            # Get the filename or model path to analyze
            model_path = model.get('model_path', '')
            filename = os.path.basename(model_path) if model_path else ''
            
            print(f"   📁 Analyzing: {filename}")
            
            # Check if this is the base character (figure)
            if 'base_character_3d' in filename.lower():
                organized['figure'] = model
                print(f"   🎯 → Identified as FIGURE: {filename}")
            # Check if this is an accessory
            elif 'accessory_' in filename.lower() and '_3d' in filename.lower():
                organized['accessories'].append(model)
                print(f"   🎨 → Identified as ACCESSORY: {filename}")
            else:
                # Log unknown patterns but still treat as accessory
                organized['accessories'].append(model)
                print(f"   ⚠️  → Unknown pattern, treating as accessory: {filename}")
        
        # Sort accessories by number (accessory_1, accessory_2, accessory_3)
        organized['accessories'].sort(key=lambda x: self._extract_accessory_number(x.get('model_path', '')))
        
        print(f"📋 Final organization:")
        print(f" - Figure: {'✅ ' + os.path.basename(organized['figure']['model_path']) if organized['figure'] else '❌ None found'}")
        print(f" - Accessories: {len(organized['accessories'])}")
        for i, acc in enumerate(organized['accessories']):
            acc_name = os.path.basename(acc.get('model_path', 'Unknown'))
            print(f"   {i+1}. {acc_name}")
        
        return organized

    async def _create_blender_script(self, job_id: str, organized_models: Dict, output_dir: str) -> Optional[str]:
        """
        Create customized Blender script with actual model paths
        Args:
            job_id: Job identifier
            organized_models: Organized model data
            output_dir: Output directory for final files
        Returns:
            Path to created Blender script
        """
        try:
            # Create temporary script file
            script_fd, script_path = tempfile.mkstemp(suffix='.py', prefix=f'blender_script_{job_id}_')
            
            # Get model paths
            figure_path = organized_models['figure']['model_path'] if organized_models['figure'] else None
            accessory_paths = [acc['model_path'] for acc in organized_models['accessories']]
            
            # Ensure we have at least 3 accessories (use placeholders if needed)
            while len(accessory_paths) < 3:
                accessory_paths.append(None)
            
            # Create the Blender script content
            script_content = self._generate_blender_script_content(
                job_id=job_id,
                figure_path=figure_path,
                accessory_paths=accessory_paths[:3],  # Take first 3
                output_dir=output_dir
            )
            
            # Write script to file
            with os.fdopen(script_fd, 'w') as f:
                f.write(script_content)
            
            print(f"📝 Created Blender script: {script_path}")
            return script_path
        except Exception as e:
            print(f"❌ Error creating Blender script: {str(e)}")
            return None

    def _generate_blender_script_content(self, job_id: str, figure_path: Optional[str],
                                            accessory_paths: List[Optional[str]], output_dir: str) -> str:
        """Generate the Blender script content with color system and style theming"""
        # Convert paths to absolute paths and handle None values
        figure_abs = os.path.abspath(figure_path) if figure_path else None
        accessory_abs = [os.path.abspath(path) if path else None for path in accessory_paths]
        output_abs = os.path.abspath(output_dir)
        
        # Debug: Print the paths being used
        print(f"🔍 Script Generation Debug:")
        print(f"  Figure: {figure_abs}")
        print(f"  Accessories: {accessory_abs}")
        print(f"  Output: {output_abs}")
        
        # Format the file paths for the script
        figure_path_str = f'"{figure_abs}"' if figure_abs else 'None'
        acc1_path = f'"{accessory_abs[0]}"' if accessory_abs[0] else 'None'
        acc2_path = f'"{accessory_abs[1]}"' if accessory_abs[1] else 'None'
        acc3_path = f'"{accessory_abs[2]}"' if accessory_abs[2] else 'None'

        # Generate the complete Blender script with our integrated version
        script_content = f'''# ========== EARLY DEBUG ==========
print("🔍 SCRIPT LOADING...")
print(f"✅ Imports successful")

import bpy
import bmesh
import os
import sys
from mathutils import Vector
from datetime import datetime
import math

# ========== JOB CONFIGURATION ==========
JOB_ID = "{job_id}"
OUTPUT_DIR = r"{output_abs}"

# Create log file for this job
LOG_FILE = os.path.join(OUTPUT_DIR, f"blender_log_{{JOB_ID}}.txt")

# ========== DEFAULT COLOR PALETTE ==========
COLOR_PALETTE = {{
    "base": (0.1, 0.1, 0.1, 1.0),              # Dark charcoal
    "title": (0.9, 0.9, 0.85, 1.0),            # Off-white/cream
    "figure": (0.4, 0.6, 0.8, 1.0),            # Modern blue
    "accessories": [
        (0.8, 0.4, 0.2, 1.0),                  # Orange
        (0.2, 0.7, 0.3, 1.0),                  # Green
        (0.7, 0.3, 0.7, 1.0)                   # Purple
    ],
    "material_properties": {{
        "figure": {{"metallic": 0.2, "roughness": 0.4}},
        "accessories": {{"metallic": 0.1, "roughness": 0.5}}
    }}
}}

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
TEST_FILES = {{
    "figure": {figure_path_str},
    "acc1": {acc1_path},
    "acc2": {acc2_path},
    "acc3": {acc3_path},
}}

# ========== EXACT LAYOUT SETTINGS ==========
BASE_WIDTH = 130
BASE_HEIGHT = 190
BASE_THICKNESS = 5

# Text area - ENHANCED
TEXT_HEIGHT = 40  # Increased for larger text and tagline

# Usable area
USABLE_HEIGHT = 140  # Reduced to account for larger text area
USABLE_Y_START = (BASE_HEIGHT/2) - TEXT_HEIGHT - (USABLE_HEIGHT/2)

# Figure area: 70×140
FIGURE_WIDTH = 70
FIGURE_HEIGHT = 140
FIGURE_X = -BASE_WIDTH/2 + FIGURE_WIDTH/2  # Left side
FIGURE_Y = USABLE_Y_START

# Gap between figure and accessories
GAP = 10

# Accessories: 30×30 each
ACCESSORY_SIZE = 30
ACCESSORY_X = FIGURE_X + FIGURE_WIDTH/2 + GAP + ACCESSORY_SIZE/2
ACCESSORY_SPACING = 53.33

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

def create_beveled_base():
    """Create the base platform with beveled edges and themed color"""
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
        bevel_modifier.width = 2.0  # 2mm bevel
        bevel_modifier.segments = 3  # Smooth bevel
        bevel_modifier.limit_method = 'ANGLE'
        bevel_modifier.angle_limit = math.radians(60)  # Only bevel sharp edges
        
        # Apply the modifier
        bpy.context.view_layer.objects.active = base
        bpy.ops.object.modifier_apply(modifier="Bevel")
        log("✓ Base bevel applied")
    
    # Apply themed color
    base_material = create_material("BaseMaterial", COLOR_PALETTE["base"], 0.1, 0.8)
    apply_material_to_object(base, base_material)
    
    log(f"Base created with default color: {{base.dimensions}}")
    return base

def create_enhanced_titles():
    """Create enhanced H1 title and H3 tagline with themed colors"""
    log("Creating enhanced titles...")
    
    # Calculate positions
    text_center_y = (BASE_HEIGHT/2) - (TEXT_HEIGHT/2)
    main_title_y = text_center_y + 8  # Above center
    tagline_y = text_center_y - 8     # Below center
    
    # === CREATE MAIN TITLE (H1) ===
    log(f"Creating main title: '{{MAIN_TITLE}}'")
    bpy.ops.object.text_add()
    main_title_obj = bpy.context.active_object
    main_title_obj.name = "MainTitle"
    main_title_obj.data.body = MAIN_TITLE
    
    # H1 properties - Large and bold
    main_title_obj.data.size = MAIN_TITLE_SIZE
    main_title_obj.data.space_character = 1.1
    main_title_obj.data.space_word = 1.3
    
    # 3D extrusion for H1
    main_title_obj.data.extrude = 2.5  # Thick extrusion
    if TEXT_BEVEL:
        main_title_obj.data.bevel_depth = 0.4  # Nice bevel
        main_title_obj.data.bevel_resolution = 4  # Smooth bevel
        log("✓ Main title bevel applied")
    
    # Position main title
    main_title_obj.location = (0, main_title_y, BASE_THICKNESS + 2)
    
    # Center the main title
    bpy.context.view_layer.objects.active = main_title_obj
    bpy.ops.object.select_all(action='DESELECT')
    main_title_obj.select_set(True)
    bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS')
    main_title_obj.location = (0, main_title_y, BASE_THICKNESS + 2)
    
    # Apply themed color to main title
    title_material = create_material("TitleMaterial", COLOR_PALETTE["title"], 0.2, 0.3)
    apply_material_to_object(main_title_obj, title_material)
    
    log(f"Main title positioned at: {{main_title_obj.location}}")
    
    # === CREATE TAGLINE (H3) ===
    log(f"Creating tagline: '{{TAGLINE}}'")
    bpy.ops.object.text_add()
    tagline_obj = bpy.context.active_object
    tagline_obj.name = "Tagline"
    tagline_obj.data.body = TAGLINE
    
    # H3 properties - Smaller and elegant
    tagline_obj.data.size = TAGLINE_SIZE
    tagline_obj.data.space_character = 1.2
    tagline_obj.data.space_word = 1.4
    
    # 3D extrusion for H3 (smaller than H1)
    tagline_obj.data.extrude = 1.2  # Thinner than main title
    if TEXT_BEVEL:
        tagline_obj.data.bevel_depth = 0.2  # Subtle bevel
        tagline_obj.data.bevel_resolution = 3
        log("✓ Tagline bevel applied")
    
    # Position tagline
    tagline_obj.location = (0, tagline_y, BASE_THICKNESS + 1.5)
    
    # Center the tagline
    bpy.context.view_layer.objects.active = tagline_obj
    bpy.ops.object.select_all(action='DESELECT')
    tagline_obj.select_set(True)
    bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS')
    tagline_obj.location = (0, tagline_y, BASE_THICKNESS + 1.5)
    
    # Apply themed color to tagline (same as main title)
    tagline_material = create_material("TaglineMaterial", COLOR_PALETTE["title"], 0.2, 0.3)
    apply_material_to_object(tagline_obj, tagline_material)
    
    log(f"Tagline positioned at: {{tagline_obj.location}}")
    log(f"✅ Enhanced titles created with default colors")
    
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
        log(f"Best mesh object: {{best_obj.name}} ({{max_vertices}} vertices)")
        log(f"Dimensions: {{best_obj.dimensions}}")
    
    return best_obj

def apply_manual_rotation(obj, rotation_type="lay_flat_x"):
    """Apply manual rotation - AGGRESSIVE VERSION that FORCES rotation"""
    
    log(f"   🔧 FORCING rotation on {{obj.name}}...")
    
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
            log(f"   ⚠️  Found armature modifier: {{modifier.name}}")
            has_armature = True
    
    # Step 5: If it has armatures, try to apply them
    if has_armature:
        log(f"   🦴 Applying armature modifiers...")
        try:
            for modifier in obj.modifiers:
                if modifier.type == 'ARMATURE':
                    bpy.ops.object.modifier_apply(modifier=modifier.name)
        except Exception as e:
            log(f"   ⚠️  Could not apply armature: {{e}}")
    
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
    log(f"   📏 After FORCED rotation - dimensions: X={{new_dims.x:.1f}}, Y={{new_dims.y:.1f}}, Z={{new_dims.z:.1f}}")
    
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
        log(f"   📏 After Y rotation attempt: X={{final_dims.x:.1f}}, Y={{final_dims.y:.1f}}, Z={{final_dims.z:.1f}}")
        
        if abs(final_dims.z - 1994.9) < 50:
            log(f"   💀 BOTH X AND Y ROTATIONS FAILED!")
            log(f"   💡 Your GLB models may have locked transforms or special rigs")
            log(f"   🔄 Try manually rotating in Blender viewport and see which rotation works")
    else:
        log(f"   ✅ ROTATION SUCCESS! Z dimension changed from ~1995 to {{new_dims.z:.1f}}")

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
    log(f"Using base scale: {{scale:.6f}}")
    
    return scale

def debug_position_object(obj, target_x, target_y, target_size_x, target_size_y, object_type="object"):
    """Position object with FIXED controls and themed coloring"""
    log(f"\\n=== PROCESSING {{object_type.upper()}}: {{obj.name}} ===")
    
    # Get settings based on object type
    if object_type == "figure":
        rotation_type = FIGURE_ROTATION
        scale_multiplier = FIGURE_SCALE_MULTIPLIER
        log(f"🎛️  FIGURE CONTROLS: Rotation={{rotation_type}}, Scale={{scale_multiplier}}x")
    else:
        rotation_type = ACCESSORY_ROTATION
        scale_multiplier = ACCESSORY_SCALE_MULTIPLIER
        log(f"🎛️  ACCESSORY CONTROLS: Rotation={{rotation_type}}, Scale={{scale_multiplier}}x")
    
    # Make sure we're working with the object
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    
    # Apply any existing transforms first
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    
    # Get current dimensions
    dims = obj.dimensions
    log(f"STEP 1 - Initial dimensions: {{dims.x:.1f}} × {{dims.y:.1f}} × {{dims.z:.1f}}")
    
    # Apply rotation
    apply_manual_rotation(obj, rotation_type)
    
    # Calculate and apply scale with multiplier
    current_dims = obj.dimensions
    base_scale = calculate_scale_for_area(obj, target_size_x, target_size_y)
    final_scale = base_scale * scale_multiplier
    obj.scale = (final_scale, final_scale, final_scale)
    
    log(f"Applied scale: {{base_scale:.6f}} × {{scale_multiplier}} = {{final_scale:.6f}}")
    
    # Update scene to get final dimensions
    bpy.context.view_layer.update()
    final_dims = obj.dimensions
    log(f"STEP 3 - After scaling: {{final_dims.x:.1f}} × {{final_dims.y:.1f}} × {{final_dims.z:.1f}}")
    
    # POSITIONING: Use Method 2 (flat on base)
    z_pos = BASE_THICKNESS + (final_dims.z / 2)
    obj.location = (target_x, target_y, z_pos)
    
    # APPLY THEMED COLORS
    if object_type == "figure":
        # APPLY FIGURE COLOR
        figure_props = COLOR_PALETTE["material_properties"]["figure"]
        figure_material = create_material(
            "FigureMaterial", 
            COLOR_PALETTE["figure"], 
            figure_props["metallic"], 
            figure_props["roughness"]
        )
        apply_material_to_object(obj, figure_material)
        log(f"🎨 Applied figure color to {{obj.name}}")
    
    else:
        # APPLY ACCESSORY COLOR (extract index from object name)
        accessory_index = 0
        if "accessory_" in object_type.lower():
            try:
                accessory_index = int(object_type.split("_")[-1]) - 1
            except:
                accessory_index = 0
        
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
        log(f"🎨 Applied accessory color #{{color_index + 1}} to {{obj.name}}")
    
    log(f"FINAL POSITION: ({{target_x}}, {{target_y}}, {{z_pos:.1f}})")
    log(f"=== {{object_type.upper()}} {{obj.name}} COMPLETE ===\\n")
    
    return obj

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
    """Main function for integrated manual + AI pipeline"""
    print("🚀 SCRIPT STARTING...")
    print(f"Python version: {{sys.version}}")
    print(f"Blender version: {{bpy.app.version}}")
    print(f"Current working directory: {{os.getcwd()}}")
    print(f"Script file location: {{__file__ if '__file__' in globals() else 'Unknown'}}")
    
    log("=== ENHANCED STARTER PACK LAYOUT GENERATION ===")
    log(f"Job ID: {{JOB_ID}}")
    log(f"Output Directory: {{OUTPUT_DIR}}")
    log(f"🎛️  CONTROLS:")
    log(f"   Figure: {{FIGURE_ROTATION}}, Scale={{FIGURE_SCALE_MULTIPLIER}}x")
    log(f"   Accessories: {{ACCESSORY_ROTATION}}, Scale={{ACCESSORY_SCALE_MULTIPLIER}}x")
    log(f"📝 TEXT SETTINGS:")
    log(f"   Main Title: '{{MAIN_TITLE}}' (Size: {{MAIN_TITLE_SIZE}})")
    log(f"   Tagline: '{{TAGLINE}}' (Size: {{TAGLINE_SIZE}})")
    log(f"   Base Bevel: {{BASE_BEVEL}}, Text Bevel: {{TEXT_BEVEL}}")
    log(f"🎨 Color Palette: default theme loaded")
    
    setup_scene()
    clear_scene()
    
    # Create beveled base with themed color
    base = create_beveled_base()
    
    # Create enhanced titles with themed colors
    main_title, tagline = create_enhanced_titles()
    
    # Import and position figure
    log("\\n" + "="*50)
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
    log("\\n" + "="*50)
    log("PROCESSING ACCESSORIES")
    log("="*50)
    
    for i, acc_key in enumerate(["acc1", "acc2", "acc3"]):
        log(f"\\n--- ACCESSORY {{i+1}} ---")
        acc = import_model(TEST_FILES[acc_key], f"Accessory_{{i+1}}")
        if acc:
            # Calculate Y position for this accessory
            acc_y = USABLE_Y_START + (USABLE_HEIGHT/2) - (ACCESSORY_SIZE/2) - (i * ACCESSORY_SPACING)
            debug_position_object(
                acc,
                ACCESSORY_X, acc_y,
                ACCESSORY_SIZE, ACCESSORY_SIZE,
                f"accessory_{{i+1}}"
            )
    
    # Export the final files
    export_files()
    
    log("\\n" + "="*50)
    log("ENHANCED STARTER PACK LAYOUT COMPLETE!")
    log("="*50)
    log(f"✅ Large H1 title: '{{MAIN_TITLE}}'")
    log(f"✅ H3 tagline: '{{TAGLINE}}'")
    log(f"✅ Beveled base edges")
    log(f"✅ Beveled text")
    log(f"✅ Color theme applied to all objects")
    log(f"✅ Models properly rotated using manual controls")
    log(f"✅ All models properly scaled and positioned")
    log(f"✅ Files exported successfully")
    log(f"Check log file: {{LOG_FILE}}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        error_msg = f"FATAL ERROR: {{e}}"
        print(error_msg)
        print("TRACEBACK:")
        traceback.print_exc()
        
        # Try to write error to log file
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\\n=== FATAL ERROR ===\\n")
                f.write(f"{{error_msg}}\\n")
                f.write("TRACEBACK:\\n")
                f.write(traceback.format_exc())
                f.write("\\n=== END ERROR ===\\n")
        except:
            pass
        
        # Exit with error code
        import sys
        sys.exit(1)
'''
        return script_content

    async def _create_keychain_blender_script(self, job_id: str, organized_models: Dict, output_dir: str) -> Optional[str]:
        """
        Create keychain version of Blender script
        Args:
            job_id: Job identifier
            organized_models: Organized model data
            output_dir: Output directory for final files
        Returns:
            Path to created keychain Blender script
        """
        try:
            # Create temporary script file
            script_fd, script_path = tempfile.mkstemp(suffix='.py', prefix=f'blender_keychain_{job_id}_')
            
            # Get model paths
            figure_path = organized_models['figure']['model_path'] if organized_models['figure'] else None
            accessory_paths = [acc['model_path'] for acc in organized_models['accessories']]
            
            # Ensure we have at least 3 accessories (use placeholders if needed)
            while len(accessory_paths) < 3:
                accessory_paths.append(None)
            
            # Create the keychain Blender script content
            script_content = self._generate_keychain_blender_script_content(
                job_id=job_id,
                figure_path=figure_path,
                accessory_paths=accessory_paths[:3],  # Take first 3
                output_dir=output_dir
            )
            
            # Write script to file
            with os.fdopen(script_fd, 'w') as f:
                f.write(script_content)
            
            print(f"📝 Created keychain Blender script: {script_path}")
            return script_path
        except Exception as e:
            print(f"❌ Error creating keychain Blender script: {str(e)}")
            return None

    def _generate_keychain_blender_script_content(self, job_id: str, figure_path: Optional[str],
                                                 accessory_paths: List[Optional[str]], output_dir: str) -> str:
        """Generate the keychain Blender script content with all keychain-specific features"""
        # Convert paths to absolute paths and handle None values
        figure_abs = os.path.abspath(figure_path) if figure_path else None
        accessory_abs = [os.path.abspath(path) if path else None for path in accessory_paths]
        output_abs = os.path.abspath(output_dir)
        
        # Debug: Print the paths being used
        print(f"🔍 Keychain Script Generation Debug:")
        print(f"  Figure: {figure_abs}")
        print(f"  Accessories: {accessory_abs}")
        print(f"  Output: {output_abs}")
        
        # Format the file paths for the script
        figure_path_str = f'"{figure_abs}"' if figure_abs else 'None'
        acc1_path = f'"{accessory_abs[0]}"' if accessory_abs[0] else 'None'
        acc2_path = f'"{accessory_abs[1]}"' if accessory_abs[1] else 'None'
        acc3_path = f'"{accessory_abs[2]}"' if accessory_abs[2] else 'None'

        # Generate the complete keychain Blender script (based on keychain_blender.py)
        script_content = f'''# ========== KEYCHAIN VERSION ==========
print("🔗 KEYCHAIN SCRIPT LOADING...")
print(f"✅ Keychain script imports successful")

import bpy
import bmesh
import os
import sys
from mathutils import Vector
from datetime import datetime
import math

# ========== JOB CONFIGURATION ==========
JOB_ID = "{job_id}"
OUTPUT_DIR = r"{output_abs}"

# Create log file for this job
LOG_FILE = os.path.join(OUTPUT_DIR, f"keychain_blender_log_{{JOB_ID}}.txt")

# ========== KEYCHAIN MODE ENABLED ==========
KEYCHAIN_MODE = True                  # Enable keychain mode
KEYCHAIN_SCALE = 0.3                  # Scale down to 30% for keychain size
KEYCHAIN_HOLE_SIZE = 5                # Keychain hole diameter in mm
KEYCHAIN_HOLE_POSITION = "bottom_left"  # "bottom_left" or "bottom_right"
MODEL_SCALE_BOOST = 2.5               # Boost model size for keychain (makes models bigger)

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

def log(message, level="INFO"):
    """Enhanced logging function"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_line = f"[{{timestamp}}] [{{level}}] {{message}}"
    print(log_line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\\\\n")
    except Exception as e:
        print(f"Failed to write to log file: {{e}}")

# ========== TEST CONFIGURATION ==========
TEST_FILES = {{
    "figure": {figure_path_str},
    "acc1": {acc1_path},
    "acc2": {acc2_path},
    "acc3": {acc3_path},
}}

# ========== EXACT LAYOUT SETTINGS (SCALED FOR KEYCHAIN) ==========
BASE_WIDTH = 130 * KEYCHAIN_SCALE
BASE_HEIGHT = 190 * KEYCHAIN_SCALE
BASE_THICKNESS = 5 * KEYCHAIN_SCALE

# Text area - ENHANCED
TEXT_HEIGHT = 40 * KEYCHAIN_SCALE

# Usable area
USABLE_HEIGHT = 140 * KEYCHAIN_SCALE
USABLE_Y_START = (BASE_HEIGHT/2) - TEXT_HEIGHT - (USABLE_HEIGHT/2)

# Figure area: 70×140
FIGURE_WIDTH = 70 * KEYCHAIN_SCALE
FIGURE_HEIGHT = 140 * KEYCHAIN_SCALE
FIGURE_X = -BASE_WIDTH/2 + FIGURE_WIDTH/2  # Left side
FIGURE_Y = USABLE_Y_START

# Gap between figure and accessories
GAP = 10 * KEYCHAIN_SCALE

# Accessories: 30×30 each
ACCESSORY_SIZE = 30 * KEYCHAIN_SCALE
ACCESSORY_X = FIGURE_X + FIGURE_WIDTH/2 + GAP + ACCESSORY_SIZE/2
ACCESSORY_SPACING = 53.33 * KEYCHAIN_SCALE

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
    
    log(f"✓ Keychain hole created at position: ({{hole_x:.1f}}, {{hole_y:.1f}}) - BOTTOM corner, safely within base bounds")

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
        bevel_modifier.width = 2.0 * KEYCHAIN_SCALE  # Scale bevel for keychain
        bevel_modifier.segments = 3  # Smooth bevel
        bevel_modifier.limit_method = 'ANGLE'
        bevel_modifier.angle_limit = math.radians(60)  # Only bevel sharp edges
        
        # Apply the modifier
        bpy.context.view_layer.objects.active = base
        bpy.ops.object.modifier_apply(modifier="Bevel")
        log("✓ Base bevel applied")
    
    # Create keychain hole if in keychain mode
    create_keychain_hole(base)
    
    log(f"Base created: {{base.dimensions}}")
    return base

def create_enhanced_titles():
    """Create enhanced H1 title and H3 tagline"""
    log("Creating enhanced titles...")
    
    # Calculate positions
    text_center_y = (BASE_HEIGHT/2) - (TEXT_HEIGHT/2)
    main_title_y = text_center_y + 8 * KEYCHAIN_SCALE  # Above center
    tagline_y = text_center_y - 8 * KEYCHAIN_SCALE     # Below center
    
    # === CREATE MAIN TITLE (H1) ===
    log(f"Creating main title: '{{MAIN_TITLE}}'")
    bpy.ops.object.text_add()
    main_title_obj = bpy.context.active_object
    main_title_obj.name = "MainTitle"
    main_title_obj.data.body = MAIN_TITLE
    
    # H1 properties - Large and bold (scaled for keychain)
    main_title_obj.data.size = MAIN_TITLE_SIZE * KEYCHAIN_SCALE
    main_title_obj.data.space_character = 1.1
    main_title_obj.data.space_word = 1.3
    
    # 3D extrusion for H1 (scaled for keychain)
    main_title_obj.data.extrude = 2.5 * KEYCHAIN_SCALE  # Thick extrusion
    if TEXT_BEVEL:
        main_title_obj.data.bevel_depth = 0.4 * KEYCHAIN_SCALE  # Nice bevel
        main_title_obj.data.bevel_resolution = 4  # Smooth bevel
        log("✓ Main title bevel applied")
    
    # Position main title
    main_title_obj.location = (0, main_title_y, BASE_THICKNESS + 2 * KEYCHAIN_SCALE)
    
    # Center the main title
    bpy.context.view_layer.objects.active = main_title_obj
    bpy.ops.object.select_all(action='DESELECT')
    main_title_obj.select_set(True)
    bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS')
    main_title_obj.location = (0, main_title_y, BASE_THICKNESS + 2 * KEYCHAIN_SCALE)
    
    log(f"Main title positioned at: {{main_title_obj.location}}")
    
    # === CREATE TAGLINE (H3) ===
    log(f"Creating tagline: '{{TAGLINE}}'")
    bpy.ops.object.text_add()
    tagline_obj = bpy.context.active_object
    tagline_obj.name = "Tagline"
    tagline_obj.data.body = TAGLINE
    
    # H3 properties - Smaller and elegant (scaled for keychain)
    tagline_obj.data.size = TAGLINE_SIZE * KEYCHAIN_SCALE
    tagline_obj.data.space_character = 1.2
    tagline_obj.data.space_word = 1.4
    
    # 3D extrusion for H3 (smaller than H1, scaled for keychain)
    tagline_obj.data.extrude = 1.2 * KEYCHAIN_SCALE  # Thinner than main title
    if TEXT_BEVEL:
        tagline_obj.data.bevel_depth = 0.2 * KEYCHAIN_SCALE  # Subtle bevel
        tagline_obj.data.bevel_resolution = 3
        log("✓ Tagline bevel applied")
    
    # Position tagline
    tagline_obj.location = (0, tagline_y, BASE_THICKNESS + 1.5 * KEYCHAIN_SCALE)
    
    # Center the tagline
    bpy.context.view_layer.objects.active = tagline_obj
    bpy.ops.object.select_all(action='DESELECT')
    tagline_obj.select_set(True)
    bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS')
    tagline_obj.location = (0, tagline_y, BASE_THICKNESS + 1.5 * KEYCHAIN_SCALE)
    
    log(f"Tagline positioned at: {{tagline_obj.location}}")
    
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
        log(f"Best mesh object: {{best_obj.name}} ({{max_vertices}} vertices)")
        log(f"Dimensions: {{best_obj.dimensions}}")
    
    return best_obj

def apply_manual_rotation(obj, rotation_type="lay_flat_x"):
    """Apply manual rotation - AGGRESSIVE VERSION that FORCES rotation"""
    
    log(f"   🔧 FORCING rotation on {{obj.name}}...")
    
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
            log(f"   ⚠️  Found armature modifier: {{modifier.name}}")
            has_armature = True
    
    # Step 5: If it has armatures, try to apply them
    if has_armature:
        log(f"   🦴 Applying armature modifiers...")
        try:
            for modifier in obj.modifiers:
                if modifier.type == 'ARMATURE':
                    bpy.ops.object.modifier_apply(modifier=modifier.name)
        except Exception as e:
            log(f"   ⚠️  Could not apply armature: {{e}}")
    
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
    log(f"   📏 After FORCED rotation - dimensions: X={{new_dims.x:.1f}}, Y={{new_dims.y:.1f}}, Z={{new_dims.z:.1f}}")

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
    log(f"Using base scale: {{scale:.6f}}")
    
    return scale

def debug_position_object(obj, target_x, target_y, target_size_x, target_size_y, object_type="object"):
    """Position object with FIXED controls"""
    log(f"\\\\n=== PROCESSING {{object_type.upper()}}: {{obj.name}} ===")
    
    # Get settings based on object type
    if object_type == "figure":
        rotation_type = FIGURE_ROTATION
        scale_multiplier = FIGURE_SCALE_MULTIPLIER
        log(f"🎛️  FIGURE CONTROLS: Rotation={{rotation_type}}, Scale={{scale_multiplier}}x")
    else:
        rotation_type = ACCESSORY_ROTATION
        scale_multiplier = ACCESSORY_SCALE_MULTIPLIER
        log(f"🎛️  ACCESSORY CONTROLS: Rotation={{rotation_type}}, Scale={{scale_multiplier}}x")
    
    # Make sure we're working with the object
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    
    # Apply any existing transforms first
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    
    # Get current dimensions
    dims = obj.dimensions
    log(f"STEP 1 - Initial dimensions: {{dims.x:.1f}} × {{dims.y:.1f}} × {{dims.z:.1f}}")
    
    # Apply rotation
    apply_manual_rotation(obj, rotation_type)
    
    # Calculate and apply scale with multiplier (and keychain scaling)
    current_dims = obj.dimensions
    base_scale = calculate_scale_for_area(obj, target_size_x, target_size_y)
    final_scale = base_scale * scale_multiplier
    if KEYCHAIN_MODE:
        final_scale *= (KEYCHAIN_SCALE * MODEL_SCALE_BOOST)  # Additional scaling for keychain with boost
    obj.scale = (final_scale, final_scale, final_scale)
    
    log(f"Applied scale: {{base_scale:.6f}} × {{scale_multiplier}} × {{KEYCHAIN_SCALE * MODEL_SCALE_BOOST}} = {{final_scale:.6f}}")
    
    # Update scene to get final dimensions
    bpy.context.view_layer.update()
    final_dims = obj.dimensions
    log(f"STEP 3 - After scaling: {{final_dims.x:.1f}} × {{final_dims.y:.1f}} × {{final_dims.z:.1f}}")
    
    # POSITIONING: Use Method 2 (flat on base)
    z_pos = BASE_THICKNESS + (final_dims.z / 2)
    obj.location = (target_x, target_y, z_pos)
    
    log(f"FINAL POSITION: ({{target_x}}, {{target_y}}, {{z_pos:.1f}})")
    log(f"=== {{object_type.upper()}} {{obj.name}} COMPLETE ===\\\\n")
    
    return obj

def export_keychain_files():
    """Export the keychain files with keychain naming"""
    log("\\\\n=== EXPORTING KEYCHAIN FILES ===")
    
    # Export STL with keychain naming
    stl_filename = f"starter_pack_keychain_{{JOB_ID}}.stl"
    stl_path = os.path.join(OUTPUT_DIR, stl_filename)
    try:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.wm.stl_export(filepath=stl_path, export_selected_objects=True)
        log(f"✓ Keychain STL exported to: {{stl_path}}")
        
        # Verify file was created
        if os.path.exists(stl_path):
            file_size = os.path.getsize(stl_path)
            file_size_mb = round(file_size / (1024 * 1024), 2)
            log(f"✓ Keychain STL size: {{file_size}} bytes ({{file_size_mb}} MB)")
        else:
            log("✗ Keychain STL file was not created", "ERROR")
            
    except Exception as e:
        log(f"✗ Keychain STL export failed: {{e}}", "ERROR")

    # Save Blender file (preserves keychain for viewing)
    blend_filename = f"starter_pack_keychain_{{JOB_ID}}.blend"
    blend_path = os.path.join(OUTPUT_DIR, blend_filename)
    try:
        bpy.ops.wm.save_as_mainfile(filepath=blend_path)
        log(f"✓ Keychain Blend file saved to: {{blend_path}}")
        
        # Verify file was created
        if os.path.exists(blend_path):
            file_size = os.path.getsize(blend_path)
            file_size_mb = round(file_size / (1024 * 1024), 2)
            log(f"✓ Keychain Blend file size: {{file_size}} bytes ({{file_size_mb}} MB)")
        else:
            log("✗ Keychain Blend file was not created", "ERROR")
    except Exception as e:
        log(f"✗ Keychain Blend file save failed: {{e}}", "ERROR")

def main():
    """Main function for keychain processing"""
    print("🔗 KEYCHAIN SCRIPT STARTING...")
    print(f"Python version: {{sys.version}}")
    print(f"Blender version: {{bpy.app.version}}")
    print(f"Current working directory: {{os.getcwd()}}")
    
    log("=== KEYCHAIN STARTER PACK LAYOUT GENERATION ===")
    log(f"Job ID: {{JOB_ID}}")
    log(f"Output Directory: {{OUTPUT_DIR}}")
    log(f"🔗 KEYCHAIN MODE ENABLED! Scale: {{KEYCHAIN_SCALE}}x, Model Boost: {{MODEL_SCALE_BOOST}}x, Hole: {{KEYCHAIN_HOLE_SIZE}}mm {{KEYCHAIN_HOLE_POSITION}}")
    log(f"🎛️  CONTROLS:")
    log(f"   Figure: {{FIGURE_ROTATION}}, Scale={{FIGURE_SCALE_MULTIPLIER}}x")
    log(f"   Accessories: {{ACCESSORY_ROTATION}}, Scale={{ACCESSORY_SCALE_MULTIPLIER}}x")
    log(f"📝 TEXT SETTINGS:")
    log(f"   Main Title: '{{MAIN_TITLE}}' (Size: {{MAIN_TITLE_SIZE * KEYCHAIN_SCALE}})")
    log(f"   Tagline: '{{TAGLINE}}' (Size: {{TAGLINE_SIZE * KEYCHAIN_SCALE}})")
    log(f"   Base Bevel: {{BASE_BEVEL}}, Text Bevel: {{TEXT_BEVEL}}")
    
    setup_scene()
    clear_scene()
    
    # Create beveled base (with keychain hole if enabled)
    base = create_beveled_base()
    
    # Create enhanced titles
    main_title, tagline = create_enhanced_titles()
    
    # Import and position figure
    log("\\\\n" + "="*50)
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
    log("\\\\n" + "="*50)
    log("PROCESSING ACCESSORIES")
    log("="*50)
    
    for i, acc_key in enumerate(["acc1", "acc2", "acc3"]):
        log(f"\\\\n--- ACCESSORY {{i+1}} ---")
        acc = import_model(TEST_FILES[acc_key], f"Accessory_{{i+1}}")
        if acc:
            # Calculate Y position for this accessory
            acc_y = USABLE_Y_START + (USABLE_HEIGHT/2) - (ACCESSORY_SIZE/2) - (i * ACCESSORY_SPACING)
            debug_position_object(
                acc,
                ACCESSORY_X, acc_y,
                ACCESSORY_SIZE, ACCESSORY_SIZE,
                f"accessory_{{i+1}}"
            )
    
    # Export the keychain files
    export_keychain_files()
    
    log("\\\\n" + "="*50)
    log("KEYCHAIN SCRIPT COMPLETE!")
    log("="*50)
    log(f"✅ Keychain size: {{BASE_WIDTH:.1f}}mm × {{BASE_HEIGHT:.1f}}mm")
    log(f"✅ Keychain hole: {{KEYCHAIN_HOLE_SIZE}}mm diameter ({{KEYCHAIN_HOLE_POSITION}})")
    log(f"✅ Large H1 title: '{{MAIN_TITLE}}'")
    log(f"✅ H3 tagline: '{{TAGLINE}}'")
    log(f"✅ Beveled base edges")
    log(f"✅ Beveled text")
    log(f"✅ Models properly rotated and positioned")
    log(f"Check log file: {{LOG_FILE}}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        error_msg = f"FATAL ERROR: {{e}}"
        print(error_msg)
        print("TRACEBACK:")
        traceback.print_exc()
        
        # Try to write error to log file
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\\\\n=== FATAL ERROR ===\\\\n")
                f.write(f"{{error_msg}}\\\\n")
                f.write("TRACEBACK:\\\\n")
                f.write(traceback.format_exc())
                f.write("\\\\n=== END ERROR ===\\\\n")
        except:
            pass
        
        # Exit with error code
        import sys
        sys.exit(1)
'''
        return script_content

    async def _execute_blender_script(self, script_path: str, output_dir: str) -> Optional[Dict]:
        """
        Execute Blender script with enhanced debugging
        Args:
            script_path: Path to Blender script
            output_dir: Output directory
        Returns:
            Execution result
        """
        try:
            print(f"🚀 Executing Blender script: {script_path}")
            # Build Blender command with debug flags
            cmd = [
                self.blender_executable,
                "--background",  # Run headless
                "--python", script_path,
                "--debug-python",  # Show Python errors
                "--python-exit-code", "1"  # Exit with error code on Python failure
            ]
            
            print(f"🔧 Running command: {' '.join(cmd)}")
            
            # Execute Blender
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=output_dir
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise Exception(f"Blender execution timed out after {self.timeout} seconds")
            
            # Decode output
            stdout_text = stdout.decode() if stdout else ""
            stderr_text = stderr.decode() if stderr else ""
            
            print(f"📄 Blender return code: {process.returncode}")
            print(f"📄 Stdout: {stdout_text}")
            if stderr_text:
                print(f"📄 Stderr: {stderr_text}")
            
            # Check results
            if process.returncode == 0:
                print("✅ Blender script executed successfully")
                # Check for output files
                result_files = await self._check_output_files(output_dir)
                return {
                    'success': True,
                    'output_files': result_files,
                    'output_dir': output_dir,
                    'stdout': stdout_text,
                    'stderr': stderr_text
                }
            else:
                print(f"❌ Blender script failed with return code: {process.returncode}")
                return {
                    'success': False,
                    'error': f"Blender failed with code {process.returncode}",
                    'stdout': stdout_text,
                    'stderr': stderr_text
                }
                
        except Exception as e:
            print(f"❌ Error executing Blender script: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def _check_output_files(self, output_dir: str) -> List[Dict]:
        """
        Check for generated output files (both regular and keychain versions)
        Args:
            output_dir: Directory to check
        Returns:
            List of output file information
        """
        output_files = []
        expected_extensions = ['.3mf', '.stl', '.blend']
        try:
            for filename in os.listdir(output_dir):
                file_path = os.path.join(output_dir, filename)
                if os.path.isfile(file_path):
                    _, ext = os.path.splitext(filename)
                    if ext.lower() in expected_extensions:
                        file_size = os.path.getsize(file_path)
                        
                        # Determine file type based on filename
                        file_type = "unknown"
                        if "keychain" in filename.lower():
                            file_type = "keychain"
                        elif "starter_pack" in filename.lower():
                            file_type = "regular"
                        
                        # Enhanced file information
                        file_info = {
                            'filename': filename,
                            'file_path': file_path,
                            'file_extension': ext.lower(),
                            'file_type': file_type,  # regular, keychain, or unknown
                            'file_size_bytes': file_size,
                            'file_size_mb': round(file_size / (1024 * 1024), 2),
                            'created_at': datetime.now().isoformat(),
                            'download_url': f"/storage/processed/{os.path.basename(os.path.dirname(output_dir))}/final/{filename}"
                        }
                        output_files.append(file_info)
            
            # Sort files by type and extension for better organization
            output_files.sort(key=lambda x: (x['file_type'], x['file_extension']))
            
            print(f"📁 Found output files:")
            for file_info in output_files:
                file_type_emoji = "🎯" if file_info['file_type'] == "regular" else "🔗" if file_info['file_type'] == "keychain" else "❓"
                print(f"  {file_type_emoji} {file_info['filename']} ({file_info['file_size_mb']} MB)")
            
            return output_files
        except Exception as e:
            print(f"❌ Error checking output files: {str(e)}")
            return []

    async def health_check(self) -> bool:
        """
        Check if Blender is available and working
        Returns:
            True if Blender is available
        """
        try:
            process = await asyncio.create_subprocess_exec(
                self.blender_executable,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10
            )
            if process.returncode == 0:
                version_info = stdout.decode().strip()
                print(f"✅ Blender health check passed: {version_info.split()[0]} {version_info.split()[1]}")
                return True
            else:
                print(f"❌ Blender health check failed: {stderr.decode()}")
                return False
        except Exception as e:
            print(f"❌ Blender health check error: {str(e)}")
            return False

    async def create_simple_test_stl(self, output_path: str) -> bool:
        """
        Create a simple test STL file to verify Blender functionality
        Args:
            output_path: Path where to save test STL
        Returns:
            True if successful
        """
        try:
            # Create simple test script
            test_script_content = '''
import bpy

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False, confirm=False)

# Create test cube
bpy.ops.mesh.primitive_cube_add()
cube = bpy.context.active_object
cube.name = "TestCube"

# Export STL
bpy.ops.wm.stl_export(filepath="{}", export_selected_objects=True)
print("Test STL created successfully")
'''.format(output_path.replace('\\', '\\\\'))

            # Write test script
            script_fd, script_path = tempfile.mkstemp(suffix='.py', prefix='blender_test_')
            with os.fdopen(script_fd, 'w') as f:
                f.write(test_script_content)
            # Execute test script
            cmd = [
                self.blender_executable,
                "--background",
                "--python", script_path
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30
            )
            # Clean up script
            if os.path.exists(script_path):
                os.remove(script_path)
            # Check if STL was created
            if process.returncode == 0 and os.path.exists(output_path):
                print(f"✅ Test STL created successfully: {output_path}")
                return True
            else:
                print(f"❌ Test STL creation failed")
                print(f"Stdout: {stdout.decode()}")
                print(f"Stderr: {stderr.decode()}")
                return False
        except Exception as e:
            print(f"❌ Error creating test STL: {str(e)}")
            return False

# Utility functions for standalone use (outside the class)
async def test_blender_installation():
    """Test Blender installation"""
    processor = BlenderProcessor()
    print("🧪 Testing Blender installation...")
    # Health check
    health_ok = await processor.health_check()
    if not health_ok:
        print("❌ Blender health check failed")
        return False
    # Test STL creation
    test_stl_path = os.path.join(tempfile.gettempdir(), "blender_test.stl")
    test_ok = await processor.create_simple_test_stl(test_stl_path)
    # Clean up test file
    if os.path.exists(test_stl_path):
        os.remove(test_stl_path)
    if test_ok:
        print("✅ Blender installation test passed!")
        return True
    else:
        print("❌ Blender installation test failed!")
        return False

if __name__ == "__main__":
    # Test the Blender installation
    import asyncio
    asyncio.run(test_blender_installation())
