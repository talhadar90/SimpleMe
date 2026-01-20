import os
import subprocess
import asyncio
import shutil
from typing import List, Dict, Optional
from datetime import datetime
import logging
from pathlib import Path

try:
    from config.settings import settings
except ImportError:
    class Settings:
        STICKER_MAKER_EXECUTABLE = "/home/ubuntu/SimpleMe/sticker_maker/PrintMaker"
        STICKER_MAKER_WORKDIR = "/home/ubuntu/SimpleMe/sticker_maker"
        STICKER_MAKER_DPI = 300
        STICKER_MAKER_MIN_SIZE_MM = 10.0
        STICKER_MAKER_CUT_MARGIN_MM = 1.0
        STICKER_MAKER_CUT_SMOOTHING = 10
        STICKER_MAKER_TIMEOUT = 300
        PROCESSED_PATH = "./storage/processed"
        BLENDER_EXECUTABLE = "blender"

    settings = Settings()

logger = logging.getLogger(__name__)


class StickerMakerService:
    """
    Service to generate printable stickers from 3D models and 2D images.
    Replaces the old BlenderProcessor with integrated Blender + sticker generation.
    """

    def __init__(self):
        """Initialize StickerMaker service"""
        self.executable = settings.STICKER_MAKER_EXECUTABLE
        self.working_dir = settings.STICKER_MAKER_WORKDIR
        self.dpi = settings.STICKER_MAKER_DPI
        self.min_size_mm = settings.STICKER_MAKER_MIN_SIZE_MM
        self.cut_margin_mm = settings.STICKER_MAKER_CUT_MARGIN_MM
        self.cut_smoothing = settings.STICKER_MAKER_CUT_SMOOTHING
        self.timeout = settings.STICKER_MAKER_TIMEOUT
        self.blender_exe = settings.BLENDER_EXECUTABLE

        logger.info(f"✅ StickerMaker service initialized - Executable: {self.executable}")
        logger.info(f"   Working dir: {self.working_dir}")
        logger.info(f"   Blender: {self.blender_exe}")

    async def process_3d_models(self, job_id: str, models_3d: List[Dict],
                                processed_images: List[Dict]) -> Dict:
        """
        Process 3D models into sticker files (replaces old BlenderProcessor)

        This method:
        1. Prepares input files in sticker_maker's expected structure
        2. Executes PrintMaker .NET application
        3. Collects output files (printing.png, reference.png, cutting.dxf)
        4. Returns results in same format as old BlenderProcessor for compatibility

        Args:
            job_id: Job identifier
            models_3d: List of 3D model metadata from Hunyuan3D
            processed_images: List of processed images with background removed

        Returns:
            Dict with processing results (compatible with old BlenderProcessor format)
        """
        try:
            logger.info(f"🖨️ Starting sticker generation for job {job_id}")
            logger.info(f"   Models: {len(models_3d)}, Images: {len(processed_images)}")

            # Step 1: Prepare input directory with required files
            logger.info(f"📁 Step 1: Preparing input files for job {job_id}")
            prep_result = await self._prepare_sticker_inputs(
                job_id=job_id,
                models_3d=models_3d,
                processed_images=processed_images
            )

            if not prep_result["success"]:
                raise Exception(f"Failed to prepare inputs: {prep_result.get('error')}")

            logger.info(f"✅ Input files prepared: {prep_result['files_prepared']}")

            # Step 2: Execute PrintMaker
            logger.info(f"⚙️ Step 2: Executing PrintMaker for job {job_id}")
            exec_result = await self._execute_printmaker(job_id)

            if not exec_result["success"]:
                raise Exception(f"PrintMaker execution failed: {exec_result.get('error')}")

            logger.info(f"✅ PrintMaker completed successfully")

            # Step 3: Collect output files
            logger.info(f"📦 Step 3: Collecting output files for job {job_id}")
            output_result = await self._collect_outputs(job_id)

            if not output_result["success"]:
                raise Exception(f"Failed to collect outputs: {output_result.get('error')}")

            logger.info(f"✅ Output files collected: {len(output_result['output_files'])} files")

            # Step 4: Build result in BlenderProcessor-compatible format
            final_result = {
                'success': True,
                'job_id': job_id,
                'output_files': output_result['output_files'],
                'output_dir': output_result['output_dir'],
                'sticker_files': {
                    'printing_png': output_result.get('printing_file'),
                    'reference_png': output_result.get('reference_file'),
                    'cutting_dxf': output_result.get('cutting_dxf')
                },
                'execution_log': exec_result.get('stdout', ''),
                'processing_time_seconds': exec_result.get('execution_time', 0),
                'method': 'sticker_maker',
                'completed_at': datetime.now().isoformat()
            }

            logger.info(f"🎉 Sticker generation completed for job {job_id}")
            return final_result

        except Exception as e:
            logger.error(f"❌ Error in sticker generation for job {job_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'job_id': job_id,
                'method': 'sticker_maker',
                'failed_at': datetime.now().isoformat()
            }

    async def _prepare_sticker_inputs(self, job_id: str, models_3d: List[Dict],
                                     processed_images: List[Dict]) -> Dict:
        """
        Prepare input files in sticker_maker's expected structure

        Expected structure:
        sticker_maker/jobs/{job_id}/in/
        ├── base_character_3d.glb
        ├── accessory_1_3d.glb
        ├── accessory_2_3d.glb
        ├── accessory_3_3d.glb
        ├── base_character_2d.png
        ├── accessory_1_2d.png
        ├── accessory_2_2d.png
        └── accessory_3_2d.png

        Args:
            job_id: Job identifier
            models_3d: 3D models from Hunyuan3D
            processed_images: Images with background removed

        Returns:
            Dict with preparation results
        """
        try:
            # Create input directory
            in_dir = os.path.join(self.working_dir, "jobs", job_id, "in")
            os.makedirs(in_dir, exist_ok=True)
            logger.info(f"📁 Created input directory: {in_dir}")

            files_prepared = []

            # Organize models by type
            organized = self._organize_models_by_type(models_3d)

            # Copy GLB files with expected names
            logger.info(f"🔄 Copying GLB files...")

            # 1. Base character GLB
            if organized['figure']:
                src_glb = organized['figure']['model_path']
                dst_glb = os.path.join(in_dir, "base_character_3d.glb")
                if os.path.exists(src_glb):
                    shutil.copy2(src_glb, dst_glb)
                    files_prepared.append("base_character_3d.glb")
                    logger.info(f"   ✅ Copied: base_character_3d.glb")
                else:
                    logger.warning(f"   ⚠️ Source not found: {src_glb}")
            else:
                logger.warning(f"   ⚠️ No base character found in models")

            # 2. Accessory GLBs (accessory_1, accessory_2, accessory_3)
            for i, acc in enumerate(organized['accessories'][:3], 1):
                src_glb = acc['model_path']
                dst_glb = os.path.join(in_dir, f"accessory_{i}_3d.glb")
                if os.path.exists(src_glb):
                    shutil.copy2(src_glb, dst_glb)
                    files_prepared.append(f"accessory_{i}_3d.glb")
                    logger.info(f"   ✅ Copied: accessory_{i}_3d.glb")
                else:
                    logger.warning(f"   ⚠️ Source not found: {src_glb}")

            # Copy PNG files (nobg versions) with expected names
            logger.info(f"🔄 Copying PNG files (nobg versions)...")

            # Map processed images to expected names
            image_map = self._map_images_to_names(processed_images)

            for expected_name, src_path in image_map.items():
                if src_path and os.path.exists(src_path):
                    dst_png = os.path.join(in_dir, expected_name)
                    shutil.copy2(src_path, dst_png)
                    files_prepared.append(expected_name)
                    logger.info(f"   ✅ Copied: {expected_name}")
                else:
                    logger.warning(f"   ⚠️ Image not found for: {expected_name}")

            logger.info(f"✅ Prepared {len(files_prepared)} files in {in_dir}")

            return {
                'success': True,
                'input_dir': in_dir,
                'files_prepared': files_prepared,
                'file_count': len(files_prepared)
            }

        except Exception as e:
            logger.error(f"❌ Error preparing inputs: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def _organize_models_by_type(self, models_3d: List[Dict]) -> Dict:
        """
        Organize 3D models by type (figure vs accessories)

        Args:
            models_3d: List of 3D model metadata

        Returns:
            Dict with 'figure' and 'accessories' lists
        """
        organized = {
            'figure': None,
            'accessories': []
        }

        for model in models_3d:
            model_path = model.get('model_path', '')
            filename = os.path.basename(model_path)

            # Check if this is the base character
            if 'base_character' in filename.lower():
                organized['figure'] = model
            # Check if this is an accessory
            elif 'accessory_' in filename.lower():
                organized['accessories'].append(model)
            else:
                # Unknown pattern, treat as accessory
                organized['accessories'].append(model)

        # Sort accessories by number
        organized['accessories'].sort(
            key=lambda x: self._extract_accessory_number(x.get('model_path', ''))
        )

        return organized

    def _extract_accessory_number(self, filepath: str) -> int:
        """Extract accessory number from filename"""
        try:
            filename = os.path.basename(filepath)
            if 'accessory_' in filename:
                parts = filename.split('accessory_')[1]
                number_str = parts.split('_')[0]
                return int(number_str)
            return 999
        except:
            return 999

    def _map_images_to_names(self, processed_images: List[Dict]) -> Dict[str, Optional[str]]:
        """
        Map processed images (nobg versions) to expected names

        Args:
            processed_images: List of processed image metadata

        Returns:
            Dict mapping expected names to source paths
        """
        image_map = {
            'base_character_2d.png': None,
            'accessory_1_2d.png': None,
            'accessory_2_2d.png': None,
            'accessory_3_2d.png': None
        }

        for img_data in processed_images:
            # Get the processed path (nobg version)
            img_path = img_data.get('processed_path') or img_data.get('file_path')
            img_type = img_data.get('type', '')

            if not img_path or not os.path.exists(img_path):
                continue

            # Map to expected names
            if 'base_character' in img_type.lower():
                image_map['base_character_2d.png'] = img_path
            elif 'accessory_1' in img_type.lower():
                image_map['accessory_1_2d.png'] = img_path
            elif 'accessory_2' in img_type.lower():
                image_map['accessory_2_2d.png'] = img_path
            elif 'accessory_3' in img_type.lower():
                image_map['accessory_3_2d.png'] = img_path

        return image_map

    async def _execute_printmaker(self, job_id: str) -> Dict:
        """
        Execute PrintMaker .NET application

        Command format:
        ./PrintMaker --job {job_id} --workdir {working_dir} --dpi 300 ...

        Args:
            job_id: Job identifier

        Returns:
            Dict with execution results
        """
        try:
            logger.info(f"🚀 Executing PrintMaker for job {job_id}")

            # Build command
            cmd = [
                self.executable,
                "--job", job_id,
                "--workdir", self.working_dir,
                "--dpi", str(self.dpi),
                "--min_sticker_mm", str(self.min_size_mm),
                "--cut_margin_mm", str(self.cut_margin_mm),
                "--cut_smoothing", str(self.cut_smoothing)
            ]

            logger.info(f"   Command: {' '.join(cmd)}")

            # Execute with timeout
            start_time = datetime.now()

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise Exception(f"PrintMaker execution timed out after {self.timeout}s")

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            # Decode output
            stdout_text = stdout.decode('utf-8') if stdout else ''
            stderr_text = stderr.decode('utf-8') if stderr else ''

            # Check return code
            if process.returncode != 0:
                logger.error(f"❌ PrintMaker failed with return code {process.returncode}")
                logger.error(f"   STDERR: {stderr_text}")
                return {
                    'success': False,
                    'error': f"PrintMaker returned code {process.returncode}",
                    'stdout': stdout_text,
                    'stderr': stderr_text,
                    'return_code': process.returncode
                }

            logger.info(f"✅ PrintMaker completed in {execution_time:.2f}s")

            return {
                'success': True,
                'stdout': stdout_text,
                'stderr': stderr_text,
                'return_code': 0,
                'execution_time': execution_time,
                'completed_at': end_time.isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Error executing PrintMaker: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def _collect_outputs(self, job_id: str) -> Dict:
        """
        Collect generated files from sticker_maker/jobs/{job_id}/out/

        Expected outputs:
        - printing.png (high-res printable file)
        - reference.png (preview with cut lines)
        - cutting.dxf (vector cut paths)

        Args:
            job_id: Job identifier

        Returns:
            Dict with output file information
        """
        try:
            # Source directory (PrintMaker output)
            out_dir = os.path.join(self.working_dir, "jobs", job_id, "out")

            # Destination directory (storage/processed)
            dest_dir = os.path.join(settings.PROCESSED_PATH, job_id, "stickers")
            os.makedirs(dest_dir, exist_ok=True)

            logger.info(f"📦 Collecting outputs from: {out_dir}")
            logger.info(f"   Destination: {dest_dir}")

            output_files = []
            file_mapping = {
                'card_printing.png': 'card_printing_file',
                'card_reference.png': 'card_reference_file',
                'card_cutting.dxf': 'card_cutting_dxf',
                'card_model.stl': 'starter_pack_stl',
                'card_model.blend': 'starter_pack_blend',
                'keychain_printing.png': 'keychain_printing_file',
                'keychain_reference.png': 'keychain_reference_file',
                'keychain_cutting.dxf': 'keychain_cutting_dxf',
                'keychain_model.stl': 'keychain_stl',
                'keychain_model.blend': 'keychain_blend'
            }

            result = {
                'success': True,
                'output_dir': dest_dir,
                'output_files': []
            }

            for src_name, file_type in file_mapping.items():
                src_path = os.path.join(out_dir, src_name)
                dst_path = os.path.join(dest_dir, src_name)

                if os.path.exists(src_path):
                    # Copy file to storage
                    shutil.copy2(src_path, dst_path)

                    # Get file info
                    file_size = os.path.getsize(dst_path)
                    file_ext = os.path.splitext(src_name)[1]

                    file_info = {
                        'filename': src_name,
                        'file_path': dst_path,
                        'file_extension': file_ext,
                        'file_size_bytes': file_size,
                        'file_size_mb': round(file_size / (1024 * 1024), 2),
                        'file_type': file_type,
                        'download_url': f"/storage/processed/{job_id}/stickers/{src_name}",
                        'created_at': datetime.now().isoformat()
                    }

                    output_files.append(file_info)
                    result[file_type] = dst_path

                    logger.info(f"   ✅ Collected: {src_name} ({file_info['file_size_mb']} MB)")
                else:
                    logger.warning(f"   ⚠️ Output file not found: {src_path}")

            result['output_files'] = output_files

            if not output_files:
                logger.error(f"❌ No output files found in {out_dir}")
                result['success'] = False
                result['error'] = "No output files generated"
            else:
                logger.info(f"✅ Collected {len(output_files)} output files")

            return result

        except Exception as e:
            logger.error(f"❌ Error collecting outputs: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def health_check(self) -> bool:
        """
        Check if PrintMaker executable exists and is executable

        Returns:
            True if healthy
        """
        try:
            # Check executable exists
            if not os.path.exists(self.executable):
                logger.error(f"❌ PrintMaker executable not found: {self.executable}")
                return False

            # Check if executable
            if not os.access(self.executable, os.X_OK):
                logger.error(f"❌ PrintMaker not executable: {self.executable}")
                return False

            # Check Blender exists
            try:
                result = subprocess.run(
                    [self.blender_exe, "--version"],
                    capture_output=True,
                    timeout=10
                )
                if result.returncode != 0:
                    logger.error(f"❌ Blender not working: {self.blender_exe}")
                    return False
            except Exception as e:
                logger.error(f"❌ Blender check failed: {e}")
                return False

            logger.info(f"✅ StickerMaker health check passed")
            return True

        except Exception as e:
            logger.error(f"❌ StickerMaker health check failed: {str(e)}")
            return False

    async def create_simple_test(self, output_path: str) -> bool:
        """
        Create a simple test to verify the service is working

        Args:
            output_path: Path for test output

        Returns:
            True if test passed
        """
        try:
            # Just check if executable exists and is runnable
            return await self.health_check()
        except Exception as e:
            logger.error(f"❌ Test failed: {str(e)}")
            return False
