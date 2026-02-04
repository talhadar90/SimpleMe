"""
Async Order Processor

Processes starter pack orders asynchronously in a queue.
Orders are processed one at a time in the order they were received.
"""

import asyncio
import logging
import os
import uuid
import traceback
from typing import Dict, Optional, List
from datetime import datetime
from collections import deque

from config.settings import settings
from services.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class OrderProcessor:
    """Async order processor with queue"""

    def __init__(self):
        self.queue: deque = deque()
        self.processing = False
        self.current_job: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._ai_generator = None
        self._sculptok_client = None

    def set_services(self, ai_generator, sculptok_client):
        """Set the AI generator and Sculptok client services"""
        self._ai_generator = ai_generator
        self._sculptok_client = sculptok_client
        logger.info("✅ OrderProcessor services configured")

    async def add_order(self, order_data: Dict) -> str:
        """
        Add an order to the processing queue.
        Returns the job_id immediately.
        """
        job_id = order_data.get("job_id", str(uuid.uuid4())[:8])
        order_data["job_id"] = job_id
        order_data["queued_at"] = datetime.now().isoformat()

        self.queue.append(order_data)
        logger.info(f"📥 Order {job_id} added to queue (position: {len(self.queue)})")

        # Start processing if not already running
        if not self.processing:
            self._task = asyncio.create_task(self._process_queue())

        return job_id

    def get_queue_status(self) -> Dict:
        """Get current queue status"""
        return {
            "queue_length": len(self.queue),
            "processing": self.processing,
            "current_job": self.current_job,
            "queued_jobs": [o.get("job_id") for o in self.queue]
        }

    async def retry_order(self, job_id: str, from_step: int, order_data: Dict = None) -> str:
        """
        Retry an order from a specific step.

        Steps:
        1 - Generate images (GPT-image-1.5)
        2 - Background image generation (optional)
        3 - Background removal (Sculptok HD)
        4 - Depth map generation
        5 - Blender processing

        Args:
            job_id: The job ID to retry
            from_step: Step number to resume from (1-5)
            order_data: Optional order data (if not provided, loads from DB)

        Returns:
            job_id
        """
        if order_data is None:
            # Load order data from database
            supabase = get_supabase_client()
            if supabase.is_connected():
                order_record = await supabase.get_order(job_id)
                if not order_record:
                    raise Exception(f"Order {job_id} not found")
                order_data = order_record
            else:
                raise Exception("Database not connected")

        order_data["job_id"] = job_id
        order_data["from_step"] = from_step
        order_data["is_retry"] = True
        order_data["queued_at"] = datetime.now().isoformat()

        # Set job_dir from existing path or construct it
        if not order_data.get("job_dir"):
            order_data["job_dir"] = f"./storage/test_starter_pack/{job_id}"

        self.queue.append(order_data)
        logger.info(f"🔄 Order {job_id} added to queue for retry from step {from_step}")

        # Start processing if not already running
        if not self.processing:
            self._task = asyncio.create_task(self._process_queue())

        return job_id

    async def _process_queue(self):
        """Process orders from the queue one by one"""
        self.processing = True
        logger.info("🔄 Order processor started")

        while self.queue:
            order_data = self.queue.popleft()
            job_id = order_data.get("job_id")
            self.current_job = job_id

            logger.info(f"▶️ Processing order {job_id} ({len(self.queue)} remaining in queue)")

            try:
                # Run in thread pool to avoid blocking the event loop
                await asyncio.to_thread(self._process_order_sync, order_data)
            except Exception as e:
                logger.error(f"❌ Order {job_id} failed with exception: {e}")
                logger.error(traceback.format_exc())
                # Update database with error
                supabase = get_supabase_client()
                if supabase.is_connected():
                    try:
                        await supabase.update_order_status(job_id, "failed", str(e))
                    except:
                        pass

        self.processing = False
        self.current_job = None
        logger.info("✅ Order processor idle - queue empty")

    def _process_order_sync(self, order_data: Dict):
        """Synchronous wrapper to run in thread pool"""
        import asyncio
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._process_order(order_data))
        finally:
            loop.close()

    def _save_step_state(self, job_dir: str, step: int, state: Dict):
        """Save intermediate state after a step completes"""
        import json
        state_file = os.path.join(job_dir, "pipeline_state.json")

        # Load existing state or create new
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                full_state = json.load(f)
        else:
            full_state = {"steps_completed": [], "data": {}}

        full_state["steps_completed"].append(step)
        full_state["last_step"] = step
        full_state["data"][f"step_{step}"] = state
        full_state["updated_at"] = datetime.now().isoformat()

        with open(state_file, 'w') as f:
            json.dump(full_state, f, indent=2)

        logger.info(f"💾 Saved state for step {step}")

    def _load_step_state(self, job_dir: str) -> Dict:
        """Load saved pipeline state"""
        import json
        state_file = os.path.join(job_dir, "pipeline_state.json")

        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                return json.load(f)
        return {"steps_completed": [], "data": {}}

    def _find_generated_images(self, job_dir: str) -> tuple:
        """Find existing generated images in job directory.

        Returns images with both original_path (high quality GPT) and nobg_path (for depth maps).
        Blender should use original_path for textures.
        """
        figure_img = None
        accessory_imgs = []

        # Look for ORIGINAL generated images (high quality, transparent background)
        generated_dir = f"./storage/generated/{os.path.basename(job_dir)}"
        if os.path.exists(generated_dir):
            for f in sorted(os.listdir(generated_dir)):
                if f.endswith('.png') and '_texture' not in f:
                    file_path = os.path.join(generated_dir, f)
                    if 'base_character' in f:
                        figure_img = {
                            "file_path": file_path,
                            "original_path": file_path,  # Original GPT image for Blender
                            "type": "base_character"
                        }
                    elif 'accessory' in f:
                        accessory_imgs.append({
                            "file_path": file_path,
                            "original_path": file_path,  # Original GPT image for Blender
                            "type": "accessory"
                        })

        # Check for nobg versions and ADD them as nobg_path (don't replace original!)
        nobg_figure = os.path.join(job_dir, "figure_nobg.png")
        if figure_img and os.path.exists(nobg_figure):
            figure_img["nobg_path"] = nobg_figure

        for i, acc in enumerate(accessory_imgs):
            nobg_path = os.path.join(job_dir, f"accessory_{i+1}_nobg.png")
            if os.path.exists(nobg_path):
                acc["nobg_path"] = nobg_path

        return figure_img, accessory_imgs

    def _find_depth_maps(self, job_dir: str) -> Dict:
        """Find existing depth maps in job directory"""
        depth_maps = {}

        figure_depth = os.path.join(job_dir, "figure_depth.png")
        if os.path.exists(figure_depth):
            depth_maps["figure"] = figure_depth

        for i in range(1, 4):
            acc_depth = os.path.join(job_dir, f"accessory_{i}_depth.png")
            if os.path.exists(acc_depth):
                depth_maps[f"accessory_{i}"] = acc_depth

        return depth_maps

    async def _process_order(self, order_data: Dict):
        """Process a single order through the full pipeline"""
        import aiofiles
        import subprocess

        job_id = order_data["job_id"]
        job_dir = order_data["job_dir"]
        supabase = get_supabase_client()

        # Check if this is a retry with a specific starting step
        from_step = order_data.get("from_step", 1)
        is_retry = order_data.get("is_retry", False)

        if is_retry:
            logger.info(f"🔄 [ORDER {job_id}] Retrying pipeline from step {from_step}")
        else:
            logger.info(f"🚀 [ORDER {job_id}] Starting pipeline")

        # Update status to processing
        if supabase.is_connected():
            await supabase.update_order_status(job_id, "processing")

        errors = []
        outputs = {}

        # Initialize variables that might be loaded from previous state
        figure_img = None
        accessory_imgs = []
        background_image_path = None
        depth_maps = {}

        try:
            # Get common data
            user_image_path = order_data.get("user_image_path")
            accessories = order_data.get("accessories", [])
            background_type = order_data.get("background_type", "transparent")
            background_color = order_data.get("background_color", "white")

            # ============================================================
            # STEP 1: Generate images with GPT-image-1.5
            # ============================================================
            if from_step <= 1:
                logger.info(f"[ORDER {job_id}] Step 1: GPT Image Generation")

                generated_images = await self._ai_generator.generate_action_figures(
                    job_id=job_id,
                    user_image_path=user_image_path,
                    accessories=accessories
                )

                if not generated_images:
                    raise Exception("GPT-image-1.5 failed to generate images")

                logger.info(f"[ORDER {job_id}] Generated {len(generated_images)} images")

                # Separate figure and accessories
                for img in generated_images:
                    if "base_character" in img.get("type", ""):
                        figure_img = img
                    else:
                        accessory_imgs.append(img)

                if not figure_img:
                    raise Exception("No base character image generated")

                # Save state after step 1
                self._save_step_state(job_dir, 1, {
                    "figure_img": figure_img,
                    "accessory_imgs": accessory_imgs
                })
            else:
                # Load existing images from previous run
                logger.info(f"[ORDER {job_id}] ⏭️ Skipping Step 1 - Loading existing images")
                figure_img, accessory_imgs = self._find_generated_images(job_dir)
                if not figure_img:
                    raise Exception("No existing figure image found for retry")
                logger.info(f"[ORDER {job_id}] Found figure + {len(accessory_imgs)} accessories")

            # ============================================================
            # STEP 2: Handle background image (if needed)
            # ============================================================
            if from_step <= 2:
                if background_type == "image":
                    logger.info(f"[ORDER {job_id}] Step 2: Background Generation")

                    bg_description = order_data.get("background_description", "")
                    bg_input_path = order_data.get("background_input_path")

                    if bg_input_path and os.path.exists(bg_input_path):
                        # Enhance user's background image
                        from openai import OpenAI
                        client = OpenAI(api_key=settings.OPENAI_API_KEY)

                        enhance_prompt = """Enhance this image to be a high-resolution, detailed background.
Keep the exact same composition and elements, but add more details and improve quality.
Output should be suitable as a background for an action figure card."""

                        with open(bg_input_path, "rb") as f:
                            response = client.images.edit(
                                model="gpt-image-1.5",
                                image=f,
                                prompt=enhance_prompt,
                                size="1024x1024"
                            )

                        if response.data:
                            import base64
                            bg_b64 = response.data[0].b64_json
                            background_image_path = os.path.join(job_dir, "background_enhanced.png")
                            async with aiofiles.open(background_image_path, "wb") as f:
                                await f.write(base64.b64decode(bg_b64))
                            logger.info(f"[ORDER {job_id}] Enhanced background saved")

                    elif bg_description:
                        # Generate new background from description
                        from openai import OpenAI
                        client = OpenAI(api_key=settings.OPENAI_API_KEY)

                        bg_prompt = f"""Create a detailed, high-quality background image: {bg_description}
The image should be suitable as a background for an action figure collector card.
Make it visually interesting but not too busy - it should complement, not overwhelm, the foreground."""

                        response = client.images.generate(
                            model="gpt-image-1.5",
                            prompt=bg_prompt,
                            size="1024x1024",
                            output_format="png",
                            n=1
                        )

                        if response.data:
                            import base64
                            bg_b64 = response.data[0].b64_json
                            background_image_path = os.path.join(job_dir, "background_generated.png")
                            async with aiofiles.open(background_image_path, "wb") as f:
                                await f.write(base64.b64decode(bg_b64))
                            logger.info(f"[ORDER {job_id}] Generated background saved")
            else:
                # Check for existing background images
                for bg_name in ["background_enhanced.png", "background_generated.png"]:
                    bg_path = os.path.join(job_dir, bg_name)
                    if os.path.exists(bg_path):
                        background_image_path = bg_path
                        logger.info(f"[ORDER {job_id}] ⏭️ Skipping Step 2 - Using existing background: {bg_name}")
                        break

            # ============================================================
            # STEP 3: Background Removal (Sculptok HD)
            # ============================================================
            if from_step <= 3:
                logger.info(f"[ORDER {job_id}] Step 3: Background Removal with HD Restoration")

                # Process figure background removal
                logger.info(f"[ORDER {job_id}] Removing background from figure image...")
                figure_upload = await self._sculptok_client.upload_image(figure_img["file_path"])
                if not figure_upload.get("success"):
                    raise Exception(f"Figure upload failed: {figure_upload.get('error')}")

                figure_bg_result = await self._sculptok_client.remove_background(
                    figure_upload.get("image_url"),
                    hd_fix=True,
                    remove_type="general"
                )
                if not figure_bg_result.get("success"):
                    raise Exception(f"Figure background removal failed: {figure_bg_result.get('error')}")

                figure_bg_complete = await self._sculptok_client.wait_for_completion(
                    figure_bg_result.get("prompt_id"),
                    "Figure Background Removal"
                )
                if not figure_bg_complete.get("success"):
                    raise Exception(f"Figure background removal timeout")

                # Save the bg-removed figure image
                figure_nobg_records = figure_bg_complete.get("img_records", [])
                if figure_nobg_records:
                    figure_nobg_url = figure_nobg_records[0]
                    figure_nobg_path = os.path.join(job_dir, "figure_nobg.png")
                    await self._sculptok_client.download_file(figure_nobg_url, figure_nobg_path)
                    # Keep original path for Blender texture, use nobg for depth maps only
                    figure_img["original_path"] = figure_img["file_path"]
                    figure_img["nobg_path"] = figure_nobg_path
                    figure_img["nobg_url"] = figure_nobg_url
                    logger.info(f"[ORDER {job_id}] Figure background removed: {figure_nobg_path}")
                else:
                    logger.warning(f"[ORDER {job_id}] No bg-removed figure image returned, using original")
                    figure_img["original_path"] = figure_img["file_path"]
                    figure_img["nobg_path"] = figure_img["file_path"]

                # Process accessory background removal
                for i, acc_img in enumerate(accessory_imgs):
                    acc_name = f"accessory_{i+1}"
                    logger.info(f"[ORDER {job_id}] Removing background from {acc_name}...")

                    acc_upload = await self._sculptok_client.upload_image(acc_img["file_path"])
                    if not acc_upload.get("success"):
                        logger.warning(f"[ORDER {job_id}] {acc_name} upload failed, using original")
                        continue

                    acc_bg_result = await self._sculptok_client.remove_background(
                        acc_upload.get("image_url"),
                        hd_fix=True,
                        remove_type="general"
                    )
                    if not acc_bg_result.get("success"):
                        logger.warning(f"[ORDER {job_id}] {acc_name} bg removal failed, using original")
                        continue

                    acc_bg_complete = await self._sculptok_client.wait_for_completion(
                        acc_bg_result.get("prompt_id"),
                        f"{acc_name} Background Removal"
                    )
                    if not acc_bg_complete.get("success"):
                        logger.warning(f"[ORDER {job_id}] {acc_name} bg removal timeout, using original")
                        continue

                    # Save the bg-removed accessory image
                    acc_nobg_records = acc_bg_complete.get("img_records", [])
                    if acc_nobg_records:
                        acc_nobg_url = acc_nobg_records[0]
                        acc_nobg_path = os.path.join(job_dir, f"{acc_name}_nobg.png")
                        await self._sculptok_client.download_file(acc_nobg_url, acc_nobg_path)
                        # Keep original path for Blender texture, use nobg for depth maps only
                        acc_img["original_path"] = acc_img["file_path"]
                        acc_img["nobg_path"] = acc_nobg_path
                        acc_img["nobg_url"] = acc_nobg_url
                        logger.info(f"[ORDER {job_id}] {acc_name} background removed: {acc_nobg_path}")
                    else:
                        acc_img["original_path"] = acc_img["file_path"]
                        acc_img["nobg_path"] = acc_img["file_path"]

                # Save state after step 3
                self._save_step_state(job_dir, 3, {
                    "figure_img": figure_img,
                    "accessory_imgs": accessory_imgs
                })
            else:
                # Load existing nobg images
                logger.info(f"[ORDER {job_id}] ⏭️ Skipping Step 3 - Loading existing bg-removed images")
                figure_img, accessory_imgs = self._find_generated_images(job_dir)
                if not figure_img:
                    raise Exception("No existing figure image found for retry")

            # ============================================================
            # STEP 4: Generate depth maps with Sculptok
            # ============================================================
            if from_step <= 4:
                logger.info(f"[ORDER {job_id}] Step 4: Depth Map Generation")

                # Use nobg images for depth maps (cleaner edges)
                figure_depth_img = figure_img.get("nobg_path") or figure_img.get("file_path")
                logger.info(f"[ORDER {job_id}] Using for depth map: {figure_depth_img}")

                # Figure depth map (skip_bg_removal=True since we already did it)
                figure_depth_result = await self._sculptok_client.process_image_to_depth_map(
                    image_path=figure_depth_img,
                    output_dir=job_dir,
                    image_name="figure",
                    skip_bg_removal=True,  # Already removed background
                    style="pro",
                    version="1.5",
                    draw_hd="4k",
                    ext_info="16bit"
                )

                if figure_depth_result.get("success"):
                    depth_maps["figure"] = figure_depth_result.get("outputs", {}).get("depth_image")
                    logger.info(f"[ORDER {job_id}] Figure depth map generated")
                else:
                    raise Exception(f"Figure depth map failed: {figure_depth_result.get('error')}")

                # Accessory depth maps (skip_bg_removal=True since we already did it)
                for i, acc_img in enumerate(accessory_imgs):
                    acc_name = f"accessory_{i+1}"
                    # Use nobg images for depth maps
                    acc_depth_img = acc_img.get("nobg_path") or acc_img.get("file_path")

                    acc_depth_result = await self._sculptok_client.process_image_to_depth_map(
                        image_path=acc_depth_img,
                        output_dir=job_dir,
                        image_name=acc_name,
                        skip_bg_removal=True,  # Already removed background
                        style="pro",
                        version="1.5",
                        draw_hd="4k",
                        ext_info="16bit"
                    )

                    if acc_depth_result.get("success"):
                        depth_maps[acc_name] = acc_depth_result.get("outputs", {}).get("depth_image")
                        logger.info(f"[ORDER {job_id}] {acc_name} depth map generated")
                    else:
                        errors.append(f"{acc_name} depth map failed")

                # Save state after step 4
                self._save_step_state(job_dir, 4, {"depth_maps": depth_maps})
            else:
                # Load existing depth maps
                logger.info(f"[ORDER {job_id}] ⏭️ Skipping Step 4 - Loading existing depth maps")
                depth_maps = self._find_depth_maps(job_dir)
                if "figure" not in depth_maps:
                    raise Exception("No existing figure depth map found for retry")
                logger.info(f"[ORDER {job_id}] Found {len(depth_maps)} depth maps")

            # ============================================================
            # STEP 5: Run Blender to create STL + texture
            # ============================================================
            logger.info(f"[ORDER {job_id}] Step 5: Blender Processing")

            blender_script = os.path.join(os.path.dirname(__file__), "blender_starter_pack.py")
            output_dir = os.path.join(job_dir, "final_output")
            os.makedirs(output_dir, exist_ok=True)

            # Build Blender command
            blender_cmd = [
                "blender", "--background", "--python", blender_script, "--"
            ]

            # Add figure (Blender expects --figure_img and --figure_depth)
            # Use ORIGINAL high-quality image for texture, not nobg (which is lower quality)
            figure_texture_img = figure_img.get("original_path") or figure_img.get("file_path")
            logger.info(f"[ORDER {job_id}] Using for Blender texture: {figure_texture_img}")

            blender_cmd.extend([
                "--figure_img", figure_texture_img,
                "--figure_depth", depth_maps["figure"]
            ])

            # Add accessories (Blender expects --acc1_img, --acc1_depth, --acc2_img, etc.)
            # Use ORIGINAL images for textures
            for i, acc_img in enumerate(accessory_imgs):
                acc_num = i + 1
                acc_name = f"accessory_{acc_num}"
                if acc_name in depth_maps and acc_num <= 3:  # Max 3 accessories supported
                    acc_texture_img = acc_img.get("original_path") or acc_img.get("file_path")
                    blender_cmd.extend([
                        f"--acc{acc_num}_img", acc_texture_img,
                        f"--acc{acc_num}_depth", depth_maps[acc_name]
                    ])

            # Add title/subtitle/colors
            blender_cmd.extend([
                "--title", order_data.get("title", ""),
                "--subtitle", order_data.get("subtitle", ""),
                "--text_color", order_data.get("text_color", "red"),
                "--background_type", background_type,
                "--background_color", background_color,
            ])

            if background_image_path:
                blender_cmd.extend(["--background_image", background_image_path])

            blender_cmd.extend([
                "--output_dir", output_dir,
                "--job_id", job_id
            ])

            logger.info(f"[ORDER {job_id}] Running Blender...")
            blender_result = subprocess.run(
                blender_cmd,
                capture_output=True,
                text=True,
                timeout=600
            )

            if blender_result.returncode == 0:
                stl_path = os.path.join(output_dir, f"{job_id}.stl")
                texture_path = os.path.join(output_dir, f"{job_id}_texture.png")
                blend_path = os.path.join(output_dir, f"{job_id}.blend")

                if os.path.exists(stl_path):
                    outputs["stl"] = stl_path
                    outputs["stl_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}.stl"
                if os.path.exists(texture_path):
                    outputs["texture"] = texture_path
                    outputs["texture_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}_texture.png"
                if os.path.exists(blend_path):
                    outputs["blend"] = blend_path
                    outputs["blend_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}.blend"

                logger.info(f"[ORDER {job_id}] Blender completed successfully")
            else:
                raise Exception(f"Blender failed: {blender_result.stderr[-500:]}")

            # ============================================================
            # FINAL: Update database with results
            # ============================================================
            success = outputs.get("stl") is not None and outputs.get("texture") is not None

            if supabase.is_connected():
                if success:
                    await supabase.update_order_outputs(job_id, {
                        "stl_path": outputs.get("stl"),
                        "texture_path": outputs.get("texture"),
                        "blend_path": outputs.get("blend"),
                        "stl_url": outputs.get("stl_url"),
                        "texture_url": outputs.get("texture_url"),
                        "blend_url": outputs.get("blend_url")
                    })
                    logger.info(f"✅ [ORDER {job_id}] Completed successfully")
                else:
                    error_msg = "; ".join(errors) if errors else "Unknown error"
                    await supabase.update_order_status(job_id, "failed", error_msg)
                    logger.error(f"❌ [ORDER {job_id}] Failed: {error_msg}")

        except Exception as e:
            logger.error(f"❌ [ORDER {job_id}] Exception: {e}")
            if supabase.is_connected():
                await supabase.update_order_status(job_id, "failed", str(e))
            raise


# Singleton instance
_order_processor: Optional[OrderProcessor] = None


def get_order_processor() -> OrderProcessor:
    """Get or create order processor singleton"""
    global _order_processor
    if _order_processor is None:
        _order_processor = OrderProcessor()
    return _order_processor
