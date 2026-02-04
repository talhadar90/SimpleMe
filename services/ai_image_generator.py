import base64
import os
import aiofiles
from openai import OpenAI
from typing import List, Dict, Optional
from datetime import datetime
from config.settings import settings

class AIImageGenerator:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL
        self.size = settings.IMAGE_SIZE
        self.quality = settings.IMAGE_QUALITY
        self.transparent_background = settings.TRANSPARENT_BACKGROUND

    async def generate_action_figures(self, job_id: str, user_image_path: str, accessories: List[str]) -> List[Dict]:

        """Generate 4 action figure images: 1 base (from user image) + 3 accessories (standalone)"""
        results = []

        # Create output directory for this job
        output_dir = os.path.join(settings.GENERATED_PATH, job_id)
        os.makedirs(output_dir, exist_ok=True)

        print(f"🎨 Generating action figures")

        # 1. Generate base action figure from user image using IMAGE EDIT API
        base_prompt = self._build_character_prompt()
        base_result = await self._generate_from_user_image(
            job_id=job_id,
            user_image_path=user_image_path,
            prompt=base_prompt,
            image_type="base_character",
            output_dir=output_dir
        )
        if base_result:
            results.append(base_result)

        # 2. Generate standalone accessory images using IMAGE GENERATION API
        for i, accessory in enumerate(accessories, 1):
            accessory_prompt = self._build_accessory_prompt(accessory)
            accessory_result = await self._generate_accessory_image(
                job_id=job_id,
                prompt=accessory_prompt,
                image_type=f"accessory_{i}",
                output_dir=output_dir,
                accessory_name=accessory
            )
            if accessory_result:
                results.append(accessory_result)

        return results

    async def ensure_transparent_background(self, image_path: str) -> Dict:
        """Ensure image has transparent background using ComfyUI background removal"""
        try:
            print(f"🖼️ Processing background removal for: {image_path}")

            # Check if file exists
            if not os.path.exists(image_path):
                return {"success": False, "error": "Image file not found"}

            # ALWAYS use ComfyUI for better background removal
            # Even if DALL-E claims transparent background, ComfyUI does it better for 3D
            from services.background_remover import ComfyUIBackgroundRemover

            bg_remover = ComfyUIBackgroundRemover()

            # Create processed file path
            base_name = os.path.splitext(image_path)[0]
            processed_path = f"{base_name}_transparent.png"

            # Process with ComfyUI
            success = await bg_remover.remove_background_single(image_path, processed_path)

            if success:
                print(f"✅ ComfyUI background removed and saved to: {processed_path}")
                return {
                    "success": True,
                    "file_path": processed_path,
                    "original_path": image_path,
                    "method": "comfyui_rmbg",
                    "processed_at": datetime.now().isoformat()
                }
            else:
                # Fallback to original if ComfyUI fails
                print(f"⚠️ ComfyUI failed, keeping original: {image_path}")
                return {
                    "success": True,
                    "file_path": image_path,
                    "method": "original_fallback",
                    "processed_at": datetime.now().isoformat()
                }

        except Exception as e:
            print(f"❌ Background removal failed for {image_path}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "original_path": image_path,
                "processed_at": datetime.now().isoformat()
            }

    def _build_character_prompt(self) -> str:
        """Build character prompt for hyperrealistic UV-print quality figure.

        Optimized for:
        - Exact facial likeness preservation
        - Hyperrealistic skin textures and details
        - Vibrant, accurate colors for UV printing
        - Clean edges for 2.5D lithophane conversion
        """
        return """Create a HYPERREALISTIC full-body portrait of this exact person for UV printing:

CAMERA ANGLE (CRITICAL - FLAT LAY VIEW):
- TOP-DOWN / FLAT LAY perspective - as if the figure is lying flat and photographed from directly above
- NO perspective distortion - orthographic style view
- Figure should appear flat like a paper doll or action figure in packaging
- This prevents weird 3D angles and ensures clean 2.5D conversion

FACE & SKIN (CRITICAL - HIGHEST PRIORITY):
- EXACT facial likeness - preserve every facial feature precisely as in the input photo
- Hyperrealistic skin texture with visible pores, subtle wrinkles, natural skin imperfections
- Accurate skin tone matching the original photo exactly
- Natural skin subsurface scattering and realistic flesh tones
- Detailed eyes with realistic iris patterns, reflections, and natural eye moisture
- Natural hair texture with individual strand details, accurate hair color
- Realistic lips with natural color and subtle texture
- Face forward, neutral expression

POSE - EXTREMELY IMPORTANT - MUST FOLLOW EXACTLY:
- A-POSE ONLY: Arms STRAIGHT down, touching the sides of the thighs
- Arms must be FULLY EXTENDED downward, NOT bent at elbows
- Hands open with fingers pointing DOWN toward the ground, palms facing inward toward thighs
- NO fists, NO gloves visible on hands, NO bent arms
- Arms should form a straight vertical line from shoulder to fingertips
- Standing like a wooden mannequin or store display dummy
- Legs straight, feet together or slightly apart
- This is a NEUTRAL REFERENCE POSE for 3D scanning - absolutely NO action poses

FULL BODY REQUIREMENTS:
- Complete full-body view from head to feet - nothing cropped
- Natural human proportions (not stylized or cartoonish)
- Feet flat on ground, legs straight

CLOTHING & FABRIC:
- Hyperrealistic fabric textures - visible weave, stitching, material properties
- Accurate colors matching any visible clothing from original photo
- Natural fabric folds and draping
- Realistic material properties (cotton, denim, leather, etc.)
- Clean, unbranded clothing - no text or logos

LIGHTING & COLOR (CRITICAL FOR UV PRINTING):
- Bright, even front lighting - no harsh shadows
- Vibrant, saturated colors optimized for print reproduction
- High color accuracy - colors must print true to screen
- Soft diffused lighting that reveals all details
- No dark shadows that would print as black areas
- Clean highlight areas without blown-out whites

COMPOSITION:
- Centered in frame with small margin on all sides
- Full body visible with no cropping
- Pure transparent background (PNG with alpha)
- Sharp, clean edges around the figure
- High resolution details throughout

OUTPUT QUALITY:
- Photorealistic quality - should look like a professional photograph
- Maximum detail and sharpness
- Print-ready color profile
- Clean silhouette for easy background separation

CRITICAL: This is for UV PRINTING - colors must be vibrant and accurate. Face must be IDENTICAL to input photo. Hyperrealistic quality, not stylized or cartoon."""

    def _build_accessory_prompt(self, accessory: str) -> str:
        """Build hyperrealistic accessory prompt optimized for UV printing and 3D conversion.

        Optimized for:
        - Photorealistic materials and textures
        - Vibrant, accurate colors for UV printing
        - Clean edges for 2.5D lithophane conversion
        - Proper lighting for depth map generation
        """
        return f"""Create a HYPERREALISTIC {accessory} for UV printing:

ACCESSORY REQUIREMENTS:
- ONLY ONE single {accessory} in the image - no duplicates, no multiple items
- PHOTOREALISTIC quality - should look like a professional product photograph
- Hyperrealistic materials with visible surface details, textures, and imperfections
- Real-world accurate proportions and scale
- Premium quality finish with realistic material properties

MATERIAL & TEXTURE (CRITICAL FOR UV PRINTING):
- Hyperrealistic surface textures - visible grain, scratches, wear patterns where appropriate
- Accurate material properties (metal reflections, fabric weave, leather grain, etc.)
- Natural material imperfections that add realism
- True-to-life colors that will print accurately
- Realistic subsurface scattering for translucent materials
- Visible fine details like stitching, seams, engraving, embossing

CAMERA ANGLE (CRITICAL FOR 3D CONVERSION - MUST FOLLOW EXACTLY):
- FLAT LAY / TOP-DOWN view - camera looking STRAIGHT DOWN at the object from directly above
- Object lying completely FLAT on surface, photographed from 90 degrees above
- NO perspective, NO 3D angles, NO tilting - pure orthographic top-down view
- Like photographing an object placed flat on a table, camera pointing straight down
- Shows the full shape and outline of the object clearly as a 2D silhouette
- Front face of the object should be visible and facing up toward camera
- This prevents weird 3D angles and ensures clean 2.5D lithophane conversion

LIGHTING (CRITICAL FOR UV PRINTING):
- Bright, even front lighting - no harsh shadows
- Soft, diffused light from all directions
- NO cast shadows on or around the object
- NO dark ambient occlusion shadows
- Colors must be vibrant and saturated for print reproduction
- No blown-out highlights or crushed blacks
- Pure transparent background (PNG with alpha)

COMPOSITION (CRITICAL):
- ONE accessory only - single item, not a set or collection
- Centered in the middle of the image
- Complete item visible with no cropping at all
- Isolated item on pure transparent background
- No other objects, props, or accessories in the scene
- Sharp, clean edges around the object
- Object should fill about 70% of the frame
- High resolution details throughout

OUTPUT QUALITY:
- Photorealistic quality - should look like a real photograph
- Maximum detail and sharpness
- Print-ready vibrant colors
- Clean silhouette for easy background separation

CRITICAL: Generate exactly ONE hyperrealistic {accessory} - single item only, flat lay angle from above, NO SHADOWS, centered, complete, photorealistic quality for UV printing."""

    async def _generate_from_user_image(self, job_id: str, user_image_path: str, prompt: str, image_type: str,
                                       output_dir: str) -> Dict:
        """Generate action figure from user image using OpenAI Image Edit API with gpt-image-1"""
        try:
            print(f"🎭 Generating {image_type} from user image for job {job_id}")
            print(f"📐 Using gpt-image-1.5 with 1024x1536 dimensions")

            with open(user_image_path, 'rb') as image_file:
                response = self.client.images.edit(
                    model="gpt-image-1.5",
                    image=image_file,
                    prompt=prompt,
                    size="1024x1536",
                    background="transparent" if self.transparent_background else "auto",
                    quality="high",
                    output_format="png",
                    input_fidelity="high",  # High fidelity to match facial features
                    n=1
                )

            # Handle base64 response (gpt-image-1 always returns b64_json)
            image_data = response.data[0]
            image_bytes = base64.b64decode(image_data.b64_json)

            # Save the image
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{image_type}_{timestamp}.png"
            file_path = os.path.join(output_dir, filename)

            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(image_bytes)

            print(f"✅ Saved {image_type} to {file_path}")

            return {
                "type": image_type,
                "method": "image_edit",
                "model_used": "gpt-image-1.5",
                "prompt": prompt,
                "size": "1024x1536",
                "quality": "high",
                "input_fidelity": "high",
                "transparent_background": self.transparent_background,
                "file_path": file_path,
                "filename": filename,
                "url": f"/storage/generated/{job_id}/{filename}",
                "generated_at": datetime.now().isoformat(),
                "tokens_used": response.usage.total_tokens if hasattr(response, 'usage') else None
            }

        except Exception as e:
            print(f"❌ Error generating {image_type}: {str(e)}")
            return None


    async def _generate_accessory_image(self, job_id: str, prompt: str, image_type: str, output_dir: str, accessory_name: str) -> Dict:
        """Generate standalone accessory image using OpenAI Image Generation API with gpt-image-1"""
        try:
            print(f"🎭 Generating {image_type} accessory for job {job_id}")
            print(f"📐 Using gpt-image-1.5 with 1024x1536 dimensions")

            response = self.client.images.generate(
                model="gpt-image-1.5",
                prompt=prompt,
                size="1024x1536",
                background="transparent" if self.transparent_background else "auto",
                quality="high",
                output_format="png",
                n=1
            )

            # Handle base64 response (gpt-image-1 always returns b64_json)
            image_data = response.data[0]
            image_bytes = base64.b64decode(image_data.b64_json)

            # Save the image
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{image_type}_{timestamp}.png"
            file_path = os.path.join(output_dir, filename)

            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(image_bytes)

            print(f"✅ Saved {image_type} to {file_path}")

            return {
                "type": image_type,
                "method": "image_generation",
                "model_used": "gpt-image-1.5",
                "prompt": prompt,
                "size": "1024x1536",
                "quality": "high",
                "transparent_background": self.transparent_background,
                "accessory": accessory_name,
                "file_path": file_path,
                "filename": filename,
                "url": f"/storage/generated/{job_id}/{filename}",
                "generated_at": datetime.now().isoformat(),
                "tokens_used": response.usage.total_tokens if hasattr(response, 'usage') else None
            }

        except Exception as e:
            print(f"❌ Error generating {image_type}: {str(e)}")
            return None
