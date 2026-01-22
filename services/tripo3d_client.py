"""
Tripo3D API Client - Replaces Hunyuan3D for better texture quality
API Documentation: https://platform.tripo3d.ai/docs
"""
import httpx
import asyncio
import os
import logging
from typing import List, Dict, Optional
from datetime import datetime
import aiofiles
from config.settings import settings

logger = logging.getLogger(__name__)


class Tripo3DClient:
    """Client for Tripo3D image-to-3D generation API"""

    BASE_URL = "https://api.tripo3d.ai/v2/openapi"

    def __init__(self, api_key: str = None):
        """Initialize Tripo3D API client

        Args:
            api_key: Tripo3D API key. If not provided, uses TRIPO3D_API_KEY from settings.
        """
        self.api_key = api_key or getattr(settings, 'TRIPO3D_API_KEY', None)
        if not self.api_key:
            raise ValueError("TRIPO3D_API_KEY is required. Set it in environment or pass to constructor.")

        self.timeout = getattr(settings, 'TRIPO3D_TIMEOUT', 300)
        self.poll_interval = getattr(settings, 'TRIPO3D_POLL_INTERVAL', 5)
        self.max_poll_attempts = getattr(settings, 'TRIPO3D_MAX_POLL_ATTEMPTS', 120)

        # Model version - v2.5 is recommended for good quality
        self.model_version = getattr(settings, 'TRIPO3D_MODEL_VERSION', 'v2.5-20250123')

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )

        logger.info(f"Tripo3D client initialized - Model version: {self.model_version}")

    async def _upload_image(self, image_path: str) -> Optional[str]:
        """Upload image and get image token

        Args:
            image_path: Path to image file

        Returns:
            image_token or None if failed
        """
        try:
            async with aiofiles.open(image_path, 'rb') as f:
                image_data = await f.read()

            # Use multipart form upload
            files = {'file': (os.path.basename(image_path), image_data)}

            async with httpx.AsyncClient(timeout=60) as upload_client:
                response = await upload_client.post(
                    f"{self.BASE_URL}/upload",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files=files
                )

            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    token = data['data']['image_token']
                    logger.info(f"Image uploaded successfully: {token[:20]}...")
                    return token
                else:
                    logger.error(f"Upload failed: {data}")
                    return None
            else:
                logger.error(f"Upload failed with status {response.status_code}: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error uploading image: {e}")
            return None

    async def _create_task(self, image_token: str, image_type: str = "unknown") -> Optional[str]:
        """Create image-to-model generation task

        Args:
            image_token: Token from uploaded image
            image_type: Type of image (base_character, accessory_1, etc.)

        Returns:
            task_id or None if failed
        """
        try:
            request_data = {
                "type": "image_to_model",
                "model_version": self.model_version,
                "file": {
                    "type": "png",
                    "file_token": image_token
                },
                "texture": True,
                "pbr": True,
                "texture_quality": "detailed",  # 4K textures
                "texture_alignment": "original_image",  # Prioritize visual fidelity
                "geometry_quality": "detailed",  # Ultra mesh quality (v3.0+)
                "orientation": "align_image",  # Auto-rotate to align with original image
                "auto_size": False
            }

            # Adjust face count based on image type
            if "base_character" in image_type:
                request_data["face_limit"] = 80000  # Higher detail for characters
            else:
                request_data["face_limit"] = 50000  # Good detail for accessories

            response = await self.client.post(
                f"{self.BASE_URL}/task",
                json=request_data
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    task_id = data['data']['task_id']
                    logger.info(f"Task created: {task_id}")
                    return task_id
                else:
                    logger.error(f"Task creation failed: {data}")
                    return None
            else:
                logger.error(f"Task creation failed with status {response.status_code}: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error creating task: {e}")
            return None

    async def _retexture_model(self, original_task_id: str) -> Optional[str]:
        """Re-texture a model with enhanced 4K textures

        Args:
            original_task_id: Task ID from image_to_model

        Returns:
            New task_id for retexture task or None if failed
        """
        try:
            request_data = {
                "type": "texture_model",
                "original_model_task_id": original_task_id,
                "texture": True,
                "pbr": True,
                "texture_quality": "detailed",  # 4K textures
                "texture_alignment": "original_image",  # Match original image
                "model_version": self.model_version,
                "bake": True  # Bake textures for better quality
            }

            logger.info(f"Re-texturing model from task: {original_task_id}")

            response = await self.client.post(
                f"{self.BASE_URL}/task",
                json=request_data
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    task_id = data['data']['task_id']
                    logger.info(f"Retexture task created: {task_id}")
                    return task_id
                else:
                    logger.error(f"Retexture task creation failed: {data}")
                    return None
            else:
                logger.error(f"Retexture task failed with status {response.status_code}: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error creating retexture task: {e}")
            return None

    async def _poll_task(self, task_id: str) -> Optional[Dict]:
        """Poll task until completion

        Args:
            task_id: Task identifier

        Returns:
            Task output data or None if failed
        """
        attempts = 0

        while attempts < self.max_poll_attempts:
            try:
                response = await self.client.get(f"{self.BASE_URL}/task/{task_id}")

                if response.status_code != 200:
                    logger.error(f"Task poll failed: {response.status_code}")
                    return None

                data = response.json()
                if data.get('code') != 0:
                    logger.error(f"Task poll error: {data}")
                    return None

                task_data = data['data']
                status = task_data.get('status')
                progress = task_data.get('progress', 0)

                logger.info(f"Task {task_id}: {status} ({progress}%)")

                if status == 'success':
                    return task_data.get('output', {})
                elif status in ['failed', 'banned', 'cancelled', 'expired']:
                    logger.error(f"Task {task_id} ended with status: {status}")
                    return None
                elif status in ['queued', 'running']:
                    await asyncio.sleep(self.poll_interval)
                    attempts += 1
                else:
                    logger.warning(f"Unknown task status: {status}")
                    await asyncio.sleep(self.poll_interval)
                    attempts += 1

            except Exception as e:
                logger.error(f"Error polling task {task_id}: {e}")
                attempts += 1
                await asyncio.sleep(self.poll_interval)

        logger.error(f"Task {task_id} polling timed out after {attempts} attempts")
        return None

    async def _download_model(self, model_url: str, output_path: str) -> bool:
        """Download model from URL

        Args:
            model_url: URL to download model from
            output_path: Local path to save model

        Returns:
            True if successful
        """
        try:
            async with httpx.AsyncClient(timeout=120) as download_client:
                response = await download_client.get(model_url)

                if response.status_code == 200:
                    async with aiofiles.open(output_path, 'wb') as f:
                        await f.write(response.content)
                    logger.info(f"Model downloaded: {output_path} ({len(response.content)} bytes)")
                    return True
                else:
                    logger.error(f"Download failed: {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"Error downloading model: {e}")
            return False

    async def generate_3d_model(self, image_path: str, job_id: str) -> Dict:
        """Generate 3D model from a single image

        Args:
            image_path: Path to the image file
            job_id: Job identifier

        Returns:
            Dict with success status and model metadata
        """
        try:
            logger.info(f"Generating 3D model from: {image_path}")

            if not os.path.exists(image_path):
                return {
                    "success": False,
                    "error": f"Image file not found: {image_path}",
                    "image_path": image_path
                }

            # Determine image type
            filename = os.path.basename(image_path)
            image_type = "unknown"
            if "base_character" in filename:
                image_type = "base_character"
            elif "accessory" in filename:
                parts = filename.split('_')
                if len(parts) >= 2:
                    image_type = f"{parts[0]}_{parts[1]}"

            # Create image metadata
            image_metadata = {
                "type": image_type,
                "file_path": image_path,
                "filename": filename,
                "method": "tripo3d_api",
                "processed_at": datetime.now().isoformat()
            }

            # Convert to 3D
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
            logger.error(f"Error in generate_3d_model: {e}")
            return {
                "success": False,
                "error": str(e),
                "image_path": image_path,
                "processed_at": datetime.now().isoformat()
            }

    async def _process_single_image(self, image_data: Dict, job_id: str, models_dir: str) -> Optional[Dict]:
        """Process a single image through the full pipeline (upload -> generate -> retexture -> download)

        Args:
            image_data: Image metadata
            job_id: Job identifier
            models_dir: Directory to save models

        Returns:
            Model metadata with task_id, or dict with error key if failed
        """
        image_path = image_data.get('file_path') or image_data.get('processed_path')
        image_type = image_data.get('type', 'unknown')

        if not image_path:
            logger.error(f"[{image_type}] No file_path or processed_path in image_data")
            return {'type': image_type, 'error': 'No image path provided'}

        try:
            # Step 1: Upload image
            logger.info(f"[{image_type}] Uploading image...")
            image_token = await self._upload_image(image_path)
            if not image_token:
                logger.error(f"[{image_type}] Failed to upload image")
                return {'type': image_type, 'error': 'Failed to upload image'}

            # Step 2: Create generation task
            logger.info(f"[{image_type}] Creating generation task...")
            task_id = await self._create_task(image_token, image_type)
            if not task_id:
                logger.error(f"[{image_type}] Failed to create task")
                return {'type': image_type, 'error': 'Failed to create task - check credits/API key'}

            return {
                'type': image_type,
                'image_type': image_type,
                'image_path': image_path,
                'task_id': task_id,
                'models_dir': models_dir,
                'job_id': job_id
            }

        except Exception as e:
            logger.error(f"[{image_type}] Error in upload/create phase: {e}")
            return {'type': image_type, 'error': str(e)}

    async def _wait_and_retexture(self, task_info: Dict) -> Optional[Dict]:
        """Wait for initial model and start retexture

        Args:
            task_info: Task information from _process_single_image

        Returns:
            Updated task info with retexture task_id or None if failed
        """
        if not task_info:
            return None

        image_type = task_info['image_type']
        task_id = task_info['task_id']

        try:
            # Wait for initial model
            logger.info(f"[{image_type}] Waiting for initial model...")
            output = await self._poll_task(task_id)
            if not output:
                logger.error(f"[{image_type}] Initial model generation failed")
                return None

            task_info['initial_output'] = output

            # Start retexture
            logger.info(f"[{image_type}] Starting retexture...")
            retexture_task_id = await self._retexture_model(task_id)
            if retexture_task_id:
                task_info['retexture_task_id'] = retexture_task_id
            else:
                logger.warning(f"[{image_type}] Could not start retexture, will use original")

            return task_info

        except Exception as e:
            logger.error(f"[{image_type}] Error in wait/retexture phase: {e}")
            return None

    async def _wait_retexture_and_download(self, task_info: Dict) -> Optional[Dict]:
        """Wait for retexture and download final model

        Args:
            task_info: Task information with retexture_task_id

        Returns:
            Model metadata or None if failed
        """
        if not task_info:
            return None

        image_type = task_info['image_type']
        image_path = task_info['image_path']
        models_dir = task_info['models_dir']
        job_id = task_info['job_id']
        task_id = task_info['task_id']
        output = task_info.get('initial_output', {})

        try:
            # Wait for retexture if started
            if 'retexture_task_id' in task_info:
                logger.info(f"[{image_type}] Waiting for retexture...")
                retexture_output = await self._poll_task(task_info['retexture_task_id'])
                if retexture_output:
                    output = retexture_output
                    task_id = task_info['retexture_task_id']
                    logger.info(f"[{image_type}] Using retextured model")
                else:
                    logger.warning(f"[{image_type}] Retexture failed, using original model")

            # Download model
            model_url = output.get('model') or output.get('pbr_model')
            if not model_url:
                logger.error(f"[{image_type}] No model URL in output")
                return None

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            model_filename = f"{image_type}_3d_{timestamp}.glb"
            model_path = os.path.join(models_dir, model_filename)

            logger.info(f"[{image_type}] Downloading model...")
            if not await self._download_model(model_url, model_path):
                logger.error(f"[{image_type}] Failed to download model")
                return None

            # Create metadata
            model_metadata = {
                'type': image_type,
                'source_image': image_path,
                'source_image_type': image_type,
                'model_path': model_path,
                'model_filename': model_filename,
                'model_format': 'glb',
                'model_url': f"/storage/processed/{job_id}/3d_models/{model_filename}",
                'generation_method': 'tripo3d_api',
                'task_id': task_id,
                'created_at': datetime.now().isoformat(),
                'file_size_bytes': os.path.getsize(model_path) if os.path.exists(model_path) else 0
            }

            logger.info(f"[{image_type}] 3D model created successfully")
            return model_metadata

        except Exception as e:
            logger.error(f"[{image_type}] Error in download phase: {e}")
            return None

    async def convert_images_to_3d(self, job_id: str, processed_images: List[Dict]) -> List[Dict]:
        """Convert all processed images to 3D models (PARALLEL processing)

        Args:
            job_id: Job identifier
            processed_images: List of processed image metadata

        Returns:
            List of 3D model metadata
        """
        # Create 3D models directory
        models_dir = os.path.join(settings.PROCESSED_PATH, job_id, "3d_models")
        os.makedirs(models_dir, exist_ok=True)

        logger.info(f"Converting {len(processed_images)} images to 3D for job {job_id} (PARALLEL)")
        for i, img in enumerate(processed_images):
            logger.info(f"  [{i+1}] {img.get('type')}: {img.get('file_path') or img.get('processed_path')}")

        # Phase 1: Upload all images and create tasks in parallel
        logger.info("Phase 1: Uploading images and creating tasks...")
        upload_tasks = [
            self._process_single_image(img_data, job_id, models_dir)
            for img_data in processed_images
        ]
        raw_results = await asyncio.gather(*upload_tasks, return_exceptions=True)

        # Log and filter Phase 1 results
        task_infos = []
        for i, result in enumerate(raw_results):
            img_type = processed_images[i].get('type', f'image_{i}')
            if isinstance(result, Exception):
                logger.error(f"[{img_type}] Phase 1 exception: {result}")
            elif result is None:
                logger.error(f"[{img_type}] Phase 1 returned None")
            elif not result.get('task_id'):
                logger.error(f"[{img_type}] Phase 1 no task_id: {result.get('error', 'unknown error')}")
            else:
                task_infos.append(result)
        logger.info(f"Phase 1 complete: {len(task_infos)}/{len(processed_images)} tasks created")

        if not task_infos:
            logger.error("No tasks created in Phase 1 - aborting")
            return []

        # Phase 2: Wait for initial models and start retexture in parallel
        logger.info("Phase 2: Waiting for initial models and starting retexture...")
        retexture_tasks = [
            self._wait_and_retexture(task_info)
            for task_info in task_infos
        ]
        raw_results = await asyncio.gather(*retexture_tasks, return_exceptions=True)

        # Log and filter Phase 2 results
        task_infos_2 = []
        for i, result in enumerate(raw_results):
            img_type = task_infos[i].get('type', f'task_{i}')
            if isinstance(result, Exception):
                logger.error(f"[{img_type}] Phase 2 exception: {result}")
            elif result is None:
                logger.error(f"[{img_type}] Phase 2 returned None")
            else:
                task_infos_2.append(result)
        logger.info(f"Phase 2 complete: {len(task_infos_2)} models ready for retexture")

        if not task_infos_2:
            logger.error("No models ready after Phase 2 - aborting")
            return []

        # Phase 3: Wait for retexture and download all models in parallel
        logger.info("Phase 3: Waiting for retexture and downloading models...")
        download_tasks = [
            self._wait_retexture_and_download(task_info)
            for task_info in task_infos_2
        ]
        raw_results = await asyncio.gather(*download_tasks, return_exceptions=True)

        # Log and filter Phase 3 results
        models_3d = []
        for i, result in enumerate(raw_results):
            img_type = task_infos_2[i].get('type', f'model_{i}')
            if isinstance(result, Exception):
                logger.error(f"[{img_type}] Phase 3 exception: {result}")
            elif result is None:
                logger.error(f"[{img_type}] Phase 3 returned None")
            else:
                models_3d.append(result)

        logger.info(f"3D conversion completed for job {job_id} - {len(models_3d)}/{len(processed_images)} models created")
        return models_3d

    async def health_check(self) -> bool:
        """Check if Tripo3D API is accessible

        Returns:
            True if API is responding
        """
        try:
            # Try to get a non-existent task - if we get 404, API is working
            response = await self.client.get(f"{self.BASE_URL}/task/test-health-check")
            # 404 means API is working, just task not found
            # 401 means auth issue
            # 200 would be unexpected but OK
            if response.status_code in [200, 404]:
                return True
            elif response.status_code == 401:
                logger.error("Tripo3D health check failed: Invalid API key")
                return False
            else:
                logger.warning(f"Tripo3D health check: status {response.status_code}")
                return response.status_code < 500

        except Exception as e:
            logger.error(f"Tripo3D health check failed: {e}")
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
