from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import uuid
import os
import aiofiles
from datetime import datetime
import json
import logging
import traceback
import asyncio

# Import our services
from services.ai_image_generator import AIImageGenerator
from services.threed_client_factory import create_3d_client
from services.sticker_maker_service import StickerMakerService  # Replaced BlenderProcessor
from config.settings import settings
from fastapi.staticfiles import StaticFiles
from services.background_remover import ComfyUIBackgroundRemover

# Import shopify 
from api.shopify_handler import ShopifyHandler, shopify_orders

# ADD CORS middleware
from fastapi.middleware.cors import CORSMiddleware

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="SimpleMe API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files to serve generated images
app.mount("/storage", StaticFiles(directory="storage"), name="storage")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/sticker_jobs", StaticFiles(directory="sticker_maker/jobs"), name="sticker_jobs")

# Pydantic models
class JobSubmissionResponse(BaseModel):
    job_id: str
    status: str
    message: str
    submitted_at: str

class JobStatus(BaseModel):
    job_id: str
    status: str  # queued, processing, completed, failed
    progress: dict
    created_at: str
    updated_at: str
    result: Optional[dict] = None
    error: Optional[str] = None

# In-memory job storage (we'll use Redis later)
job_storage = {}

# Initialize services
logger.info("🚀 Initializing services...")
try:
    ai_generator = AIImageGenerator()
    logger.info("✅ AI Image Generator initialized")
except Exception as e:
    logger.error(f"❌ Failed to initialize AI Image Generator: {e}")
    raise

try:
    threed_client = create_3d_client()
    logger.info(f"✅ 3D Client initialized (provider: {settings.THREED_PROVIDER})")
except Exception as e:
    logger.error(f"❌ Failed to initialize 3D Client: {e}")
    raise

try:
    sticker_maker = StickerMakerService()
    logger.info("✅ Sticker Maker Service initialized (replaces BlenderProcessor)")
except Exception as e:
    logger.error(f"❌ Failed to initialize Sticker Maker Service: {e}")
    raise



# Function to restore jobs from storage
async def restore_jobs_from_storage():
    """Restore job metadata from storage directories on startup"""
    try:
        logger.info("🔄 Restoring jobs from storage...")

        restored_count = 0

        # Scan storage directories
        storage_paths = [
            settings.UPLOAD_PATH,
            settings.GENERATED_PATH,
            settings.PROCESSED_PATH
        ]

        job_ids_found = set()

        for storage_path in storage_paths:
            if not os.path.exists(storage_path):
                continue

            for job_id in os.listdir(storage_path):
                if job_id in job_ids_found:
                    continue

                # Skip common directory names that aren't job IDs
                if job_id in ["3d_models", "stl_files", "stickers"]:
                    continue

                job_ids_found.add(job_id)
                job_dir = os.path.join(storage_path, job_id)
                if not os.path.isdir(job_dir):
                    continue

                # Skip if already in memory
                if job_id in job_storage:
                    continue

                # Try to find completion status from files
                processed_dir = os.path.join(settings.PROCESSED_PATH, job_id)
                has_stickers = os.path.exists(os.path.join(processed_dir, "stickers"))
                has_3d_models = os.path.exists(os.path.join(processed_dir, "3d_models"))

                generated_dir = os.path.join(settings.GENERATED_PATH, job_id)
                has_generated = os.path.exists(generated_dir) and len(os.listdir(generated_dir)) > 0

                # Determine status based on what exists
                if has_stickers and has_3d_models:
                    status = "completed"
                    progress_state = {
                        "upload": "completed",
                        "ai_generation": "completed",
                        "background_removal": "completed",
                        "3d_conversion": "completed",
                        "sticker_generation": "completed"
                    }
                elif has_3d_models:
                    status = "processing"
                    progress_state = {
                        "upload": "completed",
                        "ai_generation": "completed",
                        "background_removal": "completed",
                        "3d_conversion": "completed",
                        "sticker_generation": "pending"
                    }
                elif has_generated:
                    status = "processing"
                    progress_state = {
                        "upload": "completed",
                        "ai_generation": "completed",
                        "background_removal": "pending",
                        "3d_conversion": "pending",
                        "sticker_generation": "pending"
                    }
                else:
                    status = "queued"
                    progress_state = {
                        "upload": "completed",
                        "ai_generation": "pending",
                        "background_removal": "pending",
                        "3d_conversion": "pending",
                        "sticker_generation": "pending"
                    }

                # Get file timestamps for created_at
                created_at = datetime.fromtimestamp(os.path.getctime(job_dir)).isoformat()
                updated_at = datetime.fromtimestamp(os.path.getmtime(job_dir)).isoformat()

                # Build result object if job is completed
                result = None
                if status == "completed" and has_stickers:
                    sticker_dir = os.path.join(processed_dir, "stickers")
                    output_files = []

                    # Scan sticker files
                    if os.path.exists(sticker_dir):
                        for filename in os.listdir(sticker_dir):
                            file_path = os.path.join(sticker_dir, filename)
                            if os.path.isfile(file_path):
                                file_size = os.path.getsize(file_path)
                                output_files.append({
                                    'filename': filename,
                                    'file_path': file_path,
                                    'file_size_mb': round(file_size / (1024 * 1024), 2),
                                    'download_url': f'/storage/processed/{job_id}/stickers/{filename}'
                                })

                    # Scan 3D models
                    models_3d = []
                    models_dir = os.path.join(processed_dir, "3d_models")
                    if os.path.exists(models_dir):
                        for filename in os.listdir(models_dir):
                            if filename.endswith('.glb'):
                                file_path = os.path.join(models_dir, filename)
                                file_size = os.path.getsize(file_path)
                                models_3d.append({
                                    'model_filename': filename,
                                    'model_path': file_path,
                                    'file_size_bytes': file_size,
                                    'model_url': f'/storage/processed/{job_id}/3d_models/{filename}'
                                })

                    result = {
                        'sticker_result': {
                            'output_files': output_files
                        },
                        'models_3d': models_3d
                    }

                # Restore job to memory
                job_storage[job_id] = {
                    "job_id": job_id,
                    "status": status,
                    "progress": progress_state,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "result": result,
                    "restored": True  # Flag to indicate this was restored
                }

                restored_count += 1

        logger.info(f"✅ Restored {restored_count} jobs from storage")

    except Exception as e:
        logger.error(f"❌ Error restoring jobs: {e}")
        logger.error(traceback.format_exc())

# Startup event
@app.on_event("startup")
async def startup_event():
    """Run startup checks"""
    logger.info("🔧 Running startup health checks...")

    # Restore jobs from storage
    await restore_jobs_from_storage()

    # Create static directory for ComfyUI
    os.makedirs("static/temp_images", exist_ok=True)
    logger.info("📁 Static directory created for ComfyUI")
    
    # Check Sticker Maker installation
    try:
        sticker_maker_ok = await sticker_maker.health_check()
        if sticker_maker_ok:
            logger.info("✅ Sticker Maker health check passed")
        else:
            logger.warning("⚠️ Sticker Maker health check failed - sticker generation may not work")
    except Exception as e:
        logger.error(f"❌ Sticker Maker health check error: {e}")
    
    # Check Hunyuan3D API
    try:
        hunyuan_ok = await threed_client.health_check()
        if hunyuan_ok:
            logger.info("✅ Hunyuan3D API health check passed")
        else:
            logger.warning("⚠️ Hunyuan3D API health check failed - 3D generation may not work")
    except Exception as e:
        logger.error(f"❌ Hunyuan3D API health check error: {e}")
    
    logger.info("🎯 Startup complete - API ready to serve requests")

# Serve static files
@app.get("/")
async def root():
    """Serve the main HTML page"""
    return FileResponse('/workspace/SimpleMe/index.html')

@app.get("/styles.css")
async def get_styles():
    """Serve CSS file"""
    return FileResponse('/workspace/SimpleMe/styles.css', media_type='text/css')

@app.get("/script.js")
async def get_script():
    """Serve JavaScript file"""
    return FileResponse('/workspace/SimpleMe/script.js', media_type='application/javascript')

