"""
UV Projector - Projects 2D images onto 3D models from camera view.
This gives us: 3D model shape + 2D image quality = perfect alignment.
"""
import subprocess
import json
import os
import tempfile
import logging
from typing import Dict
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)

BLENDER_UV_PROJECT_SCRIPT = '''
import bpy
import sys
import math
import os
from mathutils import Vector

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for img in bpy.data.images:
        if img.users == 0:
            bpy.data.images.remove(img)
    for mat in bpy.data.materials:
        if mat.users == 0:
            bpy.data.materials.remove(mat)

def setup_scene():
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 32  # Good quality
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'

def create_projected_material(image_path, content_bounds=None):
    """Create emission material that projects image from camera view onto object."""
    mat = bpy.data.materials.new(name="ProjectedTexture")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # Load image
    img = bpy.data.images.load(image_path)

    # Create nodes
    output = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = 1.0

    tex_image = nodes.new('ShaderNodeTexImage')
    tex_image.image = img
    tex_image.extension = 'EXTEND'  # Extend edge pixels beyond bounds

    tex_coord = nodes.new('ShaderNodeTexCoord')

    if content_bounds:
        # Map Window coords to content region of image
        left, bottom, right, top = content_bounds

        # Small padding (2%) to slightly overfill edges
        padding = 0.02
        width_pad = (right - left) * padding
        height_pad = (top - bottom) * padding
        left += width_pad
        right -= width_pad
        bottom += height_pad
        top -= height_pad

        scale_x = right - left
        scale_y = top - bottom

        # Add mapping node to transform coordinates
        mapping = nodes.new('ShaderNodeMapping')
        mapping.inputs['Location'].default_value = (left, bottom, 0)
        mapping.inputs['Scale'].default_value = (scale_x, scale_y, 1)

        links.new(tex_coord.outputs['Window'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], tex_image.inputs['Vector'])
    else:
        links.new(tex_coord.outputs['Window'], tex_image.inputs['Vector'])

    links.new(tex_image.outputs['Color'], emission.inputs['Color'])
    links.new(emission.outputs['Emission'], output.inputs['Surface'])

    mat.blend_method = 'CLIP'

    return mat

def setup_camera_and_get_bounds(meshes):
    """Setup orthographic camera looking at meshes from front."""
    all_bbox = []
    for obj in meshes:
        all_bbox.extend([obj.matrix_world @ Vector(corner) for corner in obj.bound_box])

    if not all_bbox:
        return None, None

    min_x = min(v.x for v in all_bbox)
    max_x = max(v.x for v in all_bbox)
    min_y = min(v.y for v in all_bbox)
    max_y = max(v.y for v in all_bbox)
    min_z = min(v.z for v in all_bbox)
    max_z = max(v.z for v in all_bbox)

    center_x = (min_x + max_x) / 2
    center_z = (min_z + max_z) / 2

    width = max_x - min_x
    height = max_z - min_z

    # Create orthographic camera
    cam_data = bpy.data.cameras.new("ProjectionCam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = max(width, height) * 1.05  # Small padding

    cam_obj = bpy.data.objects.new("ProjectionCam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)

    # Position camera in front
    cam_obj.location = (center_x, min_y - 10, center_z)
    cam_obj.rotation_euler = (math.radians(90), 0, 0)

    bpy.context.scene.camera = cam_obj

    return cam_obj, {'width': width, 'height': height, 'center_x': center_x, 'center_z': center_z}

def project_and_render(glb_path, image_path, output_path, resolution=1024, content_bounds=None):
    """Project 2D image onto 3D model and render."""
    clear_scene()
    setup_scene()

    # Load 2D image to get its dimensions
    ref_img = bpy.data.images.load(image_path)
    img_w, img_h = ref_img.size
    img_aspect = img_w / img_h
    print(f"Image: {img_w}x{img_h}, aspect={img_aspect:.3f}")

    # Import GLB
    bpy.ops.import_scene.gltf(filepath=glb_path)

    # Get all mesh objects
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    if not meshes:
        print("No meshes found")
        return False

    # Get model bounds
    all_bbox = []
    for obj in meshes:
        all_bbox.extend([obj.matrix_world @ Vector(corner) for corner in obj.bound_box])

    min_x = min(v.x for v in all_bbox)
    max_x = max(v.x for v in all_bbox)
    min_y = min(v.y for v in all_bbox)
    min_z = min(v.z for v in all_bbox)
    max_z = max(v.z for v in all_bbox)

    center_x = (min_x + max_x) / 2
    center_z = (min_z + max_z) / 2
    width = max_x - min_x
    height = max_z - min_z
    model_aspect = width / height if height > 0 else 1.0
    print(f"Model: w={width:.3f}, h={height:.3f}, aspect={model_aspect:.3f}")

    # Create orthographic camera
    cam_data = bpy.data.cameras.new("ProjectionCam")
    cam_data.type = 'ORTHO'

    # Set ortho_scale to EXACTLY frame the 3D model (no padding)
    # This ensures 2D content stretches to fill entire model
    cam_data.ortho_scale = height  # Vertical size = model height
    print(f"Ortho scale: {cam_data.ortho_scale:.3f}")

    cam_obj = bpy.data.objects.new("ProjectionCam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.location = (center_x, min_y - 10, center_z)
    cam_obj.rotation_euler = (math.radians(90), 0, 0)
    bpy.context.scene.camera = cam_obj

    # Set render resolution to exactly match model aspect ratio
    # This ensures the model fills the entire frame
    bpy.context.scene.render.resolution_x = int(resolution * model_aspect)
    bpy.context.scene.render.resolution_y = resolution

    # Content bounds passed as arguments (calculated outside Blender)
    if content_bounds:
        print(f"Content bounds: left={content_bounds[0]:.3f}, bottom={content_bounds[1]:.3f}, right={content_bounds[2]:.3f}, top={content_bounds[3]:.3f}")

    # Create and apply projected material with content mapping
    mat = create_projected_material(image_path, content_bounds)
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(mat)

    # Render
    bpy.context.scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)

    print(f"Rendered: {output_path}")
    print(f"Resolution: {bpy.context.scene.render.resolution_x}x{bpy.context.scene.render.resolution_y}")
    return True

if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    glb_path = args[0]
    image_path = args[1]
    output_path = args[2]
    resolution = int(args[3]) if len(args) > 3 else 1024
    # Content bounds: left,bottom,right,top (fractions 0-1)
    if len(args) > 4:
        bounds = [float(x) for x in args[4].split(',')]
        content_bounds = tuple(bounds)
    else:
        content_bounds = None

    success = project_and_render(glb_path, image_path, output_path, resolution, content_bounds)
    sys.exit(0 if success else 1)
'''


