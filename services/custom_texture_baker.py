"""
Custom Texture Baker - Uses Hunyuan3D's renderer to bake 2D images onto 3D model UVs.
This gives us high-quality textures that follow the exact 3D model shape.
"""
import sys
import os

# Add Hunyuan3D to path
sys.path.insert(0, '/workspace/Hunyuan3D-2.1')

import torch
import numpy as np
from PIL import Image
import trimesh
import logging

logger = logging.getLogger(__name__)


def bake_texture_from_image(
    glb_path: str,
    image_path: str,
    output_path: str,
    texture_size: int = 2048,
    camera_elev: float = 0,
    camera_azim: float = 0
) -> bool:
    """
    Bake a 2D image directly onto a 3D model's UV texture space.

    Args:
        glb_path: Path to input GLB/OBJ file
        image_path: Path to 2D image to bake as texture
        output_path: Path for output textured GLB
        texture_size: Resolution of baked texture (default 2048)
        camera_elev: Camera elevation angle (0 = front view)
        camera_azim: Camera azimuth angle (0 = front view)

    Returns:
        True if successful
    """
    try:
        from hy3dpaint.DifferentiableRenderer.MeshRender import MeshRender
        from hy3dpaint.convert_utils import create_glb_with_pbr_materials

        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f"Using device: {device}")

        # Load mesh with trimesh
        logger.info(f"Loading mesh: {glb_path}")
        mesh = trimesh.load(glb_path)

        # Handle scene vs single mesh
        if isinstance(mesh, trimesh.Scene):
            meshes = [g for g in mesh.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if meshes:
                mesh = trimesh.util.concatenate(meshes)
            else:
                logger.error("No valid meshes in scene")
                return False

        # Initialize Hunyuan renderer
        logger.info("Initializing renderer...")
        render = MeshRender(
            texture_size=texture_size,
            default_resolution=1024,
            device=device
        )

        # Load mesh into renderer (expects trimesh object)
        render.load_mesh(mesh)

        # Load 2D image
        logger.info(f"Loading image: {image_path}")
        image = Image.open(image_path).convert('RGB')

        # Resize image to match render resolution if needed
        render_size = render.default_resolution[0]  # Get resolution (height, width)
        if image.size != (render_size, render_size):
            # Pad/resize to square while maintaining aspect ratio
            image = _pad_to_square(image, render_size)

        # Back-project image onto UV texture space
        logger.info(f"Baking texture from camera angle: elev={camera_elev}, azim={camera_azim}")
        texture, cos_map, boundary_map = render.back_project(
            image,
            elev=camera_elev,
            azim=camera_azim
        )

        # Convert texture to numpy
        texture_np = (texture.cpu().numpy() * 255).astype(np.uint8)

        # Handle areas not covered by projection (inpaint)
        mask = (cos_map.cpu().numpy().squeeze() > 1e-8)
        if not mask.all():
            logger.info("Inpainting uncovered regions...")
            texture_np = render.uv_inpaint(
                torch.tensor(texture_np).float() / 255,
                mask
            )
            texture_np = (texture_np * 255).astype(np.uint8)

        # Save texture as PNG
        texture_img = Image.fromarray(texture_np)
        temp_texture_path = output_path.replace('.glb', '_albedo.png')
        texture_img.save(temp_texture_path)
        logger.info(f"Saved texture: {temp_texture_path}")

        # Export mesh with new texture
        # First export as OBJ
        temp_obj = output_path.replace('.glb', '_temp.obj')
        mesh.export(temp_obj)

        # Create GLB with PBR materials
        create_glb_with_pbr_materials(
            temp_obj,
            {'albedo': temp_texture_path},
            output_path
        )

        # Cleanup temp files
        if os.path.exists(temp_obj):
            os.remove(temp_obj)
        if os.path.exists(temp_obj.replace('.obj', '.mtl')):
            os.remove(temp_obj.replace('.obj', '.mtl'))

        logger.info(f"Saved textured model: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Texture baking failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def _pad_to_square(image: Image.Image, size: int) -> Image.Image:
    """Pad image to square while centering content."""
    w, h = image.size

    # Create square canvas
    square = Image.new('RGB', (size, size), (0, 0, 0))

    # Calculate scale to fit
    scale = min(size / w, size / h)
    new_w = int(w * scale)
    new_h = int(h * scale)

    # Resize image
    resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Center on canvas
    x = (size - new_w) // 2
    y = (size - new_h) // 2
    square.paste(resized, (x, y))

    return square


def _generate_front_uvs(mesh: trimesh.Trimesh) -> np.ndarray:
    """Generate UVs by projecting from front view."""
    vertices = mesh.vertices

    # Project to XZ plane (front view)
    x = vertices[:, 0]
    z = vertices[:, 2]

    # Normalize to 0-1 range
    x_min, x_max = x.min(), x.max()
    z_min, z_max = z.min(), z.max()

    u = (x - x_min) / (x_max - x_min) if x_max > x_min else np.zeros_like(x)
    v = (z - z_min) / (z_max - z_min) if z_max > z_min else np.zeros_like(z)

    return np.column_stack([u, v])


class CustomTextureBaker:
    """Service class for baking textures onto 3D models."""

    def __init__(self, texture_size: int = 2048):
        self.texture_size = texture_size

    def bake(
        self,
        glb_path: str,
        image_path: str,
        output_path: str,
        camera_elev: float = 0,
        camera_azim: float = 0
    ) -> bool:
        """Bake texture from 2D image onto 3D model."""
        return bake_texture_from_image(
            glb_path=glb_path,
            image_path=image_path,
            output_path=output_path,
            texture_size=self.texture_size,
            camera_elev=camera_elev,
            camera_azim=camera_azim
        )


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Bake 2D texture onto 3D model")
    parser.add_argument("glb_path", help="Path to input GLB/OBJ")
    parser.add_argument("image_path", help="Path to 2D image")
    parser.add_argument("output_path", help="Path for output GLB")
    parser.add_argument("--texture-size", type=int, default=2048)
    parser.add_argument("--elev", type=float, default=0, help="Camera elevation")
    parser.add_argument("--azim", type=float, default=0, help="Camera azimuth")

    args = parser.parse_args()

    success = bake_texture_from_image(
        args.glb_path,
        args.image_path,
        args.output_path,
        args.texture_size,
        args.elev,
        args.azim
    )

    sys.exit(0 if success else 1)
