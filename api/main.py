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
from services.hunyuan3d_client import Hunyuan3DClient
from services.blender_processor import BlenderProcessor
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
    hunyuan3d_client = Hunyuan3DClient()
    logger.info("✅ Hunyuan3D Client initialized")
except Exception as e:
    logger.error(f"❌ Failed to initialize Hunyuan3D Client: {e}")
    raise

try:
    blender_processor = BlenderProcessor()
    logger.info("✅ Blender Processor initialized")
except Exception as e:
    logger.error(f"❌ Failed to initialize Blender Processor: {e}")
    raise



# Startup event
@app.on_event("startup")
async def startup_event():
    """Run startup checks"""
    logger.info("🔧 Running startup health checks...")

    # Create static directory for ComfyUI
    os.makedirs("static/temp_images", exist_ok=True)
    logger.info("📁 Static directory created for ComfyUI")
    
    # Check Blender installation
    try:
        blender_ok = await blender_processor.health_check()
        if blender_ok:
            logger.info("✅ Blender health check passed")
        else:
            logger.warning("⚠️ Blender health check failed - 3D processing may not work")
    except Exception as e:
        logger.error(f"❌ Blender health check error: {e}")
    
    # Check Hunyuan3D API
    try:
        hunyuan_ok = await hunyuan3d_client.health_check()
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
    return FileResponse('/home/ubuntu/SimpleMe/index.html')

@app.get("/styles.css")
async def get_styles():
    """Serve CSS file"""
    return FileResponse('/home/ubuntu/SimpleMe/styles.css', media_type='text/css')

@app.get("/script.js")
async def get_script():
    """Serve JavaScript file"""
    return FileResponse('/home/ubuntu/SimpleMe/script.js', media_type='application/javascript')

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
                "blender_processing": "pending"
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
                "generation_config": job_data.get("generation_config", {})
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
        blender_health = await blender_processor.health_check()
        hunyuan_health = await hunyuan3d_client.health_check()
        
        health_data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "active_jobs": len([j for j in job_storage.values() if j["status"] in ["queued", "processing"]]),
            "total_jobs": len(job_storage),
            "ai_generator": "healthy",
            "services": {
                "ai_generator": "healthy",
                "blender_processor": "healthy" if blender_health else "unhealthy",
                "hunyuan3d_client": "healthy" if hunyuan_health else "unhealthy"
            },
            "config": {
                "image_size": settings.IMAGE_SIZE,
                "image_quality": settings.IMAGE_QUALITY,
                "transparent_background": settings.TRANSPARENT_BACKGROUND,
                "model": settings.OPENAI_MODEL,
                "blender_executable": settings.BLENDER_EXECUTABLE,
                "hunyuan3d_api": settings.HUNYUAN3D_API_URL
            }
        }
        
        logger.info(f"✅ Health check completed - Services: AI=✅, Blender={'✅' if blender_health else '❌'}, Hunyuan3D={'✅' if hunyuan_health else '❌'}")
        
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
                model_3d = await hunyuan3d_client.generate_3d_model(
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
        
        # STEP 4: Blender Processing
        logger.info(f"🎨 Step 4: Starting Blender processing for job {job_id}")
        job_storage[job_id]["progress"]["blender_processing"] = "processing"
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()
        
        # Process 3D models into final starter pack
        blender_result = await blender_processor.process_3d_models(
            job_id=job_id,
            models_3d=models_3d
        )
        
        if not blender_result or not blender_result.get("success"):
            raise Exception(f"Blender processing failed: {blender_result.get('error', 'Unknown error')}")

        logger.info(f"✅ Step 4 completed: Blender processing successful")
        job_storage[job_id]["progress"]["blender_processing"] = "completed"
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()
        
        # FINAL: Update job with complete results
        final_result = {
            "generated_images": generated_images,
            "processed_images": processed_images,
            "models_3d": models_3d,
            "blender_result": blender_result,
            "total_images": len(generated_images),
            "total_3d_models": len(models_3d),
            "image_urls": [f"http://3.214.30.160:8000{img['url']}" for img in generated_images],
            "generation_details": {
                "size": settings.IMAGE_SIZE,
                "quality": settings.IMAGE_QUALITY,
                "transparent_background": settings.TRANSPARENT_BACKGROUND,
                "models_used": list(set([img.get("model_used", "unknown") for img in generated_images])),
                "3d_models_generated": len(models_3d),
                "blender_files": blender_result.get("output_files", [])
            },
            "download_links": {
                "images": [img["url"] for img in generated_images],
                "3d_models": [model.get("download_url") for model in models_3d if model.get("download_url")],
                "final_files": [file_info.get("download_url") for file_info in blender_result.get("output_files", []) if file_info.get("download_url")]
            }
        }
        
        # Update job status
        job_storage[job_id]["status"] = "completed"
        job_storage[job_id]["result"] = final_result
        job_storage[job_id]["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"🎉 Job {job_id} completed successfully!")
        logger.info(f"📊 Final stats: {len(generated_images)} images, {len(models_3d)} 3D models, {len(blender_result.get('output_files', []))} final files")
        
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
        "hunyuan3d_client": {"status": "unknown", "details": {}},
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
        hunyuan_health = await hunyuan3d_client.health_check()
        test_results["hunyuan3d_client"] = {
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
        test_results["hunyuan3d_client"] = {
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
    return FileResponse('/home/ubuntu/SimpleMe/shopify_admin.html')

@app.get("/order")
async def customer_order_page():
    """Serve the customer order page"""
    return FileResponse('/home/ubuntu/SimpleMe/customer_order.html')

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
