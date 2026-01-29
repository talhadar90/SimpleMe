"""
Hybrid Composer - Creates high-quality sticker prints by compositing
original 2D images onto positions from the layout JSON.
"""
import json
import os
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class HybridComposer:
    """Composes 2D images based on 3D layout positions for pixel-perfect output."""

    def __init__(self, dpi: int = 300):
        self.dpi = dpi
        self.mm_to_px = dpi / 25.4  # Convert mm to pixels

    def compose_card(
        self,
        job_dir: str,
        output_path: str,
        background_color: tuple = (0, 0, 0, 255),
        title: str = "Starter Pack",
        subtitle: str = "Everything You Need",
        accessory_scale: float = 1.2  # Scale accessories up slightly
    ) -> Dict:
        """
        Compose the card using original 2D images at layout positions.

        Args:
            job_dir: Path to the job directory (contains 'in' folder with layout and images)
            output_path: Path to save the output PNG
            background_color: RGBA background color
            title: Title text
            subtitle: Subtitle text

        Returns:
            Dict with success status and output info
        """
        try:
            in_dir = os.path.join(job_dir, "in")
            layout_path = os.path.join(in_dir, "card_layout.json")

            # Load layout
            with open(layout_path, 'r') as f:
                layout = json.load(f)

            # Get card dimensions
            card_info = next((item for item in layout['items'] if item['name'] == 'Card'), None)
            if not card_info:
                return {"success": False, "error": "Card info not found in layout"}

            card_w_mm = card_info['size']['w']
            card_h_mm = card_info['size']['h']

            # Convert to pixels
            card_w_px = int(card_w_mm * self.mm_to_px)
            card_h_px = int(card_h_mm * self.mm_to_px)

            logger.info(f"Creating canvas: {card_w_px}x{card_h_px} pixels ({card_w_mm}x{card_h_mm}mm at {self.dpi} DPI)")

            # Create canvas
            canvas = Image.new('RGBA', (card_w_px, card_h_px), background_color)

            # Process each item
            for item in layout['items']:
                name = item['name']

                # Skip Card and TextGroup
                if name in ['Card', 'TextGroup']:
                    continue

                # Find the corresponding image
                image_path = os.path.join(in_dir, f"{name}_r2d.png")
                if not os.path.exists(image_path):
                    logger.warning(f"Image not found: {image_path}")
                    continue

                # Load image
                img = Image.open(image_path).convert('RGBA')

                # Get target size in pixels
                target_w_mm = item['size']['w']
                target_h_mm = item['size']['h']

                # Apply scale factor for accessories
                if name.startswith('accessory'):
                    target_w_mm *= accessory_scale
                    target_h_mm *= accessory_scale

                target_w_px = int(target_w_mm * self.mm_to_px)
                target_h_px = int(target_h_mm * self.mm_to_px)

                # Resize image maintaining aspect ratio
                img_ratio = img.width / img.height
                target_ratio = target_w_px / target_h_px

                if img_ratio > target_ratio:
                    # Image is wider - fit to width
                    new_w = target_w_px
                    new_h = int(target_w_px / img_ratio)
                else:
                    # Image is taller - fit to height
                    new_h = target_h_px
                    new_w = int(target_h_px * img_ratio)

                img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                # Calculate position (convert from center-origin to top-left origin)
                center_x_mm = item['center']['x']
                center_y_mm = item['center']['y']

                # Convert to pixel coordinates (origin at center of canvas)
                center_x_px = int((card_w_mm / 2 + center_x_mm) * self.mm_to_px)
                center_y_px = int((card_h_mm / 2 - center_y_mm) * self.mm_to_px)  # Flip Y axis

                # Calculate top-left corner for pasting
                paste_x = center_x_px - new_w // 2
                paste_y = center_y_px - new_h // 2

                # Ensure image stays within canvas bounds
                if paste_x < 0:
                    paste_x = 5
                if paste_y < 0:
                    paste_y = 5
                if paste_x + new_w > card_w_px:
                    paste_x = card_w_px - new_w - 5
                if paste_y + new_h > card_h_px:
                    paste_y = card_h_px - new_h - 5

                logger.info(f"Placing {name}: size={new_w}x{new_h}px, pos=({paste_x}, {paste_y})")

                # Paste image
                canvas.paste(img_resized, (paste_x, paste_y), img_resized)

            # Add text
            self._add_text(canvas, title, subtitle, card_w_px, card_h_px)

            # Save output
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            canvas.save(output_path, 'PNG', dpi=(self.dpi, self.dpi))

            file_size = os.path.getsize(output_path)
            logger.info(f"Saved hybrid composition: {output_path} ({file_size / 1024 / 1024:.2f} MB)")

            return {
                "success": True,
                "output_path": output_path,
                "dimensions": {"width": card_w_px, "height": card_h_px},
                "dpi": self.dpi,
                "file_size_bytes": file_size
            }

        except Exception as e:
            logger.error(f"Hybrid composition failed: {e}")
            return {"success": False, "error": str(e)}

    def _add_text(self, canvas: Image.Image, title: str, subtitle: str, width: int, height: int):
        """Add title and subtitle text to the canvas."""
        draw = ImageDraw.Draw(canvas)

        # Large font sizes to match 3D render
        title_size = int(width * 0.08)  # 8% of width
        subtitle_size = int(width * 0.05)  # 5% of width

        try:
            # Try common font paths
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            ]
            title_font = None
            subtitle_font = None
            for fp in font_paths:
                if os.path.exists(fp):
                    title_font = ImageFont.truetype(fp, title_size)
                    # Try regular version for subtitle
                    regular_fp = fp.replace("Bold", "Regular").replace("-Bold", "")
                    if os.path.exists(regular_fp):
                        subtitle_font = ImageFont.truetype(regular_fp, subtitle_size)
                    else:
                        subtitle_font = ImageFont.truetype(fp, subtitle_size)
                    break

            if title_font is None:
                title_font = ImageFont.load_default()
                subtitle_font = ImageFont.load_default()
        except Exception as e:
            logger.warning(f"Font loading failed: {e}")
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()

        # Calculate text positions (top area of card)
        text_y_start = int(height * 0.03)  # 3% from top

        # Title - white/light gray with slight shadow effect
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_w = title_bbox[2] - title_bbox[0]
        title_h = title_bbox[3] - title_bbox[1]
        title_x = (width - title_w) // 2

        # Draw shadow
        draw.text((title_x + 2, text_y_start + 2), title, fill=(50, 50, 50, 200), font=title_font)
        # Draw main text
        draw.text((title_x, text_y_start), title, fill=(220, 220, 220, 255), font=title_font)

        # Subtitle
        subtitle_y = text_y_start + title_h + int(height * 0.015)
        subtitle_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
        subtitle_w = subtitle_bbox[2] - subtitle_bbox[0]
        subtitle_x = (width - subtitle_w) // 2

        # Draw shadow
        draw.text((subtitle_x + 1, subtitle_y + 1), subtitle, fill=(50, 50, 50, 180), font=subtitle_font)
        # Draw main text
        draw.text((subtitle_x, subtitle_y), subtitle, fill=(200, 200, 200, 255), font=subtitle_font)


def compose_job(job_id: str, jobs_dir: str = "/workspace/SimpleMe/sticker_maker/jobs") -> Dict:
    """
    Convenience function to compose a job's card.

    Args:
        job_id: The job ID
        jobs_dir: Base directory for jobs

    Returns:
        Dict with success status and output info
    """
    composer = HybridComposer(dpi=300)
    job_dir = os.path.join(jobs_dir, job_id)
    output_path = os.path.join(job_dir, "out", "card_hybrid.png")

    return composer.compose_card(job_dir, output_path)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        job_id = sys.argv[1]
    else:
        job_id = "31cf7d2c-31e0-4749-b219-0dd7821d621a"

    result = compose_job(job_id)
    print(f"Result: {result}")