@app.post("/submit-job", response_model=JobSubmissionResponse)
async def submit_job(
    background_tasks: BackgroundTasks,
    user_image: UploadFile = File(...),
    accessory_1: str = Form(...),
    accessory_2: str = Form(...),
    accessory_3: str = Form(...),
):
    """Submit a job to generate action figure images with specified style"""
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    logger.info(f"🆔 New job submitted: {job_id}")
    logger.info(f"📝 Job details: accessories=[{accessory_1}, {accessory_2}, {accessory_3}]")
    
    try:
        # Validate file type
        if not user_image.content_type.startswith('image/'):
            logger.error(f"❌ Invalid file type '{user_image.content_type}' for job {job_id}")
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Validate file size
        content = await user_image.read()
        file_size_mb = len(content) / (1024 * 1024)
        logger.info(f"📁 Uploaded file: {user_image.filename} ({file_size_mb:.2f} MB)")
        
        if len(content) > settings.MAX_FILE_SIZE:
            logger.error(f"❌ File too large ({file_size_mb:.2f} MB) for job {job_id}")
            raise HTTPException(
                status_code=400,
                detail=f"File size too large. Maximum {settings.MAX_FILE_SIZE // (1024*1024)}MB allowed."
            )
        
        # Create job record
        job_data = {
            "job_id": job_id,
            "status": "queued",
            "progress": {
                "upload": "pending",
                "ai_generation": "pending",
                "background_removal": "pending",
                "3d_conversion": "pending",
                "sticker_generation": "pending"  # Renamed from blender_processing
            },
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "input_data": {
                "accessories": [accessory_1, accessory_2, accessory_3],
                "original_filename": user_image.filename,
                "file_size_mb": file_size_mb
            },
            "generation_config": {
                "size": settings.IMAGE_SIZE,
                "quality": settings.IMAGE_QUALITY,
                "transparent_background": settings.TRANSPARENT_BACKGROUND,
                "model": settings.OPENAI_MODEL,
                "hunyuan3d_config": {
                    "octree_resolution": settings.HUNYUAN3D_OCTREE_RESOLUTION,
                    "inference_steps": settings.HUNYUAN3D_INFERENCE_STEPS,
                    "guidance_scale": settings.HUNYUAN3D_GUIDANCE_SCALE,
                    "face_count": settings.HUNYUAN3D_FACE_COUNT
                }
            },
            "result": None,
            "error": None
        }
        
        # Store job data
        job_storage[job_id] = job_data
        logger.info(f"💾 Job {job_id} stored in memory")
        
        # Save uploaded image
        upload_path = os.path.join(settings.UPLOAD_PATH, job_id)
        os.makedirs(upload_path, exist_ok=True)
        
        file_extension = user_image.filename.split('.')[-1] if '.' in user_image.filename else 'jpg'
        image_path = os.path.join(upload_path, f"user_image.{file_extension}")
        
        # Write the content we already read
        async with aiofiles.open(image_path, 'wb') as f:
            await f.write(content)
        
        logger.info(f"💾 User image saved: {image_path}")
        
        # Update job with image path
        job_storage[job_id]["input_data"]["user_image_path"] = image_path
        
        # Start background processing
        background_tasks.add_task(process_job, job_id)
        logger.info(f"🚀 Background processing started for job {job_id}")
        
        return JobSubmissionResponse(
            job_id=job_id,
            status="queued",
            message=f"Job submitted successfully. Use /job-status/{job_id} to check progress.",
            submitted_at=job_data["created_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error in submit_job for {job_id}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/job-status/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get the status of a submitted job"""
    logger.info(f"📊 Status request for job {job_id}")
    
    if job_id not in job_storage:
        logger.error(f"❌ Job {job_id} not found")
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_data = job_storage[job_id]
    logger.info(f"📊 Job {job_id} status: {job_data['status']}")
    
    return JobStatus(**job_data)

@app.get("/jobs")
async def list_jobs():
    """List all jobs (for debugging)"""
    logger.info(f"📋 Listing all jobs - Total: {len(job_storage)}")

    return {
        "total_jobs": len(job_storage),
        "jobs": [
            {
                "job_id": job_id,
                "status": job_data["status"],
                "created_at": job_data["created_at"],
                "updated_at": job_data["updated_at"],
                "generation_config": job_data.get("generation_config", {}),
                "result": job_data.get("result")  # Include result for file downloads
            }
            for job_id, job_data in job_storage.items()
        ]
    }

@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its files"""
    logger.info(f"🗑️ Deleting job {job_id}")
    
    if job_id not in job_storage:
        logger.error(f"❌ Job {job_id} not found for deletion")
        raise HTTPException(status_code=404, detail="Job not found")
    
    try:
        # Remove job from storage
        del job_storage[job_id]
        
        # Clean up files
        import shutil
        
        # Upload files
        job_path = os.path.join(settings.UPLOAD_PATH, job_id)
        if os.path.exists(job_path):
            shutil.rmtree(job_path)
            logger.info(f"🗑️ Deleted upload files for job {job_id}")
        
        # Generated files
        generated_path = os.path.join(settings.GENERATED_PATH, job_id)
        if os.path.exists(generated_path):
            shutil.rmtree(generated_path)
            logger.info(f"🗑️ Deleted generated files for job {job_id}")
        
        # Processed files
        processed_path = os.path.join(settings.PROCESSED_PATH, job_id)
        if os.path.exists(processed_path):
            shutil.rmtree(processed_path)
            logger.info(f"🗑️ Deleted processed files for job {job_id}")
        
        logger.info(f"✅ Job {job_id} deleted successfully")
        return {"message": f"Job {job_id} deleted successfully"}
        
    except Exception as e:
        logger.error(f"❌ Error deleting job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")

@app.get("/health")
async def health_check():
    """Comprehensive health check"""
    logger.info("🏥 Health check requested")
    
    try:
        # Check service health
        sticker_maker_health = await sticker_maker.health_check()
        hunyuan_health = await threed_client.health_check()

        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "active_jobs": len([j for j in job_storage.values() if j["status"] in ["queued", "processing"]]),
            "total_jobs": len(job_storage),
            "ai_generator": "healthy",
            "services": {
                "ai_generator": "healthy",
                "sticker_maker": "healthy" if sticker_maker_health else "unhealthy",  # Changed from blender_processor
                "threed_client": "healthy" if hunyuan_health else "unhealthy"
            },
            "config": {
                "image_size": settings.IMAGE_SIZE,
                "image_quality": settings.IMAGE_QUALITY,
                "transparent_background": settings.TRANSPARENT_BACKGROUND,
                "model": settings.OPENAI_MODEL,
                "sticker_maker_executable": settings.STICKER_MAKER_EXECUTABLE,  # Changed from blender_executable
                "hunyuan3d_api": settings.HUNYUAN3D_API_URL
            }
        }
        
        logger.info(f"✅ Health check completed - Services: AI=✅, StickerMaker={'✅' if sticker_maker_health else '❌'}, Hunyuan3D={'✅' if hunyuan_health else '❌'}")
        
        return health_data
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

@app.get("/debug/job/{job_id}")
async def debug_job(job_id: str):
    """Debug endpoint to see full job details"""
    logger.info(f"🔍 Debug request for job {job_id}")
    
    if job_id not in job_storage:
        logger.error(f"❌ Job {job_id} not found for debug")
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_data = job_storage[job_id]
    
    # Check file existence
    files_check = {
        "upload_dir": os.path.exists(os.path.join(settings.UPLOAD_PATH, job_id)),
        "generated_dir": os.path.exists(os.path.join(settings.GENERATED_PATH, job_id)),
        "processed_dir": os.path.exists(os.path.join(settings.PROCESSED_PATH, job_id)),
        "user_image": os.path.exists(job_data["input_data"].get("user_image_path", ""))
    }
    
    # List files in directories
    file_listings = {}
    for dir_name, dir_path in [
        ("upload", os.path.join(settings.UPLOAD_PATH, job_id)),
        ("generated", os.path.join(settings.GENERATED_PATH, job_id)),
        ("processed", os.path.join(settings.PROCESSED_PATH, job_id))
    ]:
        if os.path.exists(dir_path):
            try:
                file_listings[dir_name] = os.listdir(dir_path)
            except Exception as e:
                file_listings[dir_name] = f"Error listing files: {e}"
        else:
            file_listings[dir_name] = "Directory does not exist"
    
    debug_info = {
        "job_data": job_data,
        "files_exist": files_check,
        "file_listings": file_listings,
        "system_info": {
            "upload_path": settings.UPLOAD_PATH,
            "generated_path": settings.GENERATED_PATH,
            "processed_path": settings.PROCESSED_PATH
        }
    }
    
    logger.info(f"🔍 Debug info compiled for job {job_id}")
    return debug_info

# Background processing function
async def process_job(job_id: str):
    """Process the job in background with full 3D pipeline"""
    logger.info(f"🚀 Starting background processing for job {job_id}")
    
    try:
        # Update status
        job_storage[job_id]["status"] = "processing"
        job_storage[job_id]["progress"]["upload"] = "completed"
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()
        
        # Get job data
        job_data = job_storage[job_id]
        user_image_path = job_data["input_data"]["user_image_path"]
        accessories = job_data["input_data"]["accessories"]
    
        logger.info(f"🎨 Processing job {job_id}")
        
        logger.info(f"📐 Config: Size={settings.IMAGE_SIZE}, Quality={settings.IMAGE_QUALITY}, Transparent={settings.TRANSPARENT_BACKGROUND}")
        logger.info(f"🔧 3D Config: Resolution={settings.HUNYUAN3D_OCTREE_RESOLUTION}, Steps={settings.HUNYUAN3D_INFERENCE_STEPS}")
        
        # STEP 1: AI Image Generation
        logger.info(f"🎨 Step 1: Starting AI image generation for job {job_id}")
        job_storage[job_id]["progress"]["ai_generation"] = "processing"
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()
        
        generated_images = await ai_generator.generate_action_figures(
            job_id=job_id,
            user_image_path=user_image_path,
            accessories=accessories
        )
        
        if not generated_images:
            raise Exception("No images were generated by AI")
        
        logger.info(f"✅ Step 1 completed: Generated {len(generated_images)} images")
        job_storage[job_id]["progress"]["ai_generation"] = "completed"
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()
        
        # STEP 2: Background Removal using ComfyUI
        logger.info(f"🖼️ Step 2: Starting ComfyUI background removal for job {job_id}")
        job_storage[job_id]["progress"]["background_removal"] = "processing"
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()
        
        # Initialize ComfyUI background remover
        bg_remover = ComfyUIBackgroundRemover()
        
        processed_images = []
        for img_data in generated_images:
            try:
                # Create output path for processed image
                base_name = os.path.splitext(img_data["file_path"])[0]
                processed_path = f"{base_name}_nobg.png"
                
                # Use ComfyUI for background removal
                success = await bg_remover.remove_background_single(
                    img_data["file_path"], 
                    processed_path
                )

                if success and os.path.exists(processed_path):
                    img_data["processed_path"] = processed_path
                    logger.info(f"✅ ComfyUI background removed for {img_data['filename']}")
                else:
                    img_data["processed_path"] = img_data["file_path"]
                    logger.info(f"⚠️ ComfyUI failed, using original for {img_data['filename']}")
                
                processed_images.append(img_data)
                
            except Exception as e:
                logger.error(f"❌ ComfyUI background removal failed for {img_data['filename']}: {e}")
                # Use original image if background removal fails
                img_data["processed_path"] = img_data["file_path"]
                processed_images.append(img_data)
        
        # STEP 3: 3D Model Generation
        logger.info(f"🎯 Step 3: Starting 3D model generation for job {job_id}")
        job_storage[job_id]["progress"]["3d_conversion"] = "processing"
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()
        
        models_3d = []
        for i, img_data in enumerate(processed_images):
            try:
                logger.info(f"🔄 Converting image {i+1}/{len(processed_images)} to 3D: {img_data['filename']}")
                
                # Determine model type based on content
                model_type = "accessory"
                if "base_character" in img_data.get("type", "").lower():
                    model_type = "base_character"
                elif i == 0:  # First image is usually the main character
                    model_type = "base_character"
                
                # Generate 3D model
                output_dir = os.path.join(settings.GENERATED_PATH, job_id)
                model_3d = await threed_client.generate_3d_model(
                    image_path=img_data["processed_path"],
                    job_id=job_id
                )
                
                if model_3d and model_3d.get("success"):
                    models_3d.append(model_3d)
                    logger.info(f"✅ 3D model generated: {model_3d.get('model_path', 'Unknown path')}")
                else:
                    logger.error(f"❌ 3D model generation failed for {img_data['filename']}")
                    # Continue with other images even if one fails
                
            except Exception as e:
                logger.error(f"❌ 3D conversion error for {img_data['filename']}: {e}")
                # Continue processing other images
                continue
        
        if not models_3d:
            raise Exception("No 3D models were generated successfully")
        
        logger.info(f"✅ Step 3 completed: Generated {len(models_3d)} 3D models")
        job_storage[job_id]["progress"]["3d_conversion"] = "completed"
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()
        
        # STEP 4: Sticker Generation (replaces old Blender processing)
        logger.info(f"🖨️ Step 4: Starting sticker generation for job {job_id}")
        job_storage[job_id]["progress"]["sticker_generation"] = "processing"
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()

        # Process 3D models into printable stickers
        # This includes: Blender layout, 2D composition, boundary detection, DXF export
        sticker_result = await sticker_maker.process_3d_models(
            job_id=job_id,
            models_3d=models_3d,
            processed_images=processed_images  # Pass the nobg images
        )

        if not sticker_result or not sticker_result.get("success"):
            raise Exception(f"Sticker generation failed: {sticker_result.get('error', 'Unknown error')}")

        logger.info(f"✅ Step 4 completed: Sticker generation successful")
        job_storage[job_id]["progress"]["sticker_generation"] = "completed"
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()
        
        # FINAL: Update job with complete results
        final_result = {
            "generated_images": generated_images,
            "processed_images": processed_images,
            "models_3d": models_3d,
            "sticker_result": sticker_result,  # Changed from blender_result
            "blender_result": sticker_result,  # Keep for backwards compatibility with shopify_handler
            "total_images": len(generated_images),
            "total_3d_models": len(models_3d),
            "image_urls": [f"http://3.214.30.160:8000{img['url']}" for img in generated_images],
            "generation_details": {
                "size": settings.IMAGE_SIZE,
                "quality": settings.IMAGE_QUALITY,
                "transparent_background": settings.TRANSPARENT_BACKGROUND,
                "models_used": list(set([img.get("model_used", "unknown") for img in generated_images])),
                "3d_models_generated": len(models_3d),
                "sticker_files": sticker_result.get("output_files", [])  # Changed from blender_files
            },
            "download_links": {
                "images": [img["url"] for img in generated_images],
                "3d_models": [model.get("download_url") for model in models_3d if model.get("download_url")],
                "sticker_files": [file_info.get("download_url") for file_info in sticker_result.get("output_files", []) if file_info.get("download_url")]  # Changed from final_files
            }
        }
        
        # Update job status
        job_storage[job_id]["status"] = "completed"
        job_storage[job_id]["result"] = final_result
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"🎉 Job {job_id} completed successfully!")
        logger.info(f"📊 Final stats: {len(generated_images)} images, {len(models_3d)} 3D models, {len(sticker_result.get('output_files', []))} sticker files")
        
    except Exception as e:
        # Handle errors
        error_msg = str(e)
        logger.error(f"❌ Job {job_id} failed: {error_msg}")
        logger.error(f"❌ Full traceback: {traceback.format_exc()}")
        
        job_storage[job_id]["status"] = "failed"
        job_storage[job_id]["error"] = error_msg
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()
        
        # Update failed progress
        for step in job_storage[job_id]["progress"]:
            if job_storage[job_id]["progress"][step] == "processing":
                job_storage[job_id]["progress"][step] = "failed"
                break  # Only mark the current processing step as failed

try:
    shopify_handler = ShopifyHandler(job_storage, process_job)
    logger.info("✅ Shopify Handler initialized")
except Exception as e:
    logger.error(f"❌ Failed to initialize Shopify Handler: {e}")
    shopify_handler = None

# Additional utility endpoints
@app.get("/stats")
async def get_stats():
    """Get system statistics"""
    logger.info("📊 Stats requested")
    
    try:
        # Job statistics
        total_jobs = len(job_storage)
        completed_jobs = len([j for j in job_storage.values() if j["status"] == "completed"])
        failed_jobs = len([j for j in job_storage.values() if j["status"] == "failed"])
        processing_jobs = len([j for j in job_storage.values() if j["status"] == "processing"])
        queued_jobs = len([j for j in job_storage.values() if j["status"] == "queued"])
        
        # File system statistics
        def get_dir_size(path):
            total = 0
            try:
                for dirpath, dirnames, filenames in os.walk(path):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        if os.path.exists(filepath):
                            total += os.path.getsize(filepath)
            except:
                pass
            return total
        
        storage_stats = {
            "upload_size_mb": round(get_dir_size(settings.UPLOAD_PATH) / (1024*1024), 2),
            "generated_size_mb": round(get_dir_size(settings.GENERATED_PATH) / (1024*1024), 2),
            "processed_size_mb": round(get_dir_size(settings.PROCESSED_PATH) / (1024*1024), 2)
        }
        
        stats = {
            "timestamp": datetime.now().isoformat(),
            "jobs": {
                "total": total_jobs,
                "completed": completed_jobs,
                "failed": failed_jobs,
                "processing": processing_jobs,
                "queued": queued_jobs,
                "success_rate": round((completed_jobs / total_jobs * 100) if total_jobs > 0 else 0, 2)
            },
            "storage": storage_stats,
            "system": {
                "api_version": "1.0.0"
            }
        }
        
        logger.info(f"📊 Stats compiled: {total_jobs} total jobs, {completed_jobs} completed")
        return stats
        
    except Exception as e:
        logger.error(f"❌ Error generating stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate stats: {str(e)}")

@app.post("/test-services")
async def test_services():
    """Test all services functionality"""
    logger.info("🧪 Testing all services...")
    
    test_results = {
        "timestamp": datetime.now().isoformat(),
        "ai_generator": {"status": "unknown", "details": {}},
        "threed_client": {"status": "unknown", "details": {}},
        "blender_processor": {"status": "unknown", "details": {}}
    }
    
    # Test AI Generator
    try:
        logger.info("🧪 Testing AI Image Generator...")
        test_results["ai_generator"] = {
            "status": "healthy",
            "details": {
                "openai_model": settings.OPENAI_MODEL
            }
        }
        logger.info("✅ AI Generator test passed")
    except Exception as e:
        logger.error(f"❌ AI Generator test failed: {e}")
        test_results["ai_generator"] = {
            "status": "failed",
            "details": {"error": str(e)}
        }
    
    # Test Hunyuan3D Client
    try:
        logger.info("🧪 Testing Hunyuan3D Client...")
        hunyuan_health = await threed_client.health_check()
        test_results["threed_client"] = {
            "status": "healthy" if hunyuan_health else "unhealthy",
            "details": {
                "api_url": settings.HUNYUAN3D_API_URL,
                "health_check_passed": hunyuan_health,
                "config": {
                    "octree_resolution": settings.HUNYUAN3D_OCTREE_RESOLUTION,
                    "inference_steps": settings.HUNYUAN3D_INFERENCE_STEPS,
                    "guidance_scale": settings.HUNYUAN3D_GUIDANCE_SCALE
                }
            }
        }
        logger.info(f"{'✅' if hunyuan_health else '❌'} Hunyuan3D test {'passed' if hunyuan_health else 'failed'}")
    except Exception as e:
        logger.error(f"❌ Hunyuan3D test failed: {e}")
        test_results["threed_client"] = {
            "status": "failed",
            "details": {"error": str(e)}
        }
    
    # Test Blender Processor
    try:
        logger.info("🧪 Testing Blender Processor...")
        blender_health = await blender_processor.health_check()
        
        # Try to create a simple test STL
        import tempfile
        test_stl_path = os.path.join(tempfile.gettempdir(), f"blender_test_{uuid.uuid4().hex[:8]}.stl")
        test_stl_created = await blender_processor.create_simple_test_stl(test_stl_path)
        
        # Clean up test file
        if os.path.exists(test_stl_path):
            os.remove(test_stl_path)
        
        test_results["blender_processor"] = {
            "status": "healthy" if (blender_health and test_stl_created) else "unhealthy",
            "details": {
                "executable": settings.BLENDER_EXECUTABLE,
                "health_check_passed": blender_health,
                "test_stl_created": test_stl_created,
                "headless_mode": True
            }
        }
        logger.info(f"{'✅' if (blender_health and test_stl_created) else '❌'} Blender test {'passed' if (blender_health and test_stl_created) else 'failed'}")
    except Exception as e:
        logger.error(f"❌ Blender test failed: {e}")
        test_results["blender_processor"] = {
            "status": "failed",
            "details": {"error": str(e)}
        }
    
    # Overall status
    all_healthy = all(
        result["status"] == "healthy" 
        for result in test_results.values() 
        if isinstance(result, dict) and "status" in result
    )
    
    test_results["overall_status"] = "healthy" if all_healthy else "degraded"
    test_results["summary"] = {
        "all_services_healthy": all_healthy,
        "healthy_services": len([r for r in test_results.values() if isinstance(r, dict) and r.get("status") == "healthy"]),
        "total_services": 3
    }
    
    logger.info(f"🧪 Service tests completed - Overall: {'✅ Healthy' if all_healthy else '⚠️ Degraded'}")
    
    return test_results

@app.get("/logs/{lines}")
async def get_recent_logs(lines: int = 100):
    """Get recent log entries"""
    logger.info(f"📋 Fetching last {lines} log lines")
    
    try:
        if lines > 1000:
            lines = 1000  # Limit to prevent memory issues
        
        log_file = "app.log"
        if not os.path.exists(log_file):
            return {"error": "Log file not found", "logs": []}
        
        # Read last N lines
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        return {
            "total_lines": len(all_lines),
            "returned_lines": len(recent_lines),
            "logs": [line.strip() for line in recent_lines]
        }
        
    except Exception as e:
        logger.error(f"❌ Error reading logs: {e}")
        return {"error": str(e), "logs": []}

@app.post("/cleanup")
async def cleanup_old_jobs():
    """Clean up old completed/failed jobs and their files"""
    logger.info("🧹 Starting cleanup of old jobs...")
    
    try:
        from datetime import timedelta
        import shutil
        
        cutoff_time = datetime.now() - timedelta(hours=24)  # Clean jobs older than 24 hours
        cleaned_jobs = []
        
        jobs_to_clean = []
        for job_id, job_data in job_storage.items():
            try:
                job_time = datetime.fromisoformat(job_data["created_at"])
                if job_time < cutoff_time and job_data["status"] in ["completed", "failed"]:
                    jobs_to_clean.append(job_id)
            except:
                continue
        
        for job_id in jobs_to_clean:
            try:
                # Remove files
                for path_type, base_path in [
                    ("upload", settings.UPLOAD_PATH),
                    ("generated", settings.GENERATED_PATH),
                    ("processed", settings.PROCESSED_PATH)
                ]:
                    job_path = os.path.join(base_path, job_id)
                    if os.path.exists(job_path):
                        shutil.rmtree(job_path)
                
                # Remove from storage
                job_status = job_storage[job_id]["status"]
                del job_storage[job_id]
                
                cleaned_jobs.append({
                    "job_id": job_id,
                    "status": job_status
                })
                
                logger.info(f"🧹 Cleaned up job {job_id}")
                
            except Exception as e:
                logger.error(f"❌ Error cleaning job {job_id}: {e}")
        
        logger.info(f"🧹 Cleanup completed: {len(cleaned_jobs)} jobs cleaned")
        
        return {
            "cleaned_jobs": len(cleaned_jobs),
            "jobs_cleaned": cleaned_jobs,
            "remaining_jobs": len(job_storage),
            "cutoff_time": cutoff_time.isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logger.error(f"❌ HTTP Exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.now().isoformat()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"❌ Unhandled Exception: {str(exc)}")
    logger.error(f"❌ Traceback: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 API shutting down...")
    
    # Log final statistics
    total_jobs = len(job_storage)
    completed_jobs = len([j for j in job_storage.values() if j["status"] == "completed"])
    failed_jobs = len([j for j in job_storage.values() if j["status"] == "failed"])
    
    logger.info(f"📊 Final stats: {total_jobs} total jobs, {completed_jobs} completed, {failed_jobs} failed")
    logger.info("👋 SimpleMe API shutdown complete")

# ================================
# Sculptok Test Pipeline Endpoints
# ================================

from services.sculptok_client import SculptokClient, create_sculptok_client

# Initialize Sculptok client for testing
try:
    sculptok_client = create_sculptok_client()
    logger.info("✅ Sculptok Client initialized for testing")
except Exception as e:
    logger.warning(f"⚠️ Sculptok Client initialization failed: {e}")
    sculptok_client = None

@app.get("/test/sculptok/health")
async def test_sculptok_health():
    """Health check for Sculptok API"""
    if not sculptok_client:
        return {"healthy": False, "error": "Sculptok client not initialized"}

    result = await sculptok_client.health_check()
    return result

@app.post("/test/sculptok/upload")
async def test_sculptok_upload(image: UploadFile = File(...)):
    """Test Sculptok image upload"""
    logger.info(f"🧪 [TEST] Sculptok upload test: {image.filename}")

    if not sculptok_client:
        raise HTTPException(status_code=503, detail="Sculptok client not available")

    # Save uploaded image temporarily
    test_dir = os.path.join(settings.STORAGE_PATH, "test_sculptok")
    os.makedirs(test_dir, exist_ok=True)

    temp_path = os.path.join(test_dir, f"upload_test_{image.filename}")
    content = await image.read()

    async with aiofiles.open(temp_path, 'wb') as f:
        await f.write(content)

    logger.info(f"   Saved temp file: {temp_path}")

    # Test upload
    result = await sculptok_client.upload_image(temp_path)

    return {
        "test": "upload",
        "input_file": image.filename,
        "temp_path": temp_path,
        "result": result
    }

@app.post("/test/sculptok/bg-remove")
async def test_sculptok_bg_remove(image_url: str):
    """Test Sculptok background removal"""
    logger.info(f"🧪 [TEST] Sculptok BG removal test: {image_url}")

    if not sculptok_client:
        raise HTTPException(status_code=503, detail="Sculptok client not available")

    # Submit background removal
    result = await sculptok_client.remove_background(image_url)

    if result.get("success"):
        # Wait for completion
        prompt_id = result.get("prompt_id")
        logger.info(f"   Waiting for completion: {prompt_id}")

        complete_result = await sculptok_client.wait_for_completion(prompt_id, "BG Removal Test")
        return {
            "test": "bg_remove",
            "image_url": image_url,
            "submit_result": result,
            "completion_result": complete_result
        }

    return {
        "test": "bg_remove",
        "image_url": image_url,
        "result": result
    }

@app.post("/test/sculptok/stl")
async def test_sculptok_stl(
    image_url: str,
    width_mm: float = 120.0,
    min_thickness: float = 1.6,
    max_thickness: float = 5.0
):
    """Test Sculptok STL generation"""
    logger.info(f"🧪 [TEST] Sculptok STL generation test: {image_url}")

    if not sculptok_client:
        raise HTTPException(status_code=503, detail="Sculptok client not available")

    # Submit STL generation
    result = await sculptok_client.submit_stl(
        image_url,
        width_mm=width_mm,
        min_thickness=min_thickness,
        max_thickness=max_thickness
    )

    if result.get("success"):
        # Wait for completion
        prompt_id = result.get("prompt_id")
        logger.info(f"   Waiting for completion: {prompt_id}")

        complete_result = await sculptok_client.wait_for_completion(prompt_id, "STL Generation Test")
        return {
            "test": "stl_generation",
            "image_url": image_url,
            "params": {
                "width_mm": width_mm,
                "min_thickness": min_thickness,
                "max_thickness": max_thickness
            },
            "submit_result": result,
            "completion_result": complete_result
        }

    return {
        "test": "stl_generation",
        "image_url": image_url,
        "result": result
    }

@app.get("/test/sculptok/status/{prompt_id}")
async def test_sculptok_status(prompt_id: str):
    """Check status of a Sculptok task"""
    logger.info(f"🧪 [TEST] Sculptok status check: {prompt_id}")

    if not sculptok_client:
        raise HTTPException(status_code=503, detail="Sculptok client not available")

    result = await sculptok_client.get_status(prompt_id)
    return {
        "test": "status_check",
        "prompt_id": prompt_id,
        "result": result
    }

@app.post("/test/sculptok/full-pipeline")
async def test_sculptok_full_pipeline(
    image: UploadFile = File(...),
    width_mm: float = Form(default=120.0),
    skip_bg_removal: bool = Form(default=False)
):
    """
    Test full Sculptok pipeline: Upload -> BG Remove -> STL -> Download

    This endpoint tests the complete flow with detailed logging.
    """
    logger.info(f"🧪 [TEST] Full Sculptok pipeline test: {image.filename}")
    logger.info(f"   Parameters: width_mm={width_mm}, skip_bg_removal={skip_bg_removal}")

    if not sculptok_client:
        raise HTTPException(status_code=503, detail="Sculptok client not available")

    # Create test directory
    test_id = str(uuid.uuid4())[:8]
    test_dir = os.path.join(settings.STORAGE_PATH, "test_sculptok", test_id)
    os.makedirs(test_dir, exist_ok=True)

    # Save uploaded image
    input_path = os.path.join(test_dir, f"input_{image.filename}")
    content = await image.read()

    async with aiofiles.open(input_path, 'wb') as f:
        await f.write(content)

    logger.info(f"   Saved input: {input_path}")

    # Run full pipeline
    result = await sculptok_client.process_image_to_stl(
        image_path=input_path,
        output_dir=test_dir,
        image_name="test_model",
        width_mm=width_mm,
        skip_bg_removal=skip_bg_removal
    )

    # Add test metadata
    result["test_id"] = test_id
    result["test_dir"] = test_dir
    result["input_file"] = image.filename

    return result

@app.post("/test/sculptok/gpt-to-stl")
async def test_gpt_to_sculptok_pipeline(
    user_image: UploadFile = File(...),
    accessory_1: str = Form(...),
    accessory_2: str = Form(...),
    accessory_3: str = Form(...),
    width_mm: float = Form(default=120.0)
):
    """
    Test full pipeline: User Image -> GPT-image-1.5 -> Sculptok STL

    This tests the complete new pipeline with:
    1. GPT-image-1.5 for character + accessory generation
    2. Sculptok for background removal + 2.5D STL generation
    """
    logger.info(f"🧪 [TEST] Full GPT -> Sculptok pipeline test")
    logger.info(f"   User image: {user_image.filename}")
    logger.info(f"   Accessories: {accessory_1}, {accessory_2}, {accessory_3}")

    if not sculptok_client:
        raise HTTPException(status_code=503, detail="Sculptok client not available")

    # Create test job
    test_id = str(uuid.uuid4())[:8]
    test_dir = os.path.join(settings.STORAGE_PATH, "test_sculptok", test_id)
    os.makedirs(test_dir, exist_ok=True)

    results = {
        "test_id": test_id,
        "test_dir": test_dir,
        "steps": {},
        "outputs": {}
    }

    try:
        # Step 1: Save user image
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 1: Save User Image")
        logger.info(f"{'='*60}")

        user_image_path = os.path.join(test_dir, f"user_image_{user_image.filename}")
        content = await user_image.read()

        async with aiofiles.open(user_image_path, 'wb') as f:
            await f.write(content)

        results["steps"]["save_user_image"] = {"success": True, "path": user_image_path}
        logger.info(f"   Saved: {user_image_path}")

        # Step 2: Generate images with GPT-image-1.5
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 2: Generate Images with GPT-image-1.5")
        logger.info(f"{'='*60}")

        accessories = [accessory_1, accessory_2, accessory_3]
        generated_images = await ai_generator.generate_action_figures(
            job_id=test_id,
            user_image_path=user_image_path,
            accessories=accessories
        )

        results["steps"]["gpt_generation"] = {
            "success": len(generated_images) > 0,
            "count": len(generated_images),
            "images": generated_images
        }
        logger.info(f"   Generated {len(generated_images)} images")

        # Step 3: Process each image through Sculptok
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 3: Process Images through Sculptok")
        logger.info(f"{'='*60}")

        sculptok_results = []
        for i, img_data in enumerate(generated_images):
            img_path = img_data.get("file_path")  # AI generator uses "file_path" not "path"
            img_type = img_data.get("type", f"image_{i}")

            logger.info(f"\n   Processing {img_type}: {img_path}")

            output_subdir = os.path.join(test_dir, "sculptok_output", img_type)
            os.makedirs(output_subdir, exist_ok=True)

            sculptok_result = await sculptok_client.process_image_to_stl(
                image_path=img_path,
                output_dir=output_subdir,
                image_name=img_type,
                width_mm=width_mm,
                skip_bg_removal=False  # Use Sculptok for BG removal
            )

            sculptok_results.append({
                "type": img_type,
                "input": img_path,
                "result": sculptok_result
            })

            if sculptok_result.get("success"):
                results["outputs"][img_type] = sculptok_result.get("outputs", {})

        results["steps"]["sculptok_processing"] = {
            "success": any(r["result"].get("success") for r in sculptok_results),
            "results": sculptok_results
        }

        # Summary
        results["success"] = (
            results["steps"].get("gpt_generation", {}).get("success", False) and
            results["steps"].get("sculptok_processing", {}).get("success", False)
        )

        logger.info(f"\n{'='*60}")
        logger.info(f"PIPELINE COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"   Success: {results['success']}")
        logger.info(f"   Outputs: {list(results['outputs'].keys())}")

        return results

    except Exception as e:
        logger.error(f"❌ Pipeline error: {e}")
        logger.error(traceback.format_exc())
        results["error"] = str(e)
        results["success"] = False
        return results

@app.post("/test/sculptok/reprocess/{test_id}")
async def test_reprocess_existing_images(
    test_id: str,
    width_mm: float = 120.0,
    skip_bg_removal: bool = True  # Skip since GPT images already have transparent bg
):
    """
    Reprocess existing generated images through Sculptok without regenerating.

    Use this to skip GPT image generation and just run Sculptok on existing images.
    Example: POST /test/sculptok/reprocess/ca767ebc
    """
    from services.sculptok_client import SculptokClient

    sculptok_client = SculptokClient()

    # Find existing images
    generated_dir = os.path.join(settings.GENERATED_PATH, test_id)
    if not os.path.exists(generated_dir):
        return {"success": False, "error": f"No generated images found for test_id: {test_id}"}

    # Get all PNG files
    import glob
    image_files = glob.glob(os.path.join(generated_dir, "*.png"))

    if not image_files:
        return {"success": False, "error": f"No PNG images found in {generated_dir}"}

    logger.info(f"\n{'='*60}")
    logger.info(f"REPROCESSING {len(image_files)} EXISTING IMAGES")
    logger.info(f"{'='*60}")
    logger.info(f"   Test ID: {test_id}")
    logger.info(f"   Images: {image_files}")

    # Create output directory
    test_output_dir = os.path.join("./storage/test_sculptok", test_id)
    os.makedirs(test_output_dir, exist_ok=True)

    results = {
        "test_id": test_id,
        "success": False,
        "images_found": len(image_files),
        "sculptok_results": [],
        "outputs": {}
    }

    try:
        for img_path in sorted(image_files):
            # Extract image type from filename (e.g., "base_character" from "base_character_20260130_172548.png")
            filename = os.path.basename(img_path)
            # Remove timestamp and extension
            img_type = "_".join(filename.split("_")[:-2]) if filename.count("_") >= 2 else filename.rsplit(".", 1)[0]

            logger.info(f"\n   Processing {img_type}: {img_path}")

            output_subdir = os.path.join(test_output_dir, "sculptok_output", img_type)
            os.makedirs(output_subdir, exist_ok=True)

            sculptok_result = await sculptok_client.process_image_to_stl(
                image_path=img_path,
                output_dir=output_subdir,
                image_name=img_type,
                width_mm=width_mm,
                skip_bg_removal=skip_bg_removal
            )

            results["sculptok_results"].append({
                "type": img_type,
                "input": img_path,
                "result": sculptok_result
            })

            if sculptok_result.get("success"):
                results["outputs"][img_type] = sculptok_result.get("outputs", {})
                logger.info(f"   ✅ {img_type} processed successfully")
            else:
                logger.error(f"   ❌ {img_type} failed: {sculptok_result.get('error')}")

        results["success"] = any(r["result"].get("success") for r in results["sculptok_results"])

        logger.info(f"\n{'='*60}")
        logger.info(f"REPROCESSING COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"   Success: {results['success']}")
        logger.info(f"   Outputs: {list(results['outputs'].keys())}")

        return results

    except Exception as e:
        logger.error(f"❌ Reprocessing error: {e}")
        logger.error(traceback.format_exc())
        results["error"] = str(e)
        return results

@app.get("/test/sculptok")
async def test_sculptok_page():
    """Serve the Sculptok test page"""
    return FileResponse('/workspace/SimpleMe/test_sculptok.html')


# ================================
# Starter Pack Pipeline (NEW)
# ================================

@app.post("/test/starter-pack/full-pipeline")
async def test_starter_pack_full_pipeline(
    # User photo for figure
    user_image: UploadFile = File(...),
    # Accessory descriptions
    accessory_1: str = Form(...),
    accessory_2: str = Form(...),
    accessory_3: str = Form(...),
    # Title and subtitle
    title: str = Form(...),
    subtitle: str = Form(default=""),
    # Text color
    text_color: str = Form(default="red"),
    # Background options
    background_type: str = Form(default="transparent"),  # transparent, solid, image
    background_color: str = Form(default="white"),  # For solid backgrounds
    background_description: str = Form(default=""),  # For GPT-generated backgrounds
    background_image: Optional[UploadFile] = File(default=None),  # For user-uploaded backgrounds
):
    """
    Full Starter Pack Pipeline:

    1. GPT-image-1.5: Generate base character + 3 accessories + optional background
    2. Sculptok: Generate depth maps for character + accessories (high quality)
    3. Blender: Create STL + UV texture using blender_starter_pack.py

    Background options:
    - transparent: No background (transparent)
    - solid: Solid color background (use background_color)
    - image: GPT-generated or user-uploaded background
      - If background_image is provided: Enhance user's image with GPT
      - If background_description is provided: Generate new image from description

    Returns:
        - STL file path
        - UV texture file path
        - Blend file path
        - All intermediate files
    """
    logger.info(f"🚀 [STARTER_PACK] Starting full pipeline")
    logger.info(f"   User image: {user_image.filename}")
    logger.info(f"   Accessories: {accessory_1}, {accessory_2}, {accessory_3}")
    logger.info(f"   Title: {title}, Subtitle: {subtitle}")
    logger.info(f"   Text color: {text_color}")
    logger.info(f"   Background: type={background_type}, color={background_color}")

    if not sculptok_client:
        raise HTTPException(status_code=503, detail="Sculptok client not available")

    # Create job directory
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(settings.STORAGE_PATH, "test_starter_pack", job_id)
    os.makedirs(job_dir, exist_ok=True)

    results = {
        "job_id": job_id,
        "job_dir": job_dir,
        "success": False,
        "steps": {},
        "outputs": {},
        "errors": []
    }

    try:
        # ============================================================
        # STEP 1: Save user image
        # ============================================================
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 1: Save User Image")
        logger.info(f"{'='*60}")

        user_image_path = os.path.join(job_dir, f"user_image_{user_image.filename}")
        content = await user_image.read()

        async with aiofiles.open(user_image_path, 'wb') as f:
            await f.write(content)

        results["steps"]["save_user_image"] = {"success": True, "path": user_image_path}
        logger.info(f"   ✅ Saved: {user_image_path}")

        # ============================================================
        # STEP 2: Generate images with GPT-image-1.5
        # ============================================================
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 2: Generate Images with GPT-image-1.5")
        logger.info(f"{'='*60}")

        accessories = [accessory_1, accessory_2, accessory_3]
        generated_images = await ai_generator.generate_action_figures(
            job_id=job_id,
            user_image_path=user_image_path,
            accessories=accessories
        )

        if not generated_images:
            error_msg = "GPT-image-1.5 failed to generate images"
            logger.error(f"   ❌ {error_msg}")
            results["errors"].append(error_msg)
            results["steps"]["gpt_generation"] = {"success": False, "error": error_msg}
            return results

        results["steps"]["gpt_generation"] = {
            "success": True,
            "count": len(generated_images),
            "images": [img.get("file_path") for img in generated_images]
        }
        logger.info(f"   ✅ Generated {len(generated_images)} images")

        # Separate figure and accessories
        figure_img = None
        accessory_imgs = []
        for img in generated_images:
            if "base_character" in img.get("type", ""):
                figure_img = img
            else:
                accessory_imgs.append(img)

        if not figure_img:
            error_msg = "No base character image generated"
            logger.error(f"   ❌ {error_msg}")
            results["errors"].append(error_msg)
            return results

        # ============================================================
        # STEP 2b: Handle background image (if needed)
        # ============================================================
        background_image_path = None

        if background_type == "image":
            logger.info(f"\n{'='*60}")
            logger.info(f"STEP 2b: Generate/Enhance Background Image")
            logger.info(f"{'='*60}")

            if background_image:
                # User uploaded a reference image - enhance it with GPT
                logger.info(f"   Using user-uploaded reference image")

                # Save uploaded background
                bg_input_path = os.path.join(job_dir, f"bg_input_{background_image.filename}")
                bg_content = await background_image.read()
                async with aiofiles.open(bg_input_path, 'wb') as f:
                    await f.write(bg_content)

                # Enhance with GPT-image-1.5 (reimagine without changing)
                try:
                    from openai import OpenAI
                    client = OpenAI(api_key=settings.OPENAI_API_KEY)

                    enhance_prompt = """Enhance this image to be a high-resolution, detailed background.
Keep the exact same composition and elements, but add more details and improve quality.
Make it suitable for UV printing at 300 DPI.
Do not change the subject or composition - only enhance quality and details."""

                    with open(bg_input_path, 'rb') as img_file:
                        response = client.images.edit(
                            model="gpt-image-1.5",
                            image=img_file,
                            prompt=enhance_prompt,
                            size="1024x1536",
                            quality="high",
                            output_format="png",
                            n=1
                        )

                    import base64
                    bg_bytes = base64.b64decode(response.data[0].b64_json)
                    background_image_path = os.path.join(job_dir, "background_enhanced.png")
                    async with aiofiles.open(background_image_path, 'wb') as f:
                        await f.write(bg_bytes)

                    logger.info(f"   ✅ Enhanced background saved: {background_image_path}")
                    results["steps"]["background_enhancement"] = {"success": True, "path": background_image_path}

                except Exception as e:
                    logger.error(f"   ❌ Background enhancement failed: {e}")
                    results["errors"].append(f"Background enhancement failed: {e}")
                    # Fall back to original uploaded image
                    background_image_path = bg_input_path

            elif background_description:
                # Generate background from description
                logger.info(f"   Generating background from description: {background_description}")

                try:
                    from openai import OpenAI
                    client = OpenAI(api_key=settings.OPENAI_API_KEY)

                    bg_prompt = f"""Create a high-quality background image for an action figure starter pack card.
The background should be: {background_description}

Requirements:
- High resolution suitable for UV printing at 300 DPI
- Vibrant colors that will print well
- Should work as a background BEHIND action figures
- No text or logos
- Seamless, visually appealing design
- Size: 130mm x 170mm aspect ratio"""

                    response = client.images.generate(
                        model="gpt-image-1.5",
                        prompt=bg_prompt,
                        size="1024x1536",
                        quality="high",
                        output_format="png",
                        n=1
                    )

                    import base64
                    bg_bytes = base64.b64decode(response.data[0].b64_json)
                    background_image_path = os.path.join(job_dir, "background_generated.png")
                    async with aiofiles.open(background_image_path, 'wb') as f:
                        await f.write(bg_bytes)

                    logger.info(f"   ✅ Generated background saved: {background_image_path}")
                    results["steps"]["background_generation"] = {"success": True, "path": background_image_path}

                except Exception as e:
                    logger.error(f"   ❌ Background generation failed: {e}")
                    results["errors"].append(f"Background generation failed: {e}")
                    # Fall back to transparent
                    background_type = "transparent"

        # ============================================================
        # STEP 3: Generate depth maps with Sculptok (HIGH QUALITY)
        # ============================================================
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 3: Generate Depth Maps (Sculptok Pro 4K 16bit)")
        logger.info(f"{'='*60}")

        depth_maps = {}
        sculptok_output_dir = os.path.join(job_dir, "sculptok_output")
        os.makedirs(sculptok_output_dir, exist_ok=True)

        # Process figure
        logger.info(f"\n   Processing figure depth map...")
        figure_sculptok_dir = os.path.join(sculptok_output_dir, "base_character")
        os.makedirs(figure_sculptok_dir, exist_ok=True)

        figure_depth_result = await sculptok_client.process_image_to_depth_map(
            image_path=figure_img.get("file_path"),
            output_dir=figure_sculptok_dir,
            image_name="base_character",
            skip_bg_removal=True,  # GPT images already have transparent bg
            style="pro",
            version="1.5",
            draw_hd="4k",
            ext_info="16bit"
        )

        if figure_depth_result.get("success"):
            depth_maps["figure"] = figure_depth_result.get("outputs", {}).get("depth_image")
            logger.info(f"   ✅ Figure depth map: {depth_maps['figure']}")
        else:
            error_msg = f"Figure depth map failed: {figure_depth_result.get('error')}"
            logger.error(f"   ❌ {error_msg}")
            results["errors"].append(error_msg)

        # Process accessories
        for i, acc_img in enumerate(accessory_imgs):
            acc_name = f"accessory_{i+1}"
            logger.info(f"\n   Processing {acc_name} depth map...")

            acc_sculptok_dir = os.path.join(sculptok_output_dir, acc_name)
            os.makedirs(acc_sculptok_dir, exist_ok=True)

            acc_depth_result = await sculptok_client.process_image_to_depth_map(
                image_path=acc_img.get("file_path"),
                output_dir=acc_sculptok_dir,
                image_name=acc_name,
                skip_bg_removal=True,
                style="pro",
                version="1.5",
                draw_hd="4k",
                ext_info="16bit"
            )

            if acc_depth_result.get("success"):
                depth_maps[acc_name] = acc_depth_result.get("outputs", {}).get("depth_image")
                logger.info(f"   ✅ {acc_name} depth map: {depth_maps[acc_name]}")
            else:
                error_msg = f"{acc_name} depth map failed: {acc_depth_result.get('error')}"
                logger.error(f"   ❌ {error_msg}")
                results["errors"].append(error_msg)

        results["steps"]["depth_maps"] = {
            "success": len(depth_maps) > 0,
            "count": len(depth_maps),
            "paths": depth_maps
        }

        if not depth_maps.get("figure"):
            error_msg = "No figure depth map generated - cannot continue"
            logger.error(f"   ❌ {error_msg}")
            results["errors"].append(error_msg)
            return results

        # ============================================================
        # STEP 4: Run Blender Starter Pack
        # ============================================================
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 4: Run Blender Starter Pack")
        logger.info(f"{'='*60}")

        blender_output_dir = os.path.join(job_dir, "final_output")
        os.makedirs(blender_output_dir, exist_ok=True)

        # Build Blender command
        blender_script = "/workspace/SimpleMe/services/blender_starter_pack.py"

        blender_cmd = [
            "blender",
            "--background",
            "--python", blender_script,
            "--",
            "--figure_depth", depth_maps.get("figure", ""),
            "--figure_img", figure_img.get("file_path", ""),
            "--output_dir", blender_output_dir,
            "--job_id", job_id,
            "--title", title,
            "--subtitle", subtitle,
            "--text_color", text_color,
            "--background_type", background_type,
            "--background_color", background_color,
        ]

        # Add accessory depth maps and images
        for i, acc_img in enumerate(accessory_imgs):
            acc_name = f"accessory_{i+1}"
            if depth_maps.get(acc_name):
                blender_cmd.extend([f"--acc{i+1}_depth", depth_maps[acc_name]])
                blender_cmd.extend([f"--acc{i+1}_img", acc_img.get("file_path", "")])

        # Add background image if applicable
        if background_type == "image" and background_image_path:
            blender_cmd.extend(["--background_image", background_image_path])

        logger.info(f"   Running Blender command...")
        logger.debug(f"   Command: {' '.join(blender_cmd)}")

        import subprocess
        try:
            blender_result = subprocess.run(
                blender_cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            if blender_result.returncode == 0:
                logger.info(f"   ✅ Blender completed successfully")
                results["steps"]["blender"] = {"success": True, "stdout": blender_result.stdout[-2000:]}

                # Collect output files
                stl_path = os.path.join(blender_output_dir, f"{job_id}.stl")
                texture_path = os.path.join(blender_output_dir, f"{job_id}_texture.png")
                blend_path = os.path.join(blender_output_dir, f"{job_id}.blend")

                if os.path.exists(stl_path):
                    results["outputs"]["stl"] = stl_path
                    results["outputs"]["stl_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}.stl"
                    logger.info(f"   ✅ STL: {stl_path}")

                if os.path.exists(texture_path):
                    results["outputs"]["texture"] = texture_path
                    results["outputs"]["texture_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}_texture.png"
                    logger.info(f"   ✅ Texture: {texture_path}")

                if os.path.exists(blend_path):
                    results["outputs"]["blend"] = blend_path
                    results["outputs"]["blend_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}.blend"
                    logger.info(f"   ✅ Blend: {blend_path}")

            else:
                error_msg = f"Blender failed with code {blender_result.returncode}"
                logger.error(f"   ❌ {error_msg}")
                logger.error(f"   STDERR: {blender_result.stderr[-2000:]}")
                results["errors"].append(error_msg)
                results["steps"]["blender"] = {
                    "success": False,
                    "error": error_msg,
                    "stderr": blender_result.stderr[-2000:]
                }

        except subprocess.TimeoutExpired:
            error_msg = "Blender timed out after 10 minutes"
            logger.error(f"   ❌ {error_msg}")
            results["errors"].append(error_msg)
            results["steps"]["blender"] = {"success": False, "error": error_msg}

        except Exception as e:
            error_msg = f"Blender exception: {e}"
            logger.error(f"   ❌ {error_msg}")
            results["errors"].append(error_msg)
            results["steps"]["blender"] = {"success": False, "error": error_msg}

        # ============================================================
        # FINAL: Determine overall success
        # ============================================================
        results["success"] = (
            results.get("outputs", {}).get("stl") is not None and
            results.get("outputs", {}).get("texture") is not None
        )

        logger.info(f"\n{'='*60}")
        logger.info(f"STARTER PACK PIPELINE COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"   Job ID: {job_id}")
        logger.info(f"   Success: {results['success']}")
        logger.info(f"   Outputs: {list(results.get('outputs', {}).keys())}")
        if results["errors"]:
            logger.warning(f"   Errors: {results['errors']}")

        return results

    except Exception as e:
        logger.error(f"❌ [STARTER_PACK] Pipeline exception: {e}")
        logger.error(traceback.format_exc())
        results["errors"].append(str(e))
        results["success"] = False
        return results


@app.post("/test/starter-pack/resume/{job_id}")
async def resume_starter_pack_pipeline(
    job_id: str,
    title: str = Form(...),
    subtitle: str = Form(default=""),
    text_color: str = Form(default="red"),
    background_type: str = Form(default="transparent"),
    background_color: str = Form(default="white"),
):
    """
    Resume a failed Starter Pack pipeline from Sculptok step.

    Use this when GPT images are already generated but Sculptok/Blender failed.
    """
    logger.info(f"🔄 [RESUME] Resuming pipeline for job {job_id}")

    # Find existing generated images
    generated_dir = os.path.join(settings.GENERATED_PATH, job_id)
    if not os.path.exists(generated_dir):
        raise HTTPException(status_code=404, detail=f"No generated images found for job {job_id}")

    import glob
    image_files = sorted(glob.glob(os.path.join(generated_dir, "*.png")))

    if not image_files:
        raise HTTPException(status_code=404, detail=f"No PNG images found in {generated_dir}")

    logger.info(f"   Found {len(image_files)} images: {[os.path.basename(f) for f in image_files]}")

    # Separate figure and accessories
    figure_img_path = None
    accessory_img_paths = []

    for img_path in image_files:
        filename = os.path.basename(img_path)
        if "base_character" in filename:
            figure_img_path = img_path
        elif "accessory" in filename:
            accessory_img_paths.append(img_path)

    if not figure_img_path:
        raise HTTPException(status_code=404, detail="No base_character image found")

    # Sort accessories by number
    accessory_img_paths = sorted(accessory_img_paths)

    logger.info(f"   Figure: {figure_img_path}")
    logger.info(f"   Accessories: {accessory_img_paths}")

    # Setup directories
    job_dir = os.path.join(settings.STORAGE_PATH, "test_starter_pack", job_id)
    os.makedirs(job_dir, exist_ok=True)

    results = {
        "job_id": job_id,
        "job_dir": job_dir,
        "success": False,
        "resumed": True,
        "steps": {},
        "outputs": {},
        "errors": []
    }

    try:
        # ============================================================
        # STEP 3: Generate depth maps with Sculptok (HIGH QUALITY)
        # ============================================================
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 3: Generate Depth Maps (Sculptok Pro 4K 16bit)")
        logger.info(f"{'='*60}")

        depth_maps = {}
        sculptok_output_dir = os.path.join(job_dir, "sculptok_output")
        os.makedirs(sculptok_output_dir, exist_ok=True)

        # Process figure
        logger.info(f"\n   Processing figure depth map...")
        figure_sculptok_dir = os.path.join(sculptok_output_dir, "base_character")
        os.makedirs(figure_sculptok_dir, exist_ok=True)

        figure_depth_result = await sculptok_client.process_image_to_depth_map(
            image_path=figure_img_path,
            output_dir=figure_sculptok_dir,
            image_name="base_character",
            skip_bg_removal=True,
            style="pro",
            version="1.5",
            draw_hd="4k",
            ext_info="16bit"
        )

        if figure_depth_result.get("success"):
            depth_maps["figure"] = figure_depth_result.get("outputs", {}).get("depth_image")
            logger.info(f"   ✅ Figure depth map: {depth_maps['figure']}")
        else:
            error_msg = f"Figure depth map failed: {figure_depth_result.get('error')}"
            logger.error(f"   ❌ {error_msg}")
            results["errors"].append(error_msg)

        # Process accessories
        for i, acc_img_path in enumerate(accessory_img_paths[:3]):  # Max 3 accessories
            acc_name = f"accessory_{i+1}"
            logger.info(f"\n   Processing {acc_name} depth map...")

            acc_sculptok_dir = os.path.join(sculptok_output_dir, acc_name)
            os.makedirs(acc_sculptok_dir, exist_ok=True)

            acc_depth_result = await sculptok_client.process_image_to_depth_map(
                image_path=acc_img_path,
                output_dir=acc_sculptok_dir,
                image_name=acc_name,
                skip_bg_removal=True,
                style="pro",
                version="1.5",
                draw_hd="4k",
                ext_info="16bit"
            )

            if acc_depth_result.get("success"):
                depth_maps[acc_name] = acc_depth_result.get("outputs", {}).get("depth_image")
                logger.info(f"   ✅ {acc_name} depth map: {depth_maps[acc_name]}")
            else:
                error_msg = f"{acc_name} depth map failed: {acc_depth_result.get('error')}"
                logger.error(f"   ❌ {error_msg}")
                results["errors"].append(error_msg)

        results["steps"]["depth_maps"] = {
            "success": len(depth_maps) > 0,
            "count": len(depth_maps),
            "paths": depth_maps
        }

        if not depth_maps.get("figure"):
            results["errors"].append("No figure depth map - cannot continue")
            return results

        # ============================================================
        # STEP 4: Run Blender Starter Pack
        # ============================================================
        logger.info(f"\n{'='*60}")
        logger.info(f"STEP 4: Run Blender Starter Pack")
        logger.info(f"{'='*60}")

        blender_output_dir = os.path.join(job_dir, "final_output")
        os.makedirs(blender_output_dir, exist_ok=True)

        blender_script = "/workspace/SimpleMe/services/blender_starter_pack.py"

        blender_cmd = [
            "blender", "--background", "--python", blender_script, "--",
            "--figure_depth", depth_maps.get("figure", ""),
            "--figure_img", figure_img_path,
            "--output_dir", blender_output_dir,
            "--job_id", job_id,
            "--title", title,
            "--subtitle", subtitle,
            "--text_color", text_color,
            "--background_type", background_type,
            "--background_color", background_color,
        ]

        # Add accessories
        for i, acc_img_path in enumerate(accessory_img_paths[:3]):
            acc_name = f"accessory_{i+1}"
            if depth_maps.get(acc_name):
                blender_cmd.extend([f"--acc{i+1}_depth", depth_maps[acc_name]])
                blender_cmd.extend([f"--acc{i+1}_img", acc_img_path])

        logger.info(f"   Running Blender...")

        import subprocess
        blender_result = subprocess.run(blender_cmd, capture_output=True, text=True, timeout=600)

        if blender_result.returncode == 0:
            logger.info(f"   ✅ Blender completed")
            results["steps"]["blender"] = {"success": True}

            stl_path = os.path.join(blender_output_dir, f"{job_id}.stl")
            texture_path = os.path.join(blender_output_dir, f"{job_id}_texture.png")
            blend_path = os.path.join(blender_output_dir, f"{job_id}.blend")

            if os.path.exists(stl_path):
                results["outputs"]["stl"] = stl_path
                results["outputs"]["stl_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}.stl"
            if os.path.exists(texture_path):
                results["outputs"]["texture"] = texture_path
                results["outputs"]["texture_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}_texture.png"
            if os.path.exists(blend_path):
                results["outputs"]["blend"] = blend_path
                results["outputs"]["blend_url"] = f"/storage/test_starter_pack/{job_id}/final_output/{job_id}.blend"
        else:
            results["errors"].append(f"Blender failed: {blender_result.stderr[-1000:]}")
            results["steps"]["blender"] = {"success": False, "stderr": blender_result.stderr[-1000:]}

        results["success"] = bool(results.get("outputs", {}).get("stl"))

        logger.info(f"\n{'='*60}")
        logger.info(f"RESUME COMPLETE - Success: {results['success']}")
        logger.info(f"{'='*60}")

        return results

    except Exception as e:
        logger.error(f"❌ Resume failed: {e}")
        logger.error(traceback.format_exc())
        results["errors"].append(str(e))
        return results


@app.get("/test/starter-pack")
async def test_starter_pack_page():
    """Serve the Starter Pack test page"""
    # Check if test page exists, otherwise return info
    test_page_path = '/workspace/SimpleMe/test_starter_pack.html'
    if os.path.exists(test_page_path):
        return FileResponse(test_page_path)
    else:
        return {
            "message": "Starter Pack Test API",
            "endpoint": "/test/starter-pack/full-pipeline",
            "method": "POST",
            "parameters": {
                "user_image": "File - User photo for figure (required)",
                "accessory_1": "String - First accessory description (required)",
                "accessory_2": "String - Second accessory description (required)",
                "accessory_3": "String - Third accessory description (required)",
                "title": "String - Main title text (required)",
                "subtitle": "String - Subtitle text (optional)",
                "text_color": "String - red/blue/green/white/black/yellow/orange/purple/pink/gold (default: red)",
                "background_type": "String - transparent/solid/image (default: transparent)",
                "background_color": "String - Color name for solid background (default: white)",
                "background_description": "String - Description for GPT-generated background",
                "background_image": "File - User image to enhance for background (optional)"
            }
        }


# ================================
# Shopify Integration Endpoints
# ================================

@app.post("/shopify/webhook/order/created")
async def shopify_order_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle Shopify order creation webhook"""
    if not shopify_handler:
        raise HTTPException(status_code=503, detail="Shopify handler not available")
    
    return await shopify_handler.handle_order_webhook(request, background_tasks)

@app.get("/shopify/orders")
async def list_shopify_orders():
    """List all Shopify orders for admin"""
    if not shopify_handler:
        raise HTTPException(status_code=503, detail="Shopify handler not available")
    
    return shopify_handler.list_all_orders()

@app.get("/shopify/order/{order_id}")
async def get_shopify_order_status(order_id: str):
    """Get status of specific Shopify order"""
    if not shopify_handler:
        raise HTTPException(status_code=503, detail="Shopify handler not available")
    
    return shopify_handler.get_order_status(order_id)

@app.get("/shopify/download/{job_id}/stl")
async def download_stl_file(job_id: str):
    """Download STL file for shop owner"""
    if not shopify_handler:
        raise HTTPException(status_code=503, detail="Shopify handler not available")
    
    return await shopify_handler.get_stl_download(job_id)

@app.get("/shopify/download/{job_id}/keychain_stl")
async def download_keychain_stl_file(job_id: str):
    """Download keychain STL file for shop owner"""
    if not shopify_handler:
        raise HTTPException(status_code=503, detail="Shopify handler not available")
    
    return await shopify_handler.get_keychain_stl_download(job_id)

@app.get("/shopify/download/{job_id}/base_character_glb")
async def download_base_character_glb_file(job_id: str):
    """Download base character GLB file for shop owner"""
    if not shopify_handler:
        raise HTTPException(status_code=503, detail="Shopify handler not available")
    
    return await shopify_handler.get_base_character_glb_download(job_id)

@app.get("/shopify/download/{job_id}/starter_pack_blend")
async def download_starter_pack_blend_file(job_id: str):
    """Download starter pack Blender file for shop owner"""
    if not shopify_handler:
        raise HTTPException(status_code=503, detail="Shopify handler not available")
    
    return await shopify_handler.get_starter_pack_blend_download(job_id)

@app.get("/shopify/download/{job_id}/keychain_blend")
async def download_keychain_blend_file(job_id: str):
    """Download keychain Blender file for shop owner"""
    if not shopify_handler:
        raise HTTPException(status_code=503, detail="Shopify handler not available")

    return await shopify_handler.get_keychain_blend_download(job_id)

@app.get("/shopify/download/{job_id}/card_printing_png")
async def download_card_printing_png_file(job_id: str):
    """Download card printing PNG file for shop owner"""
    if not shopify_handler:
        raise HTTPException(status_code=503, detail="Shopify handler not available")

    return await shopify_handler.get_card_printing_png_download(job_id)

@app.get("/shopify/download/{job_id}/keychain_printing_png")
async def download_keychain_printing_png_file(job_id: str):
    """Download keychain printing PNG file for shop owner"""
    if not shopify_handler:
        raise HTTPException(status_code=503, detail="Shopify handler not available")

    return await shopify_handler.get_keychain_printing_png_download(job_id)

@app.get("/shopify/health")
async def shopify_health_check():
    """Health check for Shopify integration"""
    return {
        "status": "healthy" if shopify_handler else "disabled",
        "shopify_handler_available": shopify_handler is not None,
        "webhook_secret_configured": bool(os.getenv("SHOPIFY_WEBHOOK_SECRET")),
        "store_domain_configured": bool(os.getenv("SHOPIFY_STORE_DOMAIN")),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/admin")
async def shopify_admin_dashboard():
    """Serve the Shopify admin dashboard"""
    return FileResponse('/workspace/SimpleMe/shopify_admin.html')

@app.get("/order")
async def customer_order_page():
    """Serve the customer order page"""
    return FileResponse('/workspace/SimpleMe/customer_order.html')

@app.post("/shopify/test-order")
async def create_test_shopify_order(
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    accessory_1: str = Form(...),
    accessory_2: str = Form(...),
    accessory_3: str = Form(...),
    user_image: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Create a test Shopify order with real file upload"""
    if not shopify_handler:
        raise HTTPException(status_code=503, detail="Shopify handler not available")
    
    try:
        # Generate IDs
        fake_order_id = str(uuid.uuid4())[:8]
        order_number = f"TEST-{fake_order_id}"
        job_id = str(uuid.uuid4())
        
        logger.info(f"📦 Creating test order {order_number} with real image: {user_image.filename}")
        
        # Validate uploaded image
        if not user_image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Save uploaded image
        content = await user_image.read()
        file_size_mb = len(content) / (1024 * 1024)
        
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File too large")
        
        # Create job directory and save image
        upload_path = os.path.join(settings.UPLOAD_PATH, job_id)
        os.makedirs(upload_path, exist_ok=True)
        
        file_extension = user_image.filename.split('.')[-1] if '.' in user_image.filename else 'jpg'
        image_path = os.path.join(upload_path, f"user_image.{file_extension}")
        
        # Save the uploaded image
        async with aiofiles.open(image_path, 'wb') as f:
            await f.write(content)
        
        logger.info(f"💾 Saved uploaded image: {image_path} ({file_size_mb:.2f} MB)")
        
        # Create Shopify order record
        order_id = str(int(fake_order_id.replace('-', ''), 16) % 1000000)
        
        shopify_record = {
            "shopify_order_id": order_id,
            "order_number": order_number,
            "customer_email": customer_email,
            "customer_name": customer_name,
            "payment_status": "paid",
            "job_status": "processing",
            "job_id": job_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # Store the order
        shopify_orders[order_id] = shopify_record 
        
        # Create job data (same as your regular submit-job)
        
        job_data = {
            "job_id": job_id,
            "status": "queued",
            "progress": {
                "upload": "completed",
                "ai_generation": "pending",
                "background_removal": "pending",
                "3d_conversion": "pending",
                "blender_processing": "pending"
            },
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "shopify_context": {
                "order_id": order_id,
                "line_item_id": "12345",
                "product_id": "67890"
            },
            "input_data": {
                "accessories": [accessory_1, accessory_2, accessory_3],
                "original_filename": user_image.filename,
                "file_size_mb": file_size_mb,
                "user_image_path": image_path
            },
            "generation_config": {
                "size": settings.IMAGE_SIZE,
                "quality": settings.IMAGE_QUALITY,
                "transparent_background": settings.TRANSPARENT_BACKGROUND,
                "model": settings.OPENAI_MODEL,
                "hunyuan3d_config": {
                    "octree_resolution": settings.HUNYUAN3D_OCTREE_RESOLUTION,
                    "inference_steps": settings.HUNYUAN3D_INFERENCE_STEPS,
                    "guidance_scale": settings.HUNYUAN3D_GUIDANCE_SCALE,
                    "face_count": settings.HUNYUAN3D_FACE_COUNT
                }
            },
            "result": None,
            "error": None
        }
        
        # Store job
        job_storage[job_id] = job_data
        
        # Start processing with the real process_job function (not the Shopify wrapper)
        background_tasks.add_task(shopify_handler.process_job_with_shopify_context, job_id)
        
        logger.info(f"🚀 Started processing job {job_id} for order {order_number}")
        
        return {
            "order_number": order_number,
            "order_id": order_id,
            "job_id": job_id,
            "status": "created",
            "message": "Test order created successfully with real image"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating test order: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Starting SimpleMe API...")
    logger.info(f"🌐 Host: {settings.API_HOST}:{settings.API_PORT}")
    logger.info(f"🔧 Blender executable: {settings.BLENDER_EXECUTABLE}")
    logger.info(f"🎯 Hunyuan3D API: {settings.HUNYUAN3D_API_URL}")

    uvicorn.run(
        app, 
        host=settings.API_HOST, 
        port=settings.API_PORT,
        log_level="info",
        access_log=True
    )
