import asyncio
import os
from services.threed_client_factory import create_3d_client

JOB_ID = "75520930-b7f2-4196-b111-9b6baba12c90"
GENERATED_DIR = f"/workspace/SimpleMe/storage/generated/{JOB_ID}"

async def main():
    # Map the nobg images (just figure for now)
    images = {
        "base_character": f"{GENERATED_DIR}/base_character_20260122_212103_nobg.png",
    }

    # Check all files exist
    for name, path in images.items():
        if os.path.exists(path):
            print(f"✅ Found: {name}")
        else:
            print(f"❌ Missing: {path}")
            return

    # Step 1: Convert to 3D
    print("\n🔄 Converting to 3D models...")
    print(f"   Processing {len(images)} images:")
    for name, path in images.items():
        print(f"     - {name}: {path}")
    client = create_3d_client()

    models_dir = f"/workspace/SimpleMe/storage/processed/{JOB_ID}/3d_models"
    os.makedirs(models_dir, exist_ok=True)

    # Prepare processed_images list from images dict
    processed_images_list = [
        {"file_path": path, "type": name}
        for name, path in images.items()
    ]

    # Use the parallel convert_images_to_3d method
    models_3d = await client.convert_images_to_3d(JOB_ID, processed_images_list)

    # Check results
    if not models_3d:
        print("\n❌ No models returned - check logs above for errors")
        return

    successful_models = [m for m in models_3d if m.get("success")]
    failed_models = [m for m in models_3d if not m.get("success")]
    print(f"\n✅ {len(successful_models)}/{len(images)} models converted successfully")

    if failed_models:
        print("❌ Some models failed to convert:")
        for m in failed_models:
            print(f"   - {m.get('type', 'unknown')}: {m.get('error', 'unknown error')}")

    if len(successful_models) < len(images):
        print("\n⚠️ Not all models converted - stopping here")
        return

    # Skip sticker generation for now - just testing 3D model texture
    print(f"\n✅ Done! Check the GLB file in: {models_dir}")

    # Cleanup
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
