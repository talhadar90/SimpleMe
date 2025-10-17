import os
import asyncio
import uuid
import json
import aiohttp
from typing import List, Dict, Optional
from PIL import Image
import aiofiles
from datetime import datetime
from config.settings import settings
import io
import tempfile

class ComfyUIBackgroundRemover:
    def __init__(self):
        """Initialize ComfyUI background remover"""
        # Use hardcoded values or try to get from settings
        try:
            self.server_address = getattr(settings, 'COMFYUI_SERVER', "35.170.49.109:8188")
            self.static_url_base = getattr(settings, 'STATIC_FILES_URL', "http://35.170.49.109:8000")
        except:
            self.server_address = "35.170.49.109:8188"
            self.static_url_base = "http://35.170.49.109:8000"
        
        self.client_id = str(uuid.uuid4())
        self.workflow = {
            "10": {
                "inputs": {
                    "url_or_path": ""
                },
                "class_type": "LoadImageFromUrlOrPath",
                "_meta": {
                    "title": "LoadImageFromUrlOrPath"
                }
            },
            "11": {
                "inputs": {
                    "rem_mode": "RMBG-1.4",
                    "image_output": "Preview",
                    "save_prefix": "ComfyUI",
                    "torchscript_jit": False,
                    "add_background": "none",
                    "refine_foreground": False,
                    "images": ["10", 0]
                },
                "class_type": "easy imageRemBg",
                "_meta": {
                    "title": "Image Remove Bg"
                }
            },
            "13": {
                "inputs": {
                    "filename_prefix": "ComfyUI",
                    "images": ["11", 0]
                },
                "class_type": "SaveImage",
                "_meta": {
                    "title": "Save Image"
                }
            },
            "14": {
                "inputs": {
                    "images": ["11", 0]
                },
                "class_type": "SaveImageWebsocket",
                "_meta": {
                    "title": "SaveImageWebsocket"
                }
            }
        }
        print(f"✅ ComfyUI Background remover initialized - Server: {self.server_address}")

    async def remove_backgrounds_from_job(self, job_id: str, generated_images: List[Dict]) -> List[Dict]:
        """
        Remove backgrounds from all generated images for a job using ComfyUI
        
        Args:
            job_id: The job identifier
            generated_images: List of image metadata from AI generation
            
        Returns:
            List of processed image metadata with background removed
        """
        processed_images = []
        
        # Create processed directory for this job
        processed_dir = os.path.join(settings.PROCESSED_PATH, job_id)
        os.makedirs(processed_dir, exist_ok=True)
        
        print(f"🎭 Removing backgrounds using ComfyUI for job {job_id} - {len(generated_images)} images")
        
        for i, image_data in enumerate(generated_images, 1):
            try:
                print(f"🔄 Processing image {i}/{len(generated_images)}: {image_data['type']}")
                
                processed_result = await self._remove_background_from_image(
                    image_data=image_data,
                    job_id=job_id,
                    processed_dir=processed_dir
                )
                
                if processed_result:
                    processed_images.append(processed_result)
                    print(f"✅ Background removed for {image_data['type']}")
                else:
                    print(f"⚠️ Failed to process {image_data['type']}, keeping original")
                    # Keep original if processing fails
                    processed_images.append(image_data)
                    
            except Exception as e:
                print(f"❌ Error processing {image_data['type']}: {str(e)}")
                # Keep original if processing fails
                processed_images.append(image_data)
        
        print(f"✅ Background removal completed for job {job_id}")
        return processed_images
    
    async def _remove_background_from_image(self, image_data: Dict, job_id: str, processed_dir: str) -> Optional[Dict]:
        """
        Remove background from a single image using ComfyUI
        
        Args:
            image_data: Image metadata from AI generation
            job_id: Job identifier
            processed_dir: Directory to save processed images
            
        Returns:
            Updated image metadata with processed file path
        """
        try:
            original_path = image_data['file_path']
            
            # Check if original file exists
            if not os.path.exists(original_path):
                print(f"❌ Original file not found: {original_path}")
                return None
            
            # Process image with ComfyUI
            processed_image_data = await self._process_with_comfyui(original_path)
            
            if not processed_image_data:
                return None
            
            # Generate new filename for processed image
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            original_filename = image_data['filename']
            base_name = original_filename.replace('.png', '')
            processed_filename = f"{base_name}_nobg_{timestamp}.png"
            processed_path = os.path.join(processed_dir, processed_filename)
            
            # Save processed image
            async with aiofiles.open(processed_path, 'wb') as f:
                await f.write(processed_image_data)
            
            # Create updated metadata
            processed_data = image_data.copy()
            processed_data.update({
                'original_file_path': original_path,
                'file_path': processed_path,
                'filename': processed_filename,
                'url': f"/storage/processed/{job_id}/{processed_filename}",
                'background_removed': True,
                'background_removal_at': datetime.now().isoformat(),
                'processing_method': 'comfyui_rmbg'
            })
            
            return processed_data
            
        except Exception as e:
            print(f"❌ Error in _remove_background_from_image: {str(e)}")
            return None

    async def _process_with_comfyui(self, image_path: str) -> Optional[bytes]:
        """
        Process image with ComfyUI background removal
        
        Args:
            image_path: Path to the input image
            
        Returns:
            Processed image bytes with background removed
        """
        try:
            # Create a publicly accessible URL for the image
            public_image_url = await self._create_public_image_url(image_path)
            if not public_image_url:
                return None

            # Create workflow with the image URL
            workflow = self.workflow.copy()
            workflow["10"]["inputs"]["url_or_path"] = public_image_url
            
            # Generate unique prompt ID
            prompt_id = str(uuid.uuid4())
            
            # Queue the prompt
            await self._queue_prompt(workflow, prompt_id)
            
            # Get the processed image using HTTP polling (more reliable than websockets)
            processed_image_data = await self._get_processed_image_http_polling(prompt_id)
            
            # Clean up temporary image file
            await self._cleanup_temp_image(public_image_url)
            
            return processed_image_data
            
        except Exception as e:
            print(f"❌ Error in ComfyUI processing: {str(e)}")
            return None

    async def _create_public_image_url(self, image_path: str) -> Optional[str]:
        """
        Create a publicly accessible URL for the image
        This could be done by:
        1. Copying to a web-accessible directory
        2. Using a temporary file server
        3. Uploading to a cloud service
        
        For now, we'll copy to a web-accessible static directory
        """
        try:
            # Create a static directory if it doesn't exist
            static_dir = os.path.join(os.getcwd(), "static", "temp_images")
            os.makedirs(static_dir, exist_ok=True)
            
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            filename = f"temp_{timestamp}.png"
            temp_path = os.path.join(static_dir, filename)
            
            # Copy image to static directory
            async with aiofiles.open(image_path, 'rb') as src:
                image_data = await src.read()
            
            async with aiofiles.open(temp_path, 'wb') as dst:
                await dst.write(image_data)
            
            # Return the public URL
            public_url = f"{self.static_url_base}/static/temp_images/{filename}"
            print(f"📸 Created public image URL: {public_url}")
            
            return public_url
            
        except Exception as e:
            print(f"❌ Error creating public image URL: {str(e)}")
            return None

    async def _cleanup_temp_image(self, public_url: str):
        """Clean up temporary image file"""
        try:
            # Extract filename from URL
            filename = public_url.split('/')[-1] if public_url else ""
            if filename.startswith('temp_'):
                temp_path = os.path.join(os.getcwd(), "static", "temp_images", filename)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    print(f"🧹 Cleaned up temp file: {filename}")
        except Exception as e:
            print(f"⚠️ Error cleaning up temp file: {str(e)}")

    async def _queue_prompt(self, prompt: dict, prompt_id: str):
        """Queue a prompt to ComfyUI"""
        try:
            payload = {
                "prompt": prompt,
                "client_id": self.client_id,
                "prompt_id": prompt_id
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"http://{self.server_address}/prompt",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        raise Exception(f"Failed to queue prompt: {response.status}")
                    print(f"✅ Prompt queued successfully: {prompt_id}")
                    
        except Exception as e:
            print(f"❌ Error queuing prompt: {str(e)}")
            raise

    async def _get_processed_image_http_polling(self, prompt_id: str) -> Optional[bytes]:
        """Get the processed image from ComfyUI via HTTP polling (more reliable for large images)"""
        try:
            # Poll for completion instead of using websocket
            max_attempts = 30  # 5 minutes max wait (30 * 10 seconds)
            attempt = 0
            
            print(f"🔄 Starting HTTP polling for prompt: {prompt_id}")
            
            while attempt < max_attempts:
                # Get history to check completion
                history_data = await self._get_history(prompt_id)
                
                if history_data:
                    # Check if the execution is complete by looking for outputs
                    outputs = history_data.get('outputs', {})
                    if outputs:  # If we have outputs, processing is complete
                        # Extract image from history
                        processed_image_data = await self._extract_image_from_history(history_data, prompt_id)
                        if processed_image_data:
                            print(f"✅ HTTP polling successful after {attempt + 1} attempts")
                            return processed_image_data
                
                # Wait before next check
                await asyncio.sleep(10)  # Check every 10 seconds
                attempt += 1
                if attempt % 3 == 0:  # Log every 30 seconds
                    print(f"🔄 Polling attempt {attempt}/{max_attempts} for prompt: {prompt_id}")
            
            print(f"⏰ HTTP polling timeout after {max_attempts} attempts")
            return None
            
        except Exception as e:
            print(f"❌ Error in HTTP polling: {str(e)}")
            return None

    async def _get_history(self, prompt_id: str) -> Optional[dict]:
        """Get execution history from ComfyUI"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://{self.server_address}/history/{prompt_id}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        history = await response.json()
                        return history.get(prompt_id)
                    else:
                        # Don't log errors for 404s - prompt might not be in history yet
                        if response.status != 404:
                            print(f"❌ Failed to get history: {response.status}")
                        return None
                        
        except Exception as e:
            print(f"❌ Error getting history: {str(e)}")
            return None

    async def _extract_image_from_history(self, history_data: dict, prompt_id: str) -> Optional[bytes]:
        """Extract the processed image from ComfyUI history"""
        try:
            # Look for output images in the history
            outputs = history_data.get('outputs', {})
            
            # Try to find image output from node 13 (SaveImage) or 14 (SaveImageWebsocket)
            for node_id in ['13', '14']:
                if node_id in outputs:
                    node_output = outputs[node_id]
                    if 'images' in node_output and len(node_output['images']) > 0:
                        image_info = node_output['images'][0]
                        
                        # Download the image
                        image_data = await self._download_image(
                            image_info['filename'], 
                            image_info.get('subfolder', ''), 
                            image_info.get('type', 'output')
                        )
                        
                        if image_data:
                            print(f"✅ Successfully extracted image from node {node_id}")
                            return image_data
            
            print(f"❌ No image found in history for prompt {prompt_id}")
            return None
            
        except Exception as e:
            print(f"❌ Error extracting image from history: {str(e)}")
            return None

    async def _download_image(self, filename: str, subfolder: str, folder_type: str) -> Optional[bytes]:
        """Download image from ComfyUI"""
        try:
            params = {
                "filename": filename,
                "subfolder": subfolder,
                "type": folder_type
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://{self.server_address}/view",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        print(f"✅ Downloaded image: {filename} ({len(image_data)} bytes)")
                        return image_data
                    else:
                        print(f"❌ Failed to download image: {response.status}")
                        return None
                        
        except Exception as e:
            print(f"❌ Error downloading image: {str(e)}")
            return None

    async def remove_background_single(self, input_path: str, output_path: str) -> bool:
        """
        Remove background from a single image file using ComfyUI
        
        Args:
            input_path: Path to input image
            output_path: Path to save processed image
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Process image with ComfyUI
            processed_data = await self._process_with_comfyui(input_path)
            
            if not processed_data:
                return False
            
            # Save processed image
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            async with aiofiles.open(output_path, 'wb') as f:
                await f.write(processed_data)
            
            print(f"✅ Background removed and saved to: {output_path}")
            return True
            
        except Exception as e:
            print(f"❌ Error in remove_background_single: {str(e)}")
            return False

    def get_model_info(self) -> Dict:
        """Get information about the ComfyUI background removal model"""
        return {
            'model': 'RMBG-1.4',
            'description': 'ComfyUI background removal using RMBG-1.4 model',
            'suitable_for': 'General objects, people, products with high accuracy',
            'output_format': 'PNG with transparency',
            'server': self.server_address,
            'method': 'ComfyUI API with HTTP Polling'
        }

    async def health_check(self) -> bool:
        """Check if ComfyUI server is healthy"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://{self.server_address}/",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 200
        except Exception as e:
            print(f"❌ ComfyUI health check failed: {str(e)}")
            return False

# Create alias for backward compatibility
BackgroundRemover = ComfyUIBackgroundRemover