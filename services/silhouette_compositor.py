"""
Silhouette Compositor - Creates stickers by masking 2D images with 3D model silhouettes.
This ensures the sticker shape matches the 3D printed STL exactly.
"""
import subprocess
import json
import os
from PIL import Image
import numpy as np
from typing import Dict, Optional
import logging
import tempfile

logger = logging.getLogger(__name__)

# Blender script to render silhouettes
BLENDER_SILHOUETTE_SCRIPT = '''
import bpy
import sys
import math
from mathutils import Vector

def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)

def setup_scene():
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 1
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100

def create_white_material():
    mat = bpy.data.materials.new(name="White")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (1, 1, 1, 1)
    emission.inputs['Strength'].default_value = 1.0
    output = nodes.new('ShaderNodeOutputMaterial')
    mat.node_tree.links.new(emission.outputs['Emission'], output.inputs['Surface'])
    return mat

def render_silhouette(glb_path, output_path):
    clear_scene()
    setup_scene()

    bpy.ops.import_scene.gltf(filepath=glb_path)

    mat = create_white_material()
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            obj.data.materials.clear()
            obj.data.materials.append(mat)

    # Get all mesh bounds
    all_bbox = []
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            all_bbox.extend([obj.matrix_world @ Vector(corner) for corner in obj.bound_box])

    if not all_bbox:
        print("No meshes found")
        return False

    min_x = min(v.x for v in all_bbox)
    max_x = max(v.x for v in all_bbox)
    min_y = min(v.y for v in all_bbox)
    max_y = max(v.y for v in all_bbox)
    min_z = min(v.z for v in all_bbox)
    max_z = max(v.z for v in all_bbox)

    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    center_z = (min_z + max_z) / 2

    width = max_x - min_x
    height = max_z - min_z

    # Camera from front (looking along +Y axis)
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = max(width, height) * 1.15

    cam_obj = bpy.data.objects.new("Cam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.location = (center_x, min_y - 5, center_z)
    cam_obj.rotation_euler = (math.radians(90), 0, 0)
    bpy.context.scene.camera = cam_obj

    # Adjust resolution to match aspect ratio
    aspect = width / height if height > 0 else 1.0
    if aspect > 1:
        bpy.context.scene.render.resolution_x = 1024
        bpy.context.scene.render.resolution_y = int(1024 / aspect)
    else:
        bpy.context.scene.render.resolution_x = int(1024 * aspect)
        bpy.context.scene.render.resolution_y = 1024

    bpy.context.scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)
    print(f"Rendered: {output_path}")
    return True

if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    success = render_silhouette(args[0], args[1])
    sys.exit(0 if success else 1)
'''


