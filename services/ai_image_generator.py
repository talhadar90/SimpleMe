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
        """Build character prompt with technical specifications"""
        return f"""Transform this person into a highly detailed 3D action figure character:

CHARACTER REQUIREMENTS:
- Realistic facial features matching the person in the image (according to gender)
- FULL BODY from head to feet - complete figure including legs, torso, arms, and head
- Professional action figure proportions
- Show entire body standing - never cut off at waist, knees, or chest
- High-quality textures and materials

CLOTHING (CRITICAL):
- NO TEXT on any clothing or garments - remove all logos, brand names, letters, numbers
- NO logos, symbols, or graphic prints on shirts, pants, shoes, or accessories
- Plain solid colors or simple patterns only (stripes, checks OK)
- Clean, unbranded clothing aesthetic
- If original clothing has text/logos, replace with plain solid color version

POSE - EXTREMELY IMPORTANT - MUST FOLLOW EXACTLY:
- A-pose ONLY: Arms STRAIGHT down, touching the sides of the thighs
- Arms must be FULLY EXTENDED downward, NOT bent at elbows
- Hands open with fingers pointing DOWN toward the ground, palms facing inward toward thighs
- NO fists, NO gloves visible on hands, NO bent arms
- Arms should form a straight vertical line from shoulder to fingertips
- Standing like a wooden mannequin or store display dummy
- Legs straight, feet together or slightly apart
- Face forward, neutral expression
- This is a NEUTRAL REFERENCE POSE for 3D scanning - absolutely NO action poses

COMPOSITION:
- Centered composition with full height of character visible
- Complete figure from top of head to bottom of feet with no body parts cropped
- Flat, even lighting with minimal shadows for 3D conversion
- Action figure aesthetic with clean, defined details
- Premium collectible quality
- Portrait orientation layout showing the complete full-length figure
- Pure transparent background

CRITICAL: Arms STRAIGHT DOWN touching thighs. Hands OPEN, fingers pointing to floor. NO bent elbows. NO fists. NO text or logos on clothing. Like an action figure in original packaging - stiff neutral pose."""

    def _stylize_currency_if_needed(self, accessory: str) -> tuple[str, bool]:
        """
        Detect currency-related terms and stylize to avoid 3D API content policy issues.

        Returns:
            tuple: (modified_accessory_description, was_stylized)
        """
        # Currency-related keywords to detect
        currency_keywords = [
            'dollar', 'dollars', 'bill', 'bills', 'money', 'cash', 'currency',
            'hundred', '$100', '$50', '$20', '$10', '$1', 'banknote', 'banknotes',
            'euro', 'euros', 'pound', 'pounds', 'yen', 'yuan', 'peso', 'rupee',
            'franc', 'krona', 'won', 'real', 'lira', 'dinar', 'dirham'
        ]

        accessory_lower = accessory.lower()
        is_currency = any(keyword in accessory_lower for keyword in currency_keywords)

        if is_currency:
            # Stylize the currency to be cartoon/game-style
            stylized = f"stylized cartoon {accessory}, game asset style, illustrated NOT realistic currency, playful design with $ symbols"
            print(f"💵 Detected currency in accessory, stylizing: '{accessory}' -> cartoon style")
            return stylized, True

        return accessory, False

    def _build_accessory_prompt(self, accessory: str) -> str:
        """Build accessory prompt with technical specifications for 3D conversion"""
        # Check if this is currency and stylize if needed
        stylized_accessory, was_stylized = self._stylize_currency_if_needed(accessory)

        # Add extra stylization instructions for currency
        currency_note = ""
        if was_stylized:
            currency_note = """
CURRENCY STYLIZATION (CRITICAL):
- Must be CARTOON/GAME STYLE - NOT realistic currency
- Use bright, playful colors
- Add visible $ or currency symbols
- Make it look like video game money or Monopoly money
- NO realistic portraits, serial numbers, or government seals
"""

        return f"""Create a highly detailed 3D rendered {stylized_accessory}:

ACCESSORY REQUIREMENTS:
- ONLY ONE single {stylized_accessory} in the image - no duplicates, no multiple items
- Premium collectible quality design
- Realistic textures and materials with visible surface details
- Perfect for action figure scale/use
- Modern detailed design with high-quality finish
{currency_note}

CAMERA ANGLE (CRITICAL FOR 3D CONVERSION):
- FLAT LAY / TOP-DOWN view - camera looking straight down at the object
- Object lying flat on surface, photographed from directly above
- Shows the full shape and outline of the object clearly
- NO perspective distortion - orthographic style view
- Front face of the object should be visible and facing up

LIGHTING (CRITICAL):
- FLAT, even lighting with NO shadows
- NO cast shadows on or around the object
- NO ambient occlusion shadows
- Soft, diffused light from all directions
- No harsh highlights or dark areas
- Pure transparent background with no gradients

COMPOSITION (CRITICAL):
- ONE accessory only - single item, not a set or collection
- Centered in the middle of the image
- Complete item visible with no cropping at all
- Isolated item on pure transparent background
- No other objects, props, or accessories in the scene
- Clean, defined edges and silhouette
- Vibrant colors with premium finish
- High resolution and sharp details
- Object should fill about 70% of the frame

CRITICAL: Generate exactly ONE {stylized_accessory} - single item only, flat lay angle from above, NO SHADOWS, centered, complete, no duplicates."""

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
