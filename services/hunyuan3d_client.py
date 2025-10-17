import httpx
import base64
import asyncio
import os
from typing import List, Dict, Optional, Union
from datetime import datetime
import aiofiles
from config.settings import settings
import json

class Hunyuan3DClient:
    def __init__(self):
        """Initialize Hunyuan3D API client"""
        self.base_url = settings.HUNYUAN3D_API_URL
        self.timeout = settings.HUNYUAN3D_TIMEOUT
        self.max_retries = settings.HUNYUAN3D_MAX_RETRIES
        self.retry_delay = settings.HUNYUAN3D_RETRY_DELAY
        
        # HTTP client with timeout
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        
        print(f"✅ Hunyuan3D client initialized - API: {self.base_url}")

    async def generate_3d_model(self, image_path: str, job_id: str) -> Dict:
        """Generate 3D model from a single image (wrapper for compatibility)
        
        Args:
            image_path: Path to the image file
            job_id: Job identifier
            
        Returns:
            Dict with success status and model metadata
        """
        try:
            print(f"🎯 Generating 3D model from: {image_path}")
            
            # Check if image exists
            if not os.path.exists(image_path):
                return {
                    "success": False,
                    "error": f"Image file not found: {image_path}",
                    "image_path": image_path
                }
            
            # Create image metadata structure expected by convert_images_to_3d
            filename = os.path.basename(image_path)
            image_type = "unknown"
            
            # Try to determine image type from filename
            if "base_character" in filename:
                image_type = "base_character"
            elif "accessory" in filename:
                image_type = filename.split('_')[0] + "_" + filename.split('_')[1]  # e.g., "accessory_1"
            
            image_metadata = {
                "type": image_type,
                "file_path": image_path,
                "filename": filename,
                "method": "single_image_conversion",
                "processed_at": datetime.now().isoformat()
            }
            
            # Use existing convert_images_to_3d method
            models_3d = await self.convert_images_to_3d(
                job_id=job_id,
                processed_images=[image_metadata]
            )
            
            if models_3d and len(models_3d) > 0:
                model_data = models_3d[0]
                return {
                    "success": True,
                    "model_path": model_data["model_path"],
                    "model_filename": model_data["model_filename"],
                    "model_format": model_data["model_format"],
                    "model_url": model_data["model_url"],
                    "generation_method": model_data["generation_method"],
                    "file_size_bytes": model_data["file_size_bytes"],
                    "created_at": model_data["created_at"],
                    "source_image": image_path,
                    "image_type": image_type
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to generate 3D model",
                    "image_path": image_path,
                    "image_type": image_type
                }
                
        except Exception as e:
            print(f"❌ Error in generate_3d_model for {image_path}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "image_path": image_path,
                "processed_at": datetime.now().isoformat()
            }

    async def convert_images_to_3d(self, job_id: str, processed_images: List[Dict]) -> List[Dict]:
        """Convert all processed images to 3D models
        
        Args:
            job_id: Job identifier
            processed_images: List of processed image metadata
            
        Returns:
            List of 3D model metadata
        """
        models_3d = []
        
        # Create 3D models directory for this job
        models_dir = os.path.join(settings.PROCESSED_PATH, job_id, "3d_models")
        os.makedirs(models_dir, exist_ok=True)
        
        print(f"🎯 Converting {len(processed_images)} images to 3D for job {job_id}")
        
        for i, image_data in enumerate(processed_images, 1):
            try:
                print(f"🔄 Converting image {i}/{len(processed_images)}: {image_data['type']}")
                
                model_result = await self._convert_single_image_to_3d(
                    image_data=image_data,
                    job_id=job_id,
                    models_dir=models_dir
                )
                
                if model_result:
                    models_3d.append(model_result)
                    print(f"✅ 3D model created for {image_data['type']}")
                else:
                    print(f"❌ Failed to create 3D model for {image_data['type']}")
                    
            except Exception as e:
                print(f"❌ Error converting {image_data['type']} to 3D: {str(e)}")
        
        print(f"✅ 3D conversion completed for job {job_id} - {len(models_3d)} models created")
        return models_3d

    async def _try_sync_generation(self, request_data: Dict) -> Optional[Dict]:
            """Try synchronous 3D generation (faster but may timeout)
            
            Args:
                request_data: Request parameters
                
            Returns:
                Model result or None
            """
            try:
                print("🚀 Trying synchronous 3D generation...")
                
                response = await self.client.post(
                    f"{self.base_url}/generate",
                    json=request_data
                )
                
                if response.status_code == 200:
                    # Direct binary response
                    model_data = response.content
                    return {
                        'model_data': model_data,
                        'format': request_data.get('type', 'glb'),
                        'method': 'synchronous',
                        'params': request_data
                    }
                else:
                    print(f"⚠️ Sync generation failed: {response.status_code} - {response.text}")
                    return None
                    
            except httpx.TimeoutException:
                print("⏰ Sync generation timed out, will try async...")
                return None
            except Exception as e:
                print(f"❌ Sync generation error: {str(e)}")
                return None

    async def _try_async_generation(self, request_data: Dict) -> Optional[Dict]:
        """Try asynchronous 3D generation (slower but more reliable)
        
        Args:
            request_data: Request parameters
            
        Returns:
            Model result or None
        """
        try:
            print("🔄 Starting asynchronous 3D generation...")
            
            # Start async task
            response = await self.client.post(
                f"{self.base_url}/send",
                json=request_data
            )
            
            if response.status_code != 200:
                print(f"❌ Failed to start async task: {response.status_code} - {response.text}")
                return None
            
            task_data = response.json()
            task_id = task_data.get('uid')
            
            if not task_id:
                print("❌ No task ID received")
                return None
            
            print(f"📋 Task started: {task_id}")
            
            # Poll for completion
            model_data = await self._poll_task_completion(task_id)
            
            if model_data:
                return {
                    'model_data': model_data,
                    'format': request_data.get('type', 'glb'),
                    'method': 'asynchronous',
                    'params': request_data,
                    'task_id': task_id
                }
            else:
                return None
                
        except Exception as e:
            print(f"❌ Async generation error: {str(e)}")
            return None

    async def _poll_task_completion(self, task_id: str) -> Optional[bytes]:
        """Poll task status until completion
        
        Args:
            task_id: Task identifier
            
        Returns:
            Model data bytes or None
        """
        max_attempts = self.max_retries
        attempt = 0
        
        while attempt < max_attempts:
            try:
                response = await self.client.get(f"{self.base_url}/status/{task_id}")
                
                if response.status_code != 200:
                    print(f"❌ Status check failed: {response.status_code}")
                    return None
                
                status_data = response.json()
                status = status_data.get('status')
                
                print(f"📊 Task {task_id} status: {status}")
                
                if status == 'completed':
                    # Get model data
                    model_base64 = status_data.get('model_base64')
                    if model_base64:
                        model_data = base64.b64decode(model_base64)
                        print(f"✅ Task {task_id} completed successfully")
                        return model_data
                    else:
                        print(f"❌ No model data in completed task {task_id}")
                        return None
                        
                elif status == 'failed':
                    error = status_data.get('error', 'Unknown error')
                    print(f"❌ Task {task_id} failed: {error}")
                    return None
                    
                elif status in ['queued', 'processing']:
                    # Still processing, wait and retry
                    await asyncio.sleep(self.retry_delay)
                    attempt += 1
                    continue
                    
                else:
                    print(f"❓ Unknown status for task {task_id}: {status}")
                    await asyncio.sleep(self.retry_delay)
                    attempt += 1
                    continue
                    
            except Exception as e:
                print(f"❌ Error checking task {task_id}: {str(e)}")
                attempt += 1
                await asyncio.sleep(self.retry_delay)
        
        print(f"⏰ Task {task_id} polling timed out after {max_attempts} attempts")
        return None

    async def _save_3d_model(self, model_data: bytes, image_data: Dict, models_dir: str, file_format: str) -> Optional[str]:
        """Save 3D model data to file
        
        Args:
            model_data: Binary model data
            image_data: Source image metadata
            models_dir: Directory to save models
            file_format: File format (glb, obj, etc.)
            
        Returns:
            Path to saved model file
        """
        try:
            # Generate filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            base_name = image_data['type']
            filename = f"{base_name}_3d_{timestamp}.{file_format}"
            model_path = os.path.join(models_dir, filename)
            
            # Save model data
            async with aiofiles.open(model_path, 'wb') as f:
                await f.write(model_data)
            
            print(f"💾 Saved 3D model: {model_path} ({len(model_data)} bytes)")
            return model_path
            
        except Exception as e:
            print(f"❌ Error saving 3D model: {str(e)}")
            return None

    async def _convert_single_image_to_3d(self, image_data: Dict, job_id: str, models_dir: str) -> Optional[Dict]:
        """Convert a single image to 3D model

        Args:
            image_data: Image metadata
            job_id: Job identifier
            models_dir: Directory to save 3D models

        Returns:
            3D model metadata
        """
        try:
            image_path = image_data['file_path']
            
            # Check if image file exists
            if not os.path.exists(image_path):
                print(f"❌ Image file not found: {image_path}")
                return None

            # Read and encode image
            async with aiofiles.open(image_path, 'rb') as f:
                image_bytes = await f.read()
            
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            # Fix: Remove the data URL prefix - API expects just the base64 string
            
            # Prepare request based on image type
            request_data = self._build_request_data(image_data, image_base64)
            
            # Try synchronous generation first (faster)
            model_result = await self._try_sync_generation(request_data)
            
            if not model_result:
                # Fallback to async generation
                model_result = await self._try_async_generation(request_data)
            
            if not model_result:
                return None

            # Save 3D model file
            model_path = await self._save_3d_model(
                model_data=model_result['model_data'],
                image_data=image_data,
                models_dir=models_dir,
                file_format=model_result['format']
            )
            
            if not model_path:
                return None

            # Create 3D model metadata
            model_metadata = {
                'type': image_data['type'],
                'source_image': image_data['file_path'],
                'source_image_type': image_data.get('type', 'unknown'),
                'model_path': model_path,
                'model_filename': os.path.basename(model_path),
                'model_format': model_result['format'],
                'model_url': f"/storage/processed/{job_id}/3d_models/{os.path.basename(model_path)}",
                'generation_method': model_result['method'],
                'generation_params': model_result['params'],
                'created_at': datetime.now().isoformat(),
                'file_size_bytes': os.path.getsize(model_path) if os.path.exists(model_path) else 0
            }
            
            return model_metadata
            
        except Exception as e:
            print(f"❌ Error in _convert_single_image_to_3d: {str(e)}")
            return None

    def _build_request_data(self, image_data: Dict, image_base64: str) -> Dict:
        """Build request data based on image type and settings"""
        
        # Base parameters with BACKGROUND REMOVAL ENABLED
        request_data = {
            "image": image_base64,
            "remove_background": True,  # ✅ ENABLE THIS
            "texture": True,  # Enable for better geometry
            "seed": settings.HUNYUAN3D_DEFAULT_SEED,
            "type": "glb"
        }
        
        image_type = image_data.get('type', '')
        
        if 'base_character' in image_type:
            # Optimized for main character
            request_data.update({
                "octree_resolution": 256,
                "num_inference_steps": 5,
                "guidance_scale": 5.0,
                "face_count": 40000, 
                "num_chunks": 8000
            })
        else:
            # Optimized for accessories (simpler geometry)
            request_data.update({
                "octree_resolution": 256,  # Lower resolution
                "num_inference_steps": 5,   # Fewer steps
                "guidance_scale": 5.0,      # Lower guidance
                "face_count": 40000,        # Much lower face count
                "num_chunks": 8000
            })
        
        return request_data

    async def health_check(self) -> bool:
        """Check if Hunyuan3D API is healthy
        
        Returns:
            True if API is responding
        """
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Hunyuan3D health check failed: {str(e)}")
            return False

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

    def __del__(self):
        """Cleanup on deletion"""
        try:
            asyncio.create_task(self.close())
        except:
            pass