class SilhouetteCompositor:
    """Creates stickers by masking 2D images with 3D model silhouettes."""

    def __init__(self, blender_executable: str = "blender", dpi: int = 300):
        self.blender_executable = blender_executable
        self.dpi = dpi
        self.mm_to_px = dpi / 25.4

    def render_silhouette(self, glb_path: str, output_path: str) -> bool:
        """Render a 3D model as a white silhouette using Blender."""

        # Write the Blender script to a temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(BLENDER_SILHOUETTE_SCRIPT)
            script_path = f.name

        try:
            cmd = [
                self.blender_executable,
                "--background",
                "--python", script_path,
                "--",
                glb_path,
                output_path
            ]

            logger.info(f"Rendering silhouette: {os.path.basename(glb_path)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode != 0:
                logger.error(f"Blender failed: {result.stderr}")
                return False

            return os.path.exists(output_path)

        except subprocess.TimeoutExpired:
            logger.error("Blender timed out")
            return False
        except Exception as e:
            logger.error(f"Error rendering silhouette: {e}")
            return False
        finally:
            os.unlink(script_path)

    def apply_mask_to_image(self, image_path: str, mask_path: str, output_path: str) -> bool:
        """Apply silhouette mask to original 2D image."""
        try:
            # Load original image
            original = Image.open(image_path).convert('RGBA')

            # Load mask
            mask = Image.open(mask_path).convert('RGBA')

            # Resize mask to match original if needed
            if mask.size != original.size:
                # Resize original to mask size (mask is the target shape)
                # But we want to fit the original content into the mask shape

                # Get mask bounds (non-transparent area)
                mask_array = np.array(mask)
                alpha = mask_array[:, :, 3]
                rows = np.any(alpha > 0, axis=1)
                cols = np.any(alpha > 0, axis=0)

                if not np.any(rows) or not np.any(cols):
                    logger.warning("Mask is empty")
                    return False

                y_min, y_max = np.where(rows)[0][[0, -1]]
                x_min, x_max = np.where(cols)[0][[0, -1]]

                mask_content_w = x_max - x_min
                mask_content_h = y_max - y_min

                # Resize original to fit mask content area
                original_resized = original.resize((mask_content_w, mask_content_h), Image.Resampling.LANCZOS)

                # Create new image same size as mask
                result = Image.new('RGBA', mask.size, (0, 0, 0, 0))

                # Paste resized original at mask content position
                result.paste(original_resized, (x_min, y_min))

                # Apply mask
                result_array = np.array(result)
                result_array[:, :, 3] = np.minimum(result_array[:, :, 3], alpha)
                result = Image.fromarray(result_array)
            else:
                # Same size - just apply mask
                original_array = np.array(original)
                mask_array = np.array(mask)
                original_array[:, :, 3] = np.minimum(original_array[:, :, 3], mask_array[:, :, 3])
                result = Image.fromarray(original_array)

            result.save(output_path, 'PNG')
            logger.info(f"Created masked image: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error applying mask: {e}")
            return False

    def compose_card(
        self,
        job_dir: str,
        output_path: str,
        background_color: tuple = (0, 0, 0, 255),
        title: str = "Starter Pack",
        subtitle: str = "Everything You Need"
    ) -> Dict:
        """
        Create card by masking 2D images with 3D silhouettes.
        """
        try:
            in_dir = os.path.join(job_dir, "in")
            out_dir = os.path.join(job_dir, "out")
            masks_dir = os.path.join(out_dir, "masks")
            os.makedirs(masks_dir, exist_ok=True)

            layout_path = os.path.join(in_dir, "card_layout.json")

            # Load layout
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
                mask_path = os.path.join(masks_dir, f"{name}_mask.png")
                masked_path = os.path.join(masks_dir, f"{name}_masked.png")

                if not os.path.exists(glb_path):
                    logger.warning(f"GLB not found: {glb_path}")
                    continue

                if not os.path.exists(image_path):
                    logger.warning(f"Image not found: {image_path}")
                    continue

                # Render silhouette
                if not self.render_silhouette(glb_path, mask_path):
                    logger.warning(f"Failed to render silhouette for {name}")
                    continue

                # Apply mask to original image
                if not self.apply_mask_to_image(image_path, mask_path, masked_path):
                    logger.warning(f"Failed to apply mask for {name}")
                    continue

                # Load masked image
                masked_img = Image.open(masked_path).convert('RGBA')

                # Calculate target size and position
                target_w_mm = item['size']['w']
                target_h_mm = item['size']['h']
                target_w_px = int(target_w_mm * self.mm_to_px)
                target_h_px = int(target_h_mm * self.mm_to_px)

                # Resize masked image to target size
                masked_resized = masked_img.resize((target_w_px, target_h_px), Image.Resampling.LANCZOS)

                # Calculate position
                center_x_mm = item['center']['x']
                center_y_mm = item['center']['y']
                center_x_px = int((card_w_mm / 2 + center_x_mm) * self.mm_to_px)
                center_y_px = int((card_h_mm / 2 - center_y_mm) * self.mm_to_px)

                paste_x = center_x_px - target_w_px // 2
                paste_y = center_y_px - target_h_px // 2

                logger.info(f"Placing {name}: {target_w_px}x{target_h_px}px at ({paste_x}, {paste_y})")

                # Paste onto canvas
                canvas.paste(masked_resized, (paste_x, paste_y), masked_resized)

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

    def _add_text(self, canvas: Image.Image, title: str, subtitle: str, width: int, height: int):
        """Add title and subtitle text."""
        from PIL import ImageDraw, ImageFont

        draw = ImageDraw.Draw(canvas)
        title_size = int(width * 0.08)
        subtitle_size = int(width * 0.05)

        try:
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            ]
            title_font = None
            for fp in font_paths:
                if os.path.exists(fp):
                    title_font = ImageFont.truetype(fp, title_size)
                    subtitle_font = ImageFont.truetype(fp, subtitle_size)
                    break
            if title_font is None:
                title_font = ImageFont.load_default()
                subtitle_font = ImageFont.load_default()
        except:
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()

        text_y = int(height * 0.03)

        # Title
        bbox = draw.textbbox((0, 0), title, font=title_font)
        title_w = bbox[2] - bbox[0]
        title_h = bbox[3] - bbox[1]
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


def compose_with_silhouettes(job_id: str, jobs_dir: str = "/workspace/SimpleMe/sticker_maker/jobs") -> Dict:
    """Convenience function to compose a job using silhouette masks."""
    compositor = SilhouetteCompositor(dpi=300)
    job_dir = os.path.join(jobs_dir, job_id)
    output_path = os.path.join(job_dir, "out", "card_silhouette.png")

    return compositor.compose_card(job_dir, output_path)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    job_id = sys.argv[1] if len(sys.argv) > 1 else "31cf7d2c-31e0-4749-b219-0dd7821d621a"
    result = compose_with_silhouettes(job_id)
    print(f"Result: {result}")
