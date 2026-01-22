import asyncio
import os
from services.sticker_maker_service import StickerMakerService

JOB_ID = "75520930-b7f2-4196-b111-9b6baba12c90"
MODELS_DIR = f"/workspace/SimpleMe/storage/processed/{JOB_ID}/3d_models"
GENERATED_DIR = f"/workspace/SimpleMe/storage/generated/{JOB_ID}"

async def main():
    print("🎨 Running sticker generation...")

    # List all GLB models
    glb_files = sorted([f for f in os.listdir(MODELS_DIR) if f.endswith('.glb')])
    print(f"\n📦 Found {len(glb_files)} 3D models:")
    for f in glb_files:
        size_mb = os.path.getsize(os.path.join(MODELS_DIR, f)) / (1024 * 1024)
        print(f"   - {f} ({size_mb:.1f} MB)")

    # Prepare models_3d list
    models_3d = []
    for f in glb_files:
        models_3d.append({
            "model_path": os.path.join(MODELS_DIR, f),
            "success": True
        })

    # Find corresponding nobg images
    # Map model names to image names
    processed_images = []

    # Base character
    base_imgs = sorted([f for f in os.listdir(GENERATED_DIR) if f.startswith('base_character') and f.endswith('_nobg.png')])
    if base_imgs:
        processed_images.append({
            "processed_path": os.path.join(GENERATED_DIR, base_imgs[-1]),  # Use latest
            "type": "base_character"
        })
        print(f"\n🖼️ Using images:")
        print(f"   - base_character: {base_imgs[-1]}")

    # Accessories
    for i in range(1, 4):
        acc_imgs = sorted([f for f in os.listdir(GENERATED_DIR) if f.startswith(f'accessory_{i}') and f.endswith('_nobg.png')])
        if acc_imgs:
            processed_images.append({
                "processed_path": os.path.join(GENERATED_DIR, acc_imgs[-1]),  # Use latest
                "type": f"accessory_{i}"
            })
            print(f"   - accessory_{i}: {acc_imgs[-1]}")

    print(f"\n🖨️ Starting PrintMaker...")
    sticker_service = StickerMakerService()

    result = await sticker_service.process_3d_models(
        job_id=JOB_ID,
        models_3d=models_3d,
        processed_images=processed_images
    )

    if result.get("success"):
        print(f"\n✅ Stickers generated successfully!")
        print(f"   Output directory: {result.get('output_dir')}")
        print(f"\n📁 Output files:")
        for f in result.get('output_files', []):
            print(f"   - {f.get('filename')} ({f.get('file_size_mb', 0):.1f} MB)")
    else:
        print(f"\n❌ Sticker generation failed: {result.get('error')}")

if __name__ == "__main__":
    asyncio.run(main())
