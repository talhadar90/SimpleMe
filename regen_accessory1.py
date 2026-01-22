import asyncio
import os
import base64
from datetime import datetime
from openai import AsyncOpenAI
from config.settings import settings
from services.background_remover import BackgroundRemover
from services.threed_client_factory import create_3d_client

JOB_ID = "75520930-b7f2-4196-b111-9b6baba12c90"
GENERATED_DIR = f"/workspace/SimpleMe/storage/generated/{JOB_ID}"
MODELS_DIR = f"/workspace/SimpleMe/storage/processed/{JOB_ID}/3d_models"

async def main():
    print("🎨 Regenerating accessory_1 with wallet...")

    # Step 1: Generate new image using OpenAI directly
    print("\n📸 Step 1: Generating wallet image...")
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    # Use a safe prompt - wallet (no currency)
    prompt = """A premium brown leather bifold wallet, luxury men's wallet with stitching details,
slightly open showing card slots, high quality 3D render, front view,
centered on white background, realistic leather texture, classic elegant style"""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"{GENERATED_DIR}/accessory_1_{timestamp}.png"

    response = await client.images.generate(
        model="gpt-image-1.5",
        prompt=prompt,
        n=1,
        size="1024x1536",
        quality="high",
        background="transparent",
        output_format="png"
    )

    # Save image - handle base64 response
    image_data = base64.b64decode(response.data[0].b64_json)
    with open(output_path, "wb") as f:
        f.write(image_data)

    generated_image = output_path
    print(f"✅ Generated: {generated_image}")

    # Step 2: Remove background
    print("\n🧹 Step 2: Removing background...")
    remover = BackgroundRemover()

    nobg_path = generated_image.replace(".png", "_nobg.png")
    bg_result = await remover.remove_background_single(generated_image, nobg_path)

    if not bg_result:
        print(f"❌ Background removal failed")
        return

    nobg_image = nobg_path
    print(f"✅ Background removed: {nobg_image}")

    # Step 3: Convert to 3D
    print("\n🔄 Step 3: Converting to 3D...")
    threed_client = create_3d_client()

    # Use convert_images_to_3d with a single image
    processed_images = [{"file_path": nobg_image, "type": "accessory_1"}]
    models_3d = await threed_client.convert_images_to_3d(JOB_ID, processed_images)

    if models_3d and len(models_3d) > 0:
        model = models_3d[0]
        print(f"\n✅ accessory_1 3D model created!")
        print(f"   Path: {model.get('model_path')}")
    else:
        print(f"\n❌ 3D conversion failed - no model returned")

    await threed_client.close()

if __name__ == "__main__":
    asyncio.run(main())