class UVProjector:
    """Projects 2D images onto 3D models for perfect sticker alignment."""

    def __init__(self, blender_executable: str = "blender", dpi: int = 300):
        self.blender_executable = blender_executable
        self.dpi = dpi
        self.mm_to_px = dpi / 25.4

    def get_content_bounds(self, image_path: str) -> str:
        """Find non-transparent content bounds, return as comma-separated string."""
        import numpy as np

        img = Image.open(image_path).convert('RGBA')
        arr = np.array(img)
        alpha = arr[:, :, 3]

        rows = np.any(alpha > 10, axis=1)
        cols = np.any(alpha > 10, axis=0)

        if not np.any(rows) or not np.any(cols):
            return "0.0,0.0,1.0,1.0"

        y_min, y_max = np.where(rows)[0][[0, -1]]
        x_min, x_max = np.where(cols)[0][[0, -1]]

        # Return as fractions (0-1) of image size
        # Y is flipped for UV coords (0=bottom, 1=top)
        left = x_min / img.width
        bottom = 1.0 - y_max / img.height
        right = x_max / img.width
        top = 1.0 - y_min / img.height

        return f"{left:.4f},{bottom:.4f},{right:.4f},{top:.4f}"

    def project_texture(self, glb_path: str, image_path: str, output_path: str, resolution: int = 1024) -> bool:
        """Project 2D image onto 3D model and render."""

        # Calculate content bounds using PIL (outside Blender)
        content_bounds = self.get_content_bounds(image_path)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(BLENDER_UV_PROJECT_SCRIPT)
            script_path = f.name

        try:
            cmd = [
                self.blender_executable,
                "--background",
                "--python", script_path,
                "--",
                glb_path,
                image_path,
                output_path,
                str(resolution),
                content_bounds  # Pass bounds to Blender
            ]

            logger.info(f"Projecting texture onto: {os.path.basename(glb_path)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

            if result.returncode != 0:
                logger.error(f"Blender failed: {result.stderr[-500:]}")
                return False

            return os.path.exists(output_path)

        except Exception as e:
            logger.error(f"Error: {e}")
            return False
        finally:
            os.unlink(script_path)

    def compose_card(
        self,
        job_dir: str,
        output_path: str,
        background_color: tuple = (0, 0, 0, 255),
        title: str = "Starter Pack",
        subtitle: str = "Everything You Need"
    ) -> Dict:
        """Create card by projecting 2D textures onto 3D models."""
        try:
            in_dir = os.path.join(job_dir, "in")
            out_dir = os.path.join(job_dir, "out")
            projected_dir = os.path.join(out_dir, "projected")
            os.makedirs(projected_dir, exist_ok=True)

            layout_path = os.path.join(in_dir, "card_layout.json")

            with open(layout_path, 'r') as f:
                layout = json.load(f)

            # Get card dimensions
            card_info = next((item for item in layout['items'] if item['name'] == 'Card'), None)
            if not card_info:
                return {"success": False, "error": "Card info not found"}

            card_w_mm = card_info['size']['w']
            card_h_mm = card_info['size']['h']
            card_w_px = int(card_w_mm * self.mm_to_px)
            card_h_px = int(card_h_mm * self.mm_to_px)

            logger.info(f"Card: {card_w_px}x{card_h_px}px ({card_w_mm}x{card_h_mm}mm)")

            # Create canvas
            canvas = Image.new('RGBA', (card_w_px, card_h_px), background_color)

            # Process each item
            for item in layout['items']:
                name = item['name']
                if name in ['Card', 'TextGroup']:
                    continue

                glb_path = os.path.join(in_dir, f"{name}_3d.glb")
                image_path = os.path.join(in_dir, f"{name}_r2d.png")
                projected_path = os.path.join(projected_dir, f"{name}_projected.png")

                if not os.path.exists(glb_path) or not os.path.exists(image_path):
                    logger.warning(f"Missing files for {name}")
                    continue

                # Project texture onto 3D model
                if not self.project_texture(glb_path, image_path, projected_path, resolution=1024):
                    logger.warning(f"Failed to project texture for {name}")
                    continue

                # Load projected image
                projected_img = Image.open(projected_path).convert('RGBA')

                # Calculate target size from layout
                target_w_mm = item['size']['w']
                target_h_mm = item['size']['h']
                target_w_px = int(target_w_mm * self.mm_to_px)
                target_h_px = int(target_h_mm * self.mm_to_px)

                # Resize projected image to target size
                projected_resized = projected_img.resize((target_w_px, target_h_px), Image.Resampling.LANCZOS)

                # Calculate position
                center_x_mm = item['center']['x']
                center_y_mm = item['center']['y']
                center_x_px = int((card_w_mm / 2 + center_x_mm) * self.mm_to_px)
                center_y_px = int((card_h_mm / 2 - center_y_mm) * self.mm_to_px)

                paste_x = center_x_px - target_w_px // 2
                paste_y = center_y_px - target_h_px // 2

                logger.info(f"Placing {name}: {target_w_px}x{target_h_px}px at ({paste_x}, {paste_y})")

                canvas.paste(projected_resized, (paste_x, paste_y), projected_resized)

            # Add text
            self._add_text(canvas, title, subtitle, card_w_px, card_h_px)

            # Save
            canvas.save(output_path, 'PNG', dpi=(self.dpi, self.dpi))

            return {
                "success": True,
                "output_path": output_path,
                "dimensions": {"width": card_w_px, "height": card_h_px}
            }

        except Exception as e:
            logger.error(f"Composition failed: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def _add_text(self, canvas, title, subtitle, width, height):
        """Add title and subtitle."""
        from PIL import ImageDraw, ImageFont

        draw = ImageDraw.Draw(canvas)
        title_size = int(width * 0.08)
        subtitle_size = int(width * 0.05)

        try:
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            ]
            title_font = subtitle_font = None
            for fp in font_paths:
                if os.path.exists(fp):
                    title_font = ImageFont.truetype(fp, title_size)
                    subtitle_font = ImageFont.truetype(fp, subtitle_size)
                    break
            if not title_font:
                title_font = ImageFont.load_default()
                subtitle_font = ImageFont.load_default()
        except:
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()

        text_y = int(height * 0.03)

        # Title with shadow
        bbox = draw.textbbox((0, 0), title, font=title_font)
        title_w, title_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        title_x = (width - title_w) // 2
        draw.text((title_x + 2, text_y + 2), title, fill=(50, 50, 50, 200), font=title_font)
        draw.text((title_x, text_y), title, fill=(220, 220, 220, 255), font=title_font)

        # Subtitle
        subtitle_y = text_y + title_h + int(height * 0.015)
        bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
        subtitle_w = bbox[2] - bbox[0]
        subtitle_x = (width - subtitle_w) // 2
        draw.text((subtitle_x + 1, subtitle_y + 1), subtitle, fill=(50, 50, 50, 180), font=subtitle_font)
        draw.text((subtitle_x, subtitle_y), subtitle, fill=(200, 200, 200, 255), font=subtitle_font)


def project_job(job_id: str, jobs_dir: str = "/workspace/SimpleMe/sticker_maker/jobs") -> Dict:
    """Project textures for a job."""
    projector = UVProjector(dpi=300)
    job_dir = os.path.join(jobs_dir, job_id)
    output_path = os.path.join(job_dir, "out", "card_projected.png")
    return projector.compose_card(job_dir, output_path)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    job_id = sys.argv[1] if len(sys.argv) > 1 else "31cf7d2c-31e0-4749-b219-0dd7821d621a"
    result = project_job(job_id)
    print(f"Result: {result}")
