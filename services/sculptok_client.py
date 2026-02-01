"""
Sculptok API Client for 2.5D STL Generation

This service handles:
1. Image upload to Sculptok
2. Background removal (replaces ComfyUI)
3. 2.5D STL generation with depth map
4. Status polling and result download

API Documentation: https://api.sculptok.com
"""

import os
import asyncio
import aiohttp
import logging
from typing import Dict, Optional, Tuple, List
from datetime import datetime
from config.settings import settings

# Configure detailed logging for testing
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create a detailed formatter for test logging
detailed_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
)


class SculptokClient:
    """Client for Sculptok API - 2.5D STL generation from images"""

    def __init__(self):
        self.api_key = settings.SCULPTOK_API_KEY
        self.base_url = settings.SCULPTOK_API_BASE_URL
        self.timeout = settings.SCULPTOK_TIMEOUT
        self.poll_interval = settings.SCULPTOK_POLL_INTERVAL
        self.max_poll_attempts = settings.SCULPTOK_MAX_POLL_ATTEMPTS

        # STL generation parameters
        self.width_mm = settings.SCULPTOK_WIDTH_MM
        self.min_thickness = settings.SCULPTOK_MIN_THICKNESS
        self.max_thickness = settings.SCULPTOK_MAX_THICKNESS
        self.invert = settings.SCULPTOK_INVERT
        self.scale_image = settings.SCULPTOK_SCALE_IMAGE

        # Background removal parameters
        self.bg_remove_type = settings.SCULPTOK_BG_REMOVE_TYPE
        self.hd_fix = settings.SCULPTOK_HD_FIX

        if not self.api_key:
            logger.warning("⚠️ SCULPTOK_API_KEY not set - API calls will fail")

        logger.info(f"🎨 SculptokClient initialized")
        logger.info(f"   Base URL: {self.base_url}")
        logger.info(f"   API Key: {'✅ Set' if self.api_key else '❌ Missing'}")
        logger.info(f"   STL Width: {self.width_mm}mm")
        logger.info(f"   Thickness: {self.min_thickness}mm - {self.max_thickness}mm")

    def _get_headers(self, content_type: str = "application/json") -> Dict[str, str]:
        """Get headers for API requests"""
        return {
            "apikey": self.api_key,
            "Content-Type": content_type
        }

    async def upload_image(self, image_path: str) -> Dict:
        """
        Step 1: Upload image to Sculptok server

        Args:
            image_path: Local path to image file

        Returns:
            Dict with 'success', 'image_url' or 'error'
        """
        logger.info(f"📤 [UPLOAD] Starting image upload: {image_path}")

        if not os.path.exists(image_path):
            logger.error(f"❌ [UPLOAD] File not found: {image_path}")
            return {"success": False, "error": f"File not found: {image_path}"}

        file_size = os.path.getsize(image_path)
        logger.debug(f"   File size: {file_size / 1024:.2f} KB")

        url = f"{self.base_url}/image/upload"
        logger.debug(f"   URL: {url}")

        try:
            async with aiohttp.ClientSession() as session:
                # Prepare multipart form data
                data = aiohttp.FormData()
                data.add_field(
                    'file',
                    open(image_path, 'rb'),
                    filename=os.path.basename(image_path),
                    content_type='image/png'
                )

                headers = {"apikey": self.api_key}
                logger.debug(f"   Headers: {headers}")

                async with session.post(url, data=data, headers=headers, timeout=self.timeout) as response:
                    status_code = response.status
                    response_text = await response.text()

                    logger.info(f"   Response Status: {status_code}")
                    logger.debug(f"   Response Body: {response_text}")

                    if status_code == 200:
                        try:
                            result = await response.json()
                            logger.debug(f"   Parsed JSON: {result}")

                            if result.get("code") == 0:
                                image_url = result.get("data", {}).get("src")
                                logger.info(f"✅ [UPLOAD] Success! Image URL: {image_url}")
                                return {
                                    "success": True,
                                    "image_url": image_url,
                                    "raw_response": result
                                }
                            else:
                                error_msg = result.get("msg", "Unknown error")
                                logger.error(f"❌ [UPLOAD] API Error: {error_msg}")
                                return {
                                    "success": False,
                                    "error": error_msg,
                                    "raw_response": result
                                }
                        except Exception as e:
                            logger.error(f"❌ [UPLOAD] JSON parse error: {e}")
                            return {
                                "success": False,
                                "error": f"JSON parse error: {e}",
                                "raw_response": response_text
                            }
                    else:
                        logger.error(f"❌ [UPLOAD] HTTP Error {status_code}: {response_text}")
                        return {
                            "success": False,
                            "error": f"HTTP {status_code}: {response_text}"
                        }

        except asyncio.TimeoutError:
            logger.error(f"❌ [UPLOAD] Timeout after {self.timeout}s")
            return {"success": False, "error": "Upload timeout"}
        except Exception as e:
            logger.error(f"❌ [UPLOAD] Exception: {e}")
            return {"success": False, "error": str(e)}

    async def remove_background(self, image_url: str, hd_fix: bool = None, remove_type: str = None) -> Dict:
        """
        Step 2: Submit background removal task

        Args:
            image_url: URL from upload_image response
            hd_fix: Enable HD restoration (default from settings)
            remove_type: "anime" or "general" (default from settings)

        Returns:
            Dict with 'success', 'prompt_id' or 'error'
        """
        logger.info(f"🖼️ [BG_REMOVE] Starting background removal")
        logger.debug(f"   Image URL: {image_url}")

        hd_fix = hd_fix if hd_fix is not None else self.hd_fix
        remove_type = remove_type or self.bg_remove_type

        url = f"{self.base_url}/draw/hd/prompt"
        payload = {
            "imageUrl": image_url,
            "hdFix": "true" if hd_fix else "false",
            "removeBack": remove_type
        }

        logger.debug(f"   URL: {url}")
        logger.debug(f"   Payload: {payload}")

        try:
            async with aiohttp.ClientSession() as session:
                headers = self._get_headers()
                logger.debug(f"   Headers: {headers}")

                async with session.post(url, json=payload, headers=headers, timeout=self.timeout) as response:
                    status_code = response.status
                    response_text = await response.text()

                    logger.info(f"   Response Status: {status_code}")
                    logger.debug(f"   Response Body: {response_text}")

                    if status_code == 200:
                        result = await response.json()
                        logger.debug(f"   Parsed JSON: {result}")

                        if result.get("code") == 0:
                            prompt_id = result.get("data", {}).get("promptId")
                            logger.info(f"✅ [BG_REMOVE] Task submitted! Prompt ID: {prompt_id}")
                            return {
                                "success": True,
                                "prompt_id": prompt_id,
                                "raw_response": result
                            }
                        else:
                            error_msg = result.get("msg", "Unknown error")
                            logger.error(f"❌ [BG_REMOVE] API Error: {error_msg}")
                            return {
                                "success": False,
                                "error": error_msg,
                                "raw_response": result
                            }
                    else:
                        logger.error(f"❌ [BG_REMOVE] HTTP Error {status_code}")
                        return {"success": False, "error": f"HTTP {status_code}"}

        except Exception as e:
            logger.error(f"❌ [BG_REMOVE] Exception: {e}")
            return {"success": False, "error": str(e)}

    async def generate_depth_map(
        self,
        image_url: str,
        style: str = "normal",
        hd_fix: str = "auto",
        optimal_size: str = "true",
        ext_info: str = "8bit",
        version: str = "1.5",
        draw_hd: str = "2k"
    ) -> Dict:
        """
        Step 3: Generate depth map from image

        Args:
            image_url: URL from upload_image or bg_removal response
            style: Type of image - normal, portrait, sketch, pro (default: normal)
            hd_fix: AI Optimization - auto or manual (default: auto)
            optimal_size: Enable optimal size - true or false (default: true)
            ext_info: Bit depth - 8bit, 16bit, exr (default: 8bit)
            version: Model version for pro style - 1.0 or 1.5 (default: 1.5)
            draw_hd: Resolution for pro style - 2k or 4k (default: 2k)

        Returns:
            Dict with 'success', 'prompt_id' or 'error'
        """
        logger.info(f"🎨 [DEPTH_MAP] Starting depth map generation")
        logger.info(f"   Style: {style}, HD Fix: {hd_fix}")
        logger.debug(f"   Image URL: {image_url}")

        url = f"{self.base_url}/draw/prompt"
        payload = {
            "imageUrl": image_url,
            "style": style,
            "hd_fix": hd_fix,
            "optimal_size": optimal_size,
            "extInfo": ext_info
        }

        # Add pro-specific options if using pro style
        if style == "pro":
            payload["version"] = version
            payload["draw_hd"] = draw_hd

        logger.debug(f"   URL: {url}")
        logger.debug(f"   Payload: {payload}")

        try:
            async with aiohttp.ClientSession() as session:
                headers = self._get_headers()

                async with session.post(url, json=payload, headers=headers, timeout=self.timeout) as response:
                    status_code = response.status
                    response_text = await response.text()

                    logger.info(f"   Response Status: {status_code}")
                    logger.debug(f"   Response Body: {response_text}")

                    if status_code == 200:
                        result = await response.json()
                        logger.debug(f"   Parsed JSON: {result}")

                        if result.get("code") == 0:
                            prompt_id = result.get("data", {}).get("promptId")
                            logger.info(f"✅ [DEPTH_MAP] Task submitted! Prompt ID: {prompt_id}")
                            return {
                                "success": True,
                                "prompt_id": prompt_id,
                                "raw_response": result
                            }
                        else:
                            error_msg = result.get("msg", "Unknown error")
                            logger.error(f"❌ [DEPTH_MAP] API Error: {error_msg}")
                            return {
                                "success": False,
                                "error": error_msg,
                                "raw_response": result
                            }
                    else:
                        logger.error(f"❌ [DEPTH_MAP] HTTP Error {status_code}")
                        return {"success": False, "error": f"HTTP {status_code}"}

        except Exception as e:
            logger.error(f"❌ [DEPTH_MAP] Exception: {e}")
            return {"success": False, "error": str(e)}

    async def submit_stl(
        self,
        image_url: str,
        width_mm: float = None,
        min_thickness: float = None,
        max_thickness: float = None,
        invert: bool = None,
        scale_image: int = None
    ) -> Dict:
        """
        Step 3: Submit STL generation task

        Args:
            image_url: URL of image (from upload or bg removal result)
            width_mm: Output width in mm (40-240)
            min_thickness: Min thickness for brightest area (0.4-8)
            max_thickness: Max thickness for darkest area (0.4-25)
            invert: Invert grayscale
            scale_image: Scale percent (0-100)

        Returns:
            Dict with 'success', 'prompt_id' or 'error'
        """
        logger.info(f"🔧 [STL] Starting STL generation task")
        logger.debug(f"   Image URL: {image_url}")

        # Use defaults from settings if not provided
        width_mm = width_mm or self.width_mm
        min_thickness = min_thickness or self.min_thickness
        max_thickness = max_thickness or self.max_thickness
        invert = invert if invert is not None else self.invert
        scale_image = scale_image if scale_image is not None else self.scale_image

        url = f"{self.base_url}/draw/stl/prompt"
        payload = {
            "image_url": image_url,
            "width_mm": width_mm,
            "min_thickness": min_thickness,
            "max_thickness": max_thickness,
            "invert": invert,
            "scale_image": scale_image
        }

        logger.info(f"   Parameters:")
        logger.info(f"     - Width: {width_mm}mm")
        logger.info(f"     - Thickness: {min_thickness}mm - {max_thickness}mm")
        logger.info(f"     - Invert: {invert}")
        logger.info(f"     - Scale: {scale_image}%")
        logger.debug(f"   URL: {url}")
        logger.debug(f"   Payload: {payload}")

        try:
            async with aiohttp.ClientSession() as session:
                headers = self._get_headers()

                async with session.post(url, json=payload, headers=headers, timeout=self.timeout) as response:
                    status_code = response.status
                    response_text = await response.text()

                    logger.info(f"   Response Status: {status_code}")
                    logger.debug(f"   Response Body: {response_text}")

                    if status_code == 200:
                        result = await response.json()
                        logger.debug(f"   Parsed JSON: {result}")

                        if result.get("code") == 0:
                            prompt_id = result.get("data", {}).get("promptId")
                            logger.info(f"✅ [STL] Task submitted! Prompt ID: {prompt_id}")
                            return {
                                "success": True,
                                "prompt_id": prompt_id,
                                "raw_response": result
                            }
                        else:
                            error_msg = result.get("msg", "Unknown error")
                            logger.error(f"❌ [STL] API Error: {error_msg}")
                            return {
                                "success": False,
                                "error": error_msg,
                                "raw_response": result
                            }
                    else:
                        logger.error(f"❌ [STL] HTTP Error {status_code}")
                        return {"success": False, "error": f"HTTP {status_code}"}

        except Exception as e:
            logger.error(f"❌ [STL] Exception: {e}")
            return {"success": False, "error": str(e)}

    async def get_status(self, prompt_id: str) -> Dict:
        """
        Step 4: Get task status and results

        Args:
            prompt_id: The promptId from submit task

        Returns:
            Dict with status info and result URLs when complete
        """
        logger.debug(f"🔍 [STATUS] Checking status for: {prompt_id}")

        url = f"{self.base_url}/draw/prompt"
        params = {"uuid": prompt_id}

        try:
            async with aiohttp.ClientSession() as session:
                headers = self._get_headers()

                async with session.get(url, params=params, headers=headers, timeout=60) as response:
                    status_code = response.status
                    response_text = await response.text()

                    logger.debug(f"   Response Status: {status_code}")
                    logger.debug(f"   Response Body: {response_text[:500]}...")  # Truncate for logging

                    if status_code == 200:
                        result = await response.json()

                        if result.get("code") == 0:
                            data = result.get("data", {})
                            status = data.get("status")
                            position = data.get("position", 0)
                            img_records = data.get("imgRecords", [])
                            current_step = data.get("currentStep", 0)

                            logger.debug(f"   Status: {status}, Step: {current_step}, Position: {position}")
                            logger.debug(f"   imgRecords count: {len(img_records)}")

                            # Log all imgRecords for debugging
                            if img_records:
                                logger.info(f"   📦 imgRecords ({len(img_records)} items):")
                                for i, record in enumerate(img_records):
                                    logger.info(f"      [{i}]: {record}")

                            return {
                                "success": True,
                                "status": status,
                                "position": position,
                                "current_step": current_step,
                                "img_records": img_records,
                                "up_image_url": data.get("upImageUrl"),
                                "prompt_id": data.get("promptId"),
                                "raw_response": result
                            }
                        else:
                            error_msg = result.get("msg", "Unknown error")
                            logger.error(f"❌ [STATUS] API Error: {error_msg}")
                            return {"success": False, "error": error_msg}
                    else:
                        logger.error(f"❌ [STATUS] HTTP Error {status_code}")
                        return {"success": False, "error": f"HTTP {status_code}"}

        except Exception as e:
            logger.error(f"❌ [STATUS] Exception: {e}")
            return {"success": False, "error": str(e)}

    async def wait_for_completion(self, prompt_id: str, task_type: str = "task") -> Dict:
        """
        Poll for task completion

        Args:
            prompt_id: The promptId to poll
            task_type: Description for logging

        Returns:
            Final status with results
        """
        logger.info(f"⏳ [POLL] Waiting for {task_type} completion: {prompt_id}")

        for attempt in range(self.max_poll_attempts):
            result = await self.get_status(prompt_id)

            if not result.get("success"):
                logger.error(f"❌ [POLL] Status check failed: {result.get('error')}")
                return result

            status = result.get("status")
            position = result.get("position", 0)

            # Status 2 = success/completed (status 0 might be queued/pending)
            # Check for completion: status 2 OR (status 0 with imgRecords)
            if status == 2 or (status == 0 and result.get("img_records")):
                img_records = result.get("img_records", [])
                if img_records:
                    logger.info(f"✅ [POLL] {task_type} completed with {len(img_records)} outputs!")
                else:
                    logger.warning(f"⚠️ [POLL] {task_type} status={status} but NO outputs (imgRecords empty)!")
                    logger.warning(f"   Full response: {result.get('raw_response')}")
                return result

            # Status 0 without imgRecords = still processing or queued
            if status == 0:
                logger.debug(f"   Status 0 without outputs - still processing...")

            # Log progress
            if attempt % 6 == 0:  # Log every 30 seconds (6 * 5s interval)
                logger.info(f"   ⏳ Attempt {attempt + 1}/{self.max_poll_attempts} - Status: {status}, Position: {position}")

            await asyncio.sleep(self.poll_interval)

        logger.error(f"❌ [POLL] Timeout waiting for {task_type}")
        return {"success": False, "error": "Polling timeout"}

    async def download_file(self, url: str, output_path: str) -> Dict:
        """
        Download a file from URL

        Args:
            url: URL to download
            output_path: Local path to save file

        Returns:
            Dict with success status
        """
        logger.info(f"📥 [DOWNLOAD] Downloading: {url}")
        logger.debug(f"   Output: {output_path}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=120) as response:
                    if response.status == 200:
                        # Ensure directory exists
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)

                        with open(output_path, 'wb') as f:
                            while True:
                                chunk = await response.content.read(8192)
                                if not chunk:
                                    break
                                f.write(chunk)

                        file_size = os.path.getsize(output_path)
                        logger.info(f"✅ [DOWNLOAD] Saved: {output_path} ({file_size / 1024:.2f} KB)")
                        return {"success": True, "path": output_path, "size": file_size}
                    else:
                        logger.error(f"❌ [DOWNLOAD] HTTP Error {response.status}")
                        return {"success": False, "error": f"HTTP {response.status}"}

        except Exception as e:
            logger.error(f"❌ [DOWNLOAD] Exception: {e}")
            return {"success": False, "error": str(e)}

    async def process_image_to_stl(
        self,
        image_path: str,
        output_dir: str,
        image_name: str = "model",
        width_mm: float = None,
        skip_bg_removal: bool = False
    ) -> Dict:
        """
        Full pipeline: Upload -> Background Removal -> STL Generation -> Download

        Args:
            image_path: Local path to input image
            output_dir: Directory to save outputs
            image_name: Base name for output files
            width_mm: Override width in mm
            skip_bg_removal: Skip background removal step

        Returns:
            Dict with all results including STL and depth image paths
        """
        logger.info(f"🚀 [PIPELINE] Starting full Sculptok pipeline")
        logger.info(f"   Input: {image_path}")
        logger.info(f"   Output Dir: {output_dir}")
        logger.info(f"   Name: {image_name}")
        logger.info(f"   Skip BG Removal: {skip_bg_removal}")

        os.makedirs(output_dir, exist_ok=True)
        results = {
            "success": False,
            "steps": {},
            "outputs": {}
        }

        # Step 1: Upload image
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 1: Upload Image")
        logger.info(f"{'='*60}")

        upload_result = await self.upload_image(image_path)
        results["steps"]["upload"] = upload_result

        if not upload_result.get("success"):
            logger.error(f"Pipeline failed at upload step")
            return results

        image_url = upload_result.get("image_url")

        # Step 2: Background removal (optional)
        if not skip_bg_removal:
            logger.info(f"\n{'='*60}")
            logger.info(f"STEP 2: Background Removal")
            logger.info(f"{'='*60}")

            bg_result = await self.remove_background(image_url)
            results["steps"]["background_removal"] = bg_result

            if not bg_result.get("success"):
                logger.error(f"Pipeline failed at background removal step")
                return results

            # Wait for background removal to complete
            bg_complete = await self.wait_for_completion(
                bg_result.get("prompt_id"),
                "Background Removal"
            )
            results["steps"]["background_removal_complete"] = bg_complete

            if not bg_complete.get("success"):
                logger.error(f"Pipeline failed waiting for background removal")
                return results

            # Get the processed image URL from imgRecords
            img_records = bg_complete.get("img_records", [])
            if img_records:
                # Use the first image record as the bg-removed image
                image_url = img_records[0]
                logger.info(f"   Using BG-removed image: {image_url}")

                # Download the bg-removed image for reference
                bg_output_path = os.path.join(output_dir, f"{image_name}_nobg.png")
                await self.download_file(image_url, bg_output_path)
                results["outputs"]["nobg_image"] = bg_output_path

        # Step 3: Generate Depth Map
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 3: Generate Depth Map")
        logger.info(f"{'='*60}")
        logger.info(f"   Using image URL: {image_url}")

        depth_result = await self.generate_depth_map(
            image_url,
            style="normal",  # normal, portrait, sketch, pro
            hd_fix="auto"
        )
        results["steps"]["depth_map_submit"] = depth_result

        if not depth_result.get("success"):
            logger.error(f"Pipeline failed at depth map generation step")
            return results

        # Wait for depth map generation to complete
        depth_complete = await self.wait_for_completion(
            depth_result.get("prompt_id"),
            "Depth Map Generation"
        )
        results["steps"]["depth_map_complete"] = depth_complete

        if not depth_complete.get("success"):
            logger.error(f"Pipeline failed waiting for depth map generation")
            return results

        # Get the depth map URL from imgRecords
        depth_img_records = depth_complete.get("img_records", [])
        if not depth_img_records:
            logger.error(f"❌ No depth map generated!")
            return results

        # The first imgRecord should be the depth map
        depth_map_url = depth_img_records[0] if isinstance(depth_img_records[0], str) else depth_img_records[0].get("url", "")
        logger.info(f"   Depth map URL: {depth_map_url}")

        # Download the depth map for reference
        depth_output_path = os.path.join(output_dir, f"{image_name}_depth.png")
        await self.download_file(depth_map_url, depth_output_path)
        results["outputs"]["depth_image"] = depth_output_path

        # Step 4: Submit STL generation using depth map
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 4: STL Generation")
        logger.info(f"{'='*60}")
        logger.info(f"   Using depth map URL: {depth_map_url}")

        stl_result = await self.submit_stl(depth_map_url, width_mm=width_mm)
        results["steps"]["stl_submit"] = stl_result

        if not stl_result.get("success"):
            logger.error(f"Pipeline failed at STL submission step")
            return results

        # Wait for STL generation to complete
        stl_complete = await self.wait_for_completion(
            stl_result.get("prompt_id"),
            "STL Generation"
        )
        results["steps"]["stl_complete"] = stl_complete

        if not stl_complete.get("success"):
            logger.error(f"Pipeline failed waiting for STL generation")
            return results

        # Step 5: Download results
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 5: Download Results")
        logger.info(f"{'='*60}")

        img_records = stl_complete.get("img_records", [])
        logger.info(f"   Found {len(img_records)} output files")

        # Log the full img_records for debugging
        if not img_records:
            logger.warning(f"   ⚠️ imgRecords is empty! Checking raw response...")
            raw = stl_complete.get("raw_response", {}).get("data", {})
            logger.warning(f"   Raw data keys: {raw.keys() if isinstance(raw, dict) else type(raw)}")
            logger.warning(f"   Raw data: {raw}")

        # Categorize and download outputs
        for i, record in enumerate(img_records):
            # Handle both string URLs and object format
            if isinstance(record, str):
                url = record
            elif isinstance(record, dict):
                url = record.get("url") or record.get("imgUrl") or record.get("fileUrl") or str(record)
                logger.info(f"   imgRecord[{i}] is dict with keys: {record.keys()}")
            else:
                logger.warning(f"   imgRecord[{i}] has unexpected type: {type(record)}")
                continue
            logger.info(f"   Processing imgRecord[{i}]: {url}")

            # Determine file type from URL
            if url.endswith('.stl'):
                output_path = os.path.join(output_dir, f"{image_name}.stl")
                download_result = await self.download_file(url, output_path)
                if download_result.get("success"):
                    results["outputs"]["stl"] = output_path
                    results["outputs"]["stl_url"] = url
            elif 'depth' in url.lower() or i == 1:  # Assume second item might be depth
                output_path = os.path.join(output_dir, f"{image_name}_depth.png")
                download_result = await self.download_file(url, output_path)
                if download_result.get("success"):
                    results["outputs"]["depth"] = output_path
                    results["outputs"]["depth_url"] = url
            else:
                # Download as generic output
                ext = os.path.splitext(url)[1] or '.png'
                output_path = os.path.join(output_dir, f"{image_name}_output_{i}{ext}")
                download_result = await self.download_file(url, output_path)
                if download_result.get("success"):
                    results["outputs"][f"output_{i}"] = output_path

        # Mark success if we have at least some outputs
        if results["outputs"]:
            results["success"] = True
            logger.info(f"\n✅ [PIPELINE] Complete!")
            logger.info(f"   Outputs: {list(results['outputs'].keys())}")
        else:
            logger.error(f"❌ [PIPELINE] No outputs downloaded")

        return results

    async def process_image_to_depth_map(
        self,
        image_path: str,
        output_dir: str,
        image_name: str = "model",
        skip_bg_removal: bool = False,
        style: str = "pro",
        version: str = "1.5",
        draw_hd: str = "4k",
        ext_info: str = "16bit"
    ) -> Dict:
        """
        Depth Map Only Pipeline: Upload -> Background Removal -> Depth Map -> Download

        This is the new pipeline for Blender Starter Pack - we only need depth maps,
        Blender handles the final STL generation.

        Args:
            image_path: Local path to input image
            output_dir: Directory to save outputs
            image_name: Base name for output files
            skip_bg_removal: Skip background removal step
            style: Depth map style - normal, portrait, sketch, pro (default: pro)
            version: Model version for pro style - 1.0 or 1.5 (default: 1.5)
            draw_hd: Resolution for pro style - 2k or 4k (default: 4k)
            ext_info: Bit depth - 8bit, 16bit, exr (default: 16bit)

        Returns:
            Dict with results including depth map path
        """
        logger.info(f"🚀 [DEPTH_PIPELINE] Starting depth map pipeline")
        logger.info(f"   Input: {image_path}")
        logger.info(f"   Output Dir: {output_dir}")
        logger.info(f"   Name: {image_name}")
        logger.info(f"   Skip BG Removal: {skip_bg_removal}")
        logger.info(f"   Quality: style={style}, version={version}, draw_hd={draw_hd}, ext_info={ext_info}")

        os.makedirs(output_dir, exist_ok=True)
        results = {
            "success": False,
            "steps": {},
            "outputs": {}
        }

        try:
            # Step 1: Upload image
            logger.info(f"\n{'='*60}")
            logger.info(f"STEP 1: Upload Image")
            logger.info(f"{'='*60}")

            upload_result = await self.upload_image(image_path)
            results["steps"]["upload"] = upload_result

            if not upload_result.get("success"):
                logger.error(f"❌ [DEPTH_PIPELINE] Failed at upload step: {upload_result.get('error')}")
                results["error"] = f"Upload failed: {upload_result.get('error')}"
                return results

            image_url = upload_result.get("image_url")
            logger.info(f"   ✅ Uploaded: {image_url}")

            # Step 2: Background removal (optional)
            if not skip_bg_removal:
                logger.info(f"\n{'='*60}")
                logger.info(f"STEP 2: Background Removal")
                logger.info(f"{'='*60}")

                bg_result = await self.remove_background(image_url)
                results["steps"]["background_removal"] = bg_result

                if not bg_result.get("success"):
                    logger.error(f"❌ [DEPTH_PIPELINE] Failed at background removal: {bg_result.get('error')}")
                    results["error"] = f"Background removal failed: {bg_result.get('error')}"
                    return results

                # Wait for background removal to complete
                bg_complete = await self.wait_for_completion(
                    bg_result.get("prompt_id"),
                    "Background Removal"
                )
                results["steps"]["background_removal_complete"] = bg_complete

                if not bg_complete.get("success"):
                    logger.error(f"❌ [DEPTH_PIPELINE] Failed waiting for background removal")
                    results["error"] = "Background removal timeout or failed"
                    return results

                # Get the processed image URL from imgRecords
                img_records = bg_complete.get("img_records", [])
                if img_records:
                    image_url = img_records[0]
                    logger.info(f"   ✅ BG removed: {image_url}")

                    # Download the bg-removed image
                    nobg_output_path = os.path.join(output_dir, f"{image_name}_nobg.png")
                    await self.download_file(image_url, nobg_output_path)
                    results["outputs"]["nobg_image"] = nobg_output_path
            else:
                logger.info(f"   ⏭️ Skipping background removal")

            # Step 3: Generate Depth Map (HIGH QUALITY)
            logger.info(f"\n{'='*60}")
            logger.info(f"STEP 3: Generate Depth Map (High Quality)")
            logger.info(f"{'='*60}")
            logger.info(f"   Image URL: {image_url}")
            logger.info(f"   Settings: style={style}, version={version}, draw_hd={draw_hd}, ext_info={ext_info}")

            depth_result = await self.generate_depth_map(
                image_url,
                style=style,
                hd_fix="auto",
                optimal_size="true",
                ext_info=ext_info,
                version=version,
                draw_hd=draw_hd
            )
            results["steps"]["depth_map_submit"] = depth_result

            if not depth_result.get("success"):
                logger.error(f"❌ [DEPTH_PIPELINE] Failed at depth map generation: {depth_result.get('error')}")
                results["error"] = f"Depth map generation failed: {depth_result.get('error')}"
                return results

            # Wait for depth map generation to complete
            depth_complete = await self.wait_for_completion(
                depth_result.get("prompt_id"),
                "Depth Map Generation"
            )
            results["steps"]["depth_map_complete"] = depth_complete

            if not depth_complete.get("success"):
                logger.error(f"❌ [DEPTH_PIPELINE] Failed waiting for depth map generation")
                results["error"] = "Depth map generation timeout or failed"
                return results

            # Step 4: Download depth map
            logger.info(f"\n{'='*60}")
            logger.info(f"STEP 4: Download Depth Map")
            logger.info(f"{'='*60}")

            depth_img_records = depth_complete.get("img_records", [])
            if not depth_img_records:
                logger.error(f"❌ [DEPTH_PIPELINE] No depth map generated!")
                results["error"] = "No depth map in response"
                return results

            # Get depth map URL
            depth_map_url = depth_img_records[0] if isinstance(depth_img_records[0], str) else depth_img_records[0].get("url", "")
            logger.info(f"   Depth map URL: {depth_map_url}")

            # Download the depth map
            depth_output_path = os.path.join(output_dir, f"{image_name}_depth.png")
            download_result = await self.download_file(depth_map_url, depth_output_path)

            if download_result.get("success"):
                results["outputs"]["depth_image"] = depth_output_path
                results["outputs"]["depth_url"] = depth_map_url
                results["success"] = True
                logger.info(f"\n✅ [DEPTH_PIPELINE] Complete!")
                logger.info(f"   Depth map: {depth_output_path}")
            else:
                logger.error(f"❌ [DEPTH_PIPELINE] Failed to download depth map")
                results["error"] = "Failed to download depth map"

            return results

        except Exception as e:
            logger.error(f"❌ [DEPTH_PIPELINE] Exception: {e}")
            import traceback
            logger.error(traceback.format_exc())
            results["error"] = str(e)
            return results

    async def health_check(self) -> Dict:
        """Check if Sculptok API is reachable"""
        logger.info("🏥 [HEALTH] Checking Sculptok API...")

        if not self.api_key:
            return {
                "healthy": False,
                "error": "SCULPTOK_API_KEY not configured"
            }

        # Try a simple request to check connectivity
        # We'll use the status endpoint with a dummy UUID (will return error but proves connectivity)
        url = f"{self.base_url}/draw/prompt"
        params = {"uuid": "health-check-test"}

        try:
            async with aiohttp.ClientSession() as session:
                headers = self._get_headers()
                async with session.get(url, params=params, headers=headers, timeout=10) as response:
                    # Any response (even error) means API is reachable
                    if response.status in [200, 400, 401, 404]:
                        logger.info(f"✅ [HEALTH] API reachable (status: {response.status})")
                        return {
                            "healthy": True,
                            "status_code": response.status,
                            "base_url": self.base_url
                        }
                    else:
                        return {
                            "healthy": False,
                            "error": f"Unexpected status: {response.status}"
                        }

        except Exception as e:
            logger.error(f"❌ [HEALTH] API unreachable: {e}")
            return {
                "healthy": False,
                "error": str(e)
            }


# Convenience function for creating client
def create_sculptok_client() -> SculptokClient:
    """Create and return a SculptokClient instance"""
    return SculptokClient()
