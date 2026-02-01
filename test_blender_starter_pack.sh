#!/bin/bash
# Test the Blender Starter Pack - Displacement Method with Accessories
#
# Usage examples:
#   ./test_blender_starter_pack.sh                    # Default: transparent background
#   ./test_blender_starter_pack.sh solid blue         # Solid blue background
#   ./test_blender_starter_pack.sh image /path/to/bg.png  # Image background

BLENDER_SCRIPT="/workspace/SimpleMe/services/blender_starter_pack.py"
OUTPUT_DIR="/workspace/SimpleMe/storage/test_sculptok/ca767ebc/final_output"

# Figure files
FIGURE_DEPTH="/workspace/SimpleMe/storage/test_sculptok/ca767ebc/sculptok_output/base_character/base_character_depth.png"
FIGURE_IMG="/workspace/SimpleMe/storage/generated/00cba3d4/base_character_20260131_204647.png"

# Accessory 1 files
ACC1_DEPTH="/workspace/SimpleMe/storage/test_sculptok/ca767ebc/sculptok_output/accessory_1/accessory_1_depth.png"
ACC1_IMG="/workspace/SimpleMe/storage/generated/ca767ebc/accessory_1_20260130_172630.png"

# Accessory 2 files
ACC2_DEPTH="/workspace/SimpleMe/storage/test_sculptok/ca767ebc/sculptok_output/accessory_2/accessory_2_depth.png"
ACC2_IMG="/workspace/SimpleMe/storage/generated/ca767ebc/accessory_2_20260130_172719.png"

# Accessory 3 files
ACC3_DEPTH="/workspace/SimpleMe/storage/test_sculptok/ca767ebc/sculptok_output/accessory_3/accessory_3_depth.png"
ACC3_IMG="/workspace/SimpleMe/storage/generated/ca767ebc/accessory_3_20260130_172811.png"

# Background options (can be overridden via command line)
BG_TYPE="${1:-transparent}"  # transparent, solid, or image
BG_COLOR="${2:-white}"       # Color name for solid background
BG_IMAGE="${2:-}"            # Path to background image (for image type)

mkdir -p "$OUTPUT_DIR"

echo "==================================="
echo "Running Blender - Displacement Method"
echo "==================================="
echo "Background: type=$BG_TYPE, color=$BG_COLOR"

# Build background arguments
BG_ARGS="--background_type $BG_TYPE"
if [ "$BG_TYPE" == "solid" ]; then
    BG_ARGS="$BG_ARGS --background_color $BG_COLOR"
elif [ "$BG_TYPE" == "image" ] && [ -n "$BG_IMAGE" ]; then
    BG_ARGS="$BG_ARGS --background_image $BG_IMAGE"
fi

blender --background --python "$BLENDER_SCRIPT" -- \
    --figure_depth "$FIGURE_DEPTH" \
    --figure_img "$FIGURE_IMG" \
    --acc1_depth "$ACC1_DEPTH" \
    --acc1_img "$ACC1_IMG" \
    --acc2_depth "$ACC2_DEPTH" \
    --acc2_img "$ACC2_IMG" \
    --acc3_depth "$ACC3_DEPTH" \
    --acc3_img "$ACC3_IMG" \
    --output_dir "$OUTPUT_DIR" \
    --job_id "displacement_test" \
    --title "Helmut" \
    --subtitle "TGI AG" \
    --text_color "red" \
    $BG_ARGS

echo ""
echo "==================================="
echo "Done! Check: $OUTPUT_DIR/displacement_test.blend"
echo "==================================="
echo "Outputs:"
echo "  - STL: $OUTPUT_DIR/displacement_test.stl"
echo "  - Texture: $OUTPUT_DIR/displacement_test_texture.png"
echo "  - Blend: $OUTPUT_DIR/displacement_test.blend"
echo "==================================="
