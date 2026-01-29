#!/usr/bin/env python3
"""
Extract texture from GLB file
Run with: blender --background --python extract_texture.py
"""
import bpy
import os

# Paths
JOB_ID = "75520930-b7f2-4196-b111-9b6baba12c90"
GLB_PATH = f"/workspace/SimpleMe/storage/processed/{JOB_ID}/3d_models/base_character_4k_test.glb"
OUTPUT_DIR = f"/workspace/SimpleMe/storage/processed/{JOB_ID}/textures"


def clear_scene():
    """Remove all objects from scene"""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def main():
    print("=" * 60)
    print("Extract Texture from GLB")
    print("=" * 60)

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Clear scene
    clear_scene()

    # Import GLB
    print(f"\nImporting: {GLB_PATH}")
    bpy.ops.import_scene.gltf(filepath=GLB_PATH)

    # Find all images loaded from the GLB
    print(f"\nFound {len(bpy.data.images)} images in file:")

    extracted_count = 0
    for img in bpy.data.images:
        # Skip built-in images
        if img.name in ['Render Result', 'Viewer Node']:
            continue

        print(f"\n  Image: {img.name}")
        print(f"    Size: {img.size[0]} x {img.size[1]}")
        print(f"    Channels: {img.channels}")
        print(f"    Source: {img.source}")

        # Save the image
        # Clean filename
        safe_name = img.name.replace('/', '_').replace('\\', '_')
        if not safe_name.endswith('.png'):
            safe_name = safe_name.split('.')[0] + '.png'

        output_path = os.path.join(OUTPUT_DIR, safe_name)

        # Save as PNG
        img.filepath_raw = output_path
        img.file_format = 'PNG'
        img.save()

        print(f"    Saved to: {output_path}")
        extracted_count += 1

    print(f"\n" + "=" * 60)
    print(f"Extracted {extracted_count} texture(s) to: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
