import asyncio
import os
import shutil
from services.threed_client_factory import create_3d_client
from services.sticker_maker_service import StickerMakerService

JOB_ID = "8beb082a-4533-4b71-8190-32dbcb3f7c23"
GENERATED_DIR = f"/workspace/SimpleMe/storage/generated/{JOB_ID}"

async def main():
    # Map the nobg images
    images = {
        "base_character": f"{GENERATED_DIR}/base_character_20260122_194824_nobg.png",
        "accessory_1": f"{GENERATED_DIR}/accessory_1_20260122_194914_nobg.png",
        "accessory_2": f"{GENERATED_DIR}/accessory_2_20260122_194959_nobg.png",
        "accessory_3": f"{GENERATED_DIR}/accessory_3_20260122_195050_nobg.png",
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

    # Prepare processed_images list for parallel conversion
    # Note: client expects 'file_path' key, not 'processed_path'
    processed_images_list = [
        {"file_path": images["base_character"], "type": "base_character"},
        {"file_path": images["accessory_1"], "type": "accessory_1"},
        {"file_path": images["accessory_2"], "type": "accessory_2"},
        {"file_path": images["accessory_3"], "type": "accessory_3"},
    ]

    # Use the parallel convert_images_to_3d method
    models_3d = await client.convert_images_to_3d(JOB_ID, processed_images_list)

    # Check results
    if not models_3d:
        print("\n❌ No models returned - check logs above for errors")
        return

    successful_models = [m for m in models_3d if m.get("success")]
    failed_models = [m for m in models_3d if not m.get("success")]
    print(f"\n✅ {len(successful_models)}/4 models converted successfully")

    if failed_models:
        print("❌ Some models failed to convert:")
        for m in failed_models:
            print(f"   - {m.get('type', 'unknown')}: {m.get('error', 'unknown error')}")

    if len(successful_models) < 4:
        print("\n⚠️ Not all models converted - stopping here")
        return

    # Step 2: Generate stickers
    print("\n🎨 Generating stickers...")
    sticker_service = StickerMakerService()

    result = await sticker_service.process_3d_models(
        job_id=JOB_ID,
        models_3d=models_3d,
        processed_images=processed_images_list
    )

    if result.get("success"):
        print(f"\n✅ Stickers generated!")
        print(f"   Output: {result.get('output_dir')}")
    else:
        print(f"\n❌ Sticker generation failed: {result.get('error')}")

    # Cleanup
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
