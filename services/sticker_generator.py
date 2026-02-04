"""
Sticker Generator - Creates front and back stickers from Blender texture output
Size: 130mm x 170mm @ 300 DPI
"""

import os
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path


# Constants
STICKER_WIDTH_MM = 130.0
STICKER_HEIGHT_MM = 170.0
DPI = 300

# Convert mm to pixels
MM_TO_INCH = 25.4
STICKER_WIDTH_PX = int((STICKER_WIDTH_MM / MM_TO_INCH) * DPI)  # 1535
STICKER_HEIGHT_PX = int((STICKER_HEIGHT_MM / MM_TO_INCH) * DPI)  # 2008

# Colors
GRAY_BACKGROUND = (200, 200, 205)  # Light gray
BLUE_TEXT = (30, 80, 150)  # Dark blue for text
WHITE = (255, 255, 255)

# Layout for front sticker
FRONT_PADDING_TOP = 80  # pixels
FRONT_PADDING_SIDES = 120  # pixels
FRONT_PADDING_BOTTOM = 380  # pixels for title text below card
FRONT_CORNER_RADIUS = 50  # rounded corners for texture preview

# Layout for back sticker
BACK_LOGO_TOP_MARGIN = 60
BACK_FIGURE_ID_TOP = 160
BACK_DESCRIPTION_BOTTOM_MARGIN = 80


def create_rounded_rectangle_mask(size, radius):
    """Create a smooth anti-aliased mask with rounded corners"""
    # Create mask at 4x resolution for anti-aliasing
    scale = 4
    large_size = (size[0] * scale, size[1] * scale)
    large_radius = radius * scale

    mask = Image.new('L', large_size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, large_size[0]-1, large_size[1]-1], radius=large_radius, fill=255)

    # Downscale with anti-aliasing
    mask = mask.resize(size, Image.Resampling.LANCZOS)

    return mask


def load_font(size, bold=False):
    """Load a font, falling back to default if not available"""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except:
                pass

    # Fallback to default
    return ImageFont.load_default()


def create_front_sticker(texture_path: str, title: str, subtitle: str, output_path: str):
    """
    Create the front sticker with texture preview and title

    Args:
        texture_path: Path to the texture PNG from Blender
        title: Main title text (e.g., "MAX MUSTERMANN")
        subtitle: Subtitle text (e.g., "BEST DAD")
        output_path: Output path for the front sticker
    """
    print(f"\n=== Creating Front Sticker ===")
    print(f"  Texture: {texture_path}")
    print(f"  Title: {title}")
    print(f"  Subtitle: {subtitle}")

    # Create gray background
    sticker = Image.new('RGB', (STICKER_WIDTH_PX, STICKER_HEIGHT_PX), GRAY_BACKGROUND)
    draw = ImageDraw.Draw(sticker)

    # Calculate texture preview area
    preview_left = FRONT_PADDING_SIDES
    preview_top = FRONT_PADDING_TOP
    preview_width = STICKER_WIDTH_PX - (2 * FRONT_PADDING_SIDES)
    preview_height = STICKER_HEIGHT_PX - FRONT_PADDING_TOP - FRONT_PADDING_BOTTOM

    print(f"  Preview area: {preview_width}x{preview_height}px at ({preview_left}, {preview_top})")

    # Load and resize texture
    if os.path.exists(texture_path):
        texture = Image.open(texture_path).convert('RGBA')

        # Resize texture to fit preview area while maintaining aspect ratio
        tex_aspect = texture.width / texture.height
        preview_aspect = preview_width / preview_height

        if tex_aspect > preview_aspect:
            # Texture is wider - fit to width
            new_width = preview_width
            new_height = int(preview_width / tex_aspect)
        else:
            # Texture is taller - fit to height
            new_height = preview_height
            new_width = int(preview_height * tex_aspect)

        texture_resized = texture.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Center the texture in preview area
        tex_x = preview_left + (preview_width - new_width) // 2
        tex_y = preview_top + (preview_height - new_height) // 2

        # Create rounded corners mask
        mask = create_rounded_rectangle_mask((new_width, new_height), FRONT_CORNER_RADIUS)

        # Create a temporary image for the rounded texture
        rounded_texture = Image.new('RGBA', (new_width, new_height), (0, 0, 0, 0))
        rounded_texture.paste(texture_resized, (0, 0))
        rounded_texture.putalpha(mask)

        # Paste onto sticker
        sticker.paste(rounded_texture, (tex_x, tex_y), rounded_texture)

        print(f"  Texture placed: {new_width}x{new_height}px at ({tex_x}, {tex_y})")
    else:
        # Draw placeholder rectangle if texture not found
        draw.rounded_rectangle(
            [preview_left, preview_top, preview_left + preview_width, preview_top + preview_height],
            radius=FRONT_CORNER_RADIUS,
            fill=(100, 130, 170),
            outline=None
        )
        print(f"  WARNING: Texture not found, using placeholder")

    # Add title text below the card
    title_font = load_font(110, bold=True)
    subtitle_font = load_font(90, bold=True)

    # Calculate text position (centered, below the preview)
    text_y_start = preview_top + preview_height + 50

    if title:
        title_bbox = draw.textbbox((0, 0), title.upper(), font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (STICKER_WIDTH_PX - title_width) // 2
        draw.text((title_x, text_y_start), title.upper(), fill=BLUE_TEXT, font=title_font)
        text_y_start += 120

    if subtitle:
        subtitle_bbox = draw.textbbox((0, 0), subtitle.upper(), font=subtitle_font)
        subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
        subtitle_x = (STICKER_WIDTH_PX - subtitle_width) // 2
        draw.text((subtitle_x, text_y_start), subtitle.upper(), fill=BLUE_TEXT, font=subtitle_font)

    # Save with high quality
    sticker.save(output_path, 'PNG', dpi=(DPI, DPI))
    print(f"  Saved: {output_path}")

    return output_path


def create_back_sticker(job_id: str, output_path: str, logo_path: str = None):
    """
    Create the back sticker with logo, job ID, and description

    Args:
        job_id: The job/figure ID
        output_path: Output path for the back sticker
        logo_path: Optional path to SimpleME logo image
    """
    print(f"\n=== Creating Back Sticker ===")
    print(f"  Job ID: {job_id}")

    # Create gray background
    sticker = Image.new('RGB', (STICKER_WIDTH_PX, STICKER_HEIGHT_PX), GRAY_BACKGROUND)
    draw = ImageDraw.Draw(sticker)

    # Load fonts
    logo_font = load_font(80, bold=True)
    id_font = load_font(36, bold=True)
    desc_font = load_font(28, bold=False)

    # Draw "Simple ME" text logo at top
    logo_text = "Simple ME"
    logo_bbox = draw.textbbox((0, 0), logo_text, font=logo_font)
    logo_width = logo_bbox[2] - logo_bbox[0]
    logo_x = (STICKER_WIDTH_PX - logo_width) // 2 - 40  # Offset for icon
    draw.text((logo_x, BACK_LOGO_TOP_MARGIN), logo_text, fill=BLUE_TEXT, font=logo_font)

    # Draw simple icon next to logo (person in box)
    icon_x = logo_x + logo_width + 20
    icon_y = BACK_LOGO_TOP_MARGIN + 10
    icon_size = 70

    # Draw icon box
    draw.rounded_rectangle(
        [icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
        radius=8,
        fill=BLUE_TEXT
    )
    # Draw simple person shape in icon
    person_cx = icon_x + icon_size // 2
    person_cy = icon_y + icon_size // 2
    # Head
    draw.ellipse([person_cx - 10, icon_y + 12, person_cx + 10, icon_y + 32], fill=WHITE)
    # Body
    draw.rectangle([person_cx - 8, icon_y + 35, person_cx + 8, icon_y + 55], fill=WHITE)

    # Draw Figure ID
    figure_id_text = f"FIGURE ID: {job_id.upper()}"
    id_bbox = draw.textbbox((0, 0), figure_id_text, font=id_font)
    id_width = id_bbox[2] - id_bbox[0]
    id_x = (STICKER_WIDTH_PX - id_width) // 2
    draw.text((id_x, BACK_FIGURE_ID_TOP), figure_id_text, fill=(50, 50, 50), font=id_font)

    # Draw description text at bottom (German)
    description_lines = [
        "Diese Figur wurde individuell für Sie erstellt.",
        "Basierend auf einem Foto, gefertigt mit KI-Technologie",
        "und hochwertigem 3D-Druck.",
        "Jedes Stück ist ein Unikat."
    ]

    # Calculate starting Y for description (from bottom)
    line_height = 38
    total_desc_height = len(description_lines) * line_height
    desc_y = STICKER_HEIGHT_PX - BACK_DESCRIPTION_BOTTOM_MARGIN - total_desc_height

    for line in description_lines:
        line_bbox = draw.textbbox((0, 0), line, font=desc_font)
        line_width = line_bbox[2] - line_bbox[0]
        line_x = (STICKER_WIDTH_PX - line_width) // 2
        draw.text((line_x, desc_y), line, fill=BLUE_TEXT, font=desc_font)
        desc_y += line_height

    # Save with high quality
    sticker.save(output_path, 'PNG', dpi=(DPI, DPI))
    print(f"  Saved: {output_path}")

    return output_path


def generate_stickers(
    texture_path: str,
    output_dir: str,
    job_id: str,
    title: str = "",
    subtitle: str = ""
):
    """
    Generate both front and back stickers

    Args:
        texture_path: Path to the texture PNG from Blender
        output_dir: Directory to save stickers
        job_id: Job ID for the figure
        title: Title text for front sticker
        subtitle: Subtitle text for front sticker

    Returns:
        dict with paths to front and back stickers
    """
    os.makedirs(output_dir, exist_ok=True)

    front_path = os.path.join(output_dir, f"{job_id}_sticker_front.png")
    back_path = os.path.join(output_dir, f"{job_id}_sticker_back.png")

    create_front_sticker(texture_path, title, subtitle, front_path)
    create_back_sticker(job_id, back_path)

    print(f"\n=== Stickers Generated ===")
    print(f"  Front: {front_path}")
    print(f"  Back: {back_path}")

    return {
        "front": front_path,
        "back": back_path
    }


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate front and back stickers")
    parser.add_argument("--texture", required=True, help="Path to texture PNG from Blender")
    parser.add_argument("--output_dir", required=True, help="Output directory for stickers")
    parser.add_argument("--job_id", required=True, help="Job/Figure ID")
    parser.add_argument("--title", default="", help="Title text for front sticker")
    parser.add_argument("--subtitle", default="", help="Subtitle text for front sticker")

    args = parser.parse_args()

    generate_stickers(
        texture_path=args.texture,
        output_dir=args.output_dir,
        job_id=args.job_id,
        title=args.title,
        subtitle=args.subtitle
    )
