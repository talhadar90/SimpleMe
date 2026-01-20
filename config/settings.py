from pydantic_settings import BaseSettings
from typing import Optional, Dict, List
import os

class Settings(BaseSettings):
    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Shopify Configuration
    SHOPIFY_WEBHOOK_SECRET: str = ""
    SHOPIFY_STORE_DOMAIN: str = ""

    # OpenAI Configuration
    OPENAI_API_KEY: str  # Required - must be set in .env
    OPENAI_MODEL: str = "gpt-image-1.5"  # Latest OpenAI image model
    IMAGE_SIZE: str = "1024x1536"  # Portrait orientation for action figures
    IMAGE_QUALITY: str = "high"
    TRANSPARENT_BACKGROUND: bool = True

    # Storage Configuration
    STORAGE_PATH: str = "./storage"
    UPLOAD_PATH: str = "./storage/uploads"
    GENERATED_PATH: str = "./storage/generated"
    PROCESSED_PATH: str = "./storage/processed"

    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379"

    # Job Configuration
    MAX_FILE_SIZE: int = 4 * 1024 * 1024  # 4MB for dall-e-2
    ALLOWED_IMAGE_TYPES: list = ["image/jpeg", "image/png", "image/webp"]

    # Hunyuan3D API Configuration
    HUNYUAN3D_API_URL: str = "http://localhost:8081"  # Default local API
    HUNYUAN3D_TIMEOUT: int = 300  # 5 minutes timeout
    HUNYUAN3D_MAX_RETRIES: int = 20  # Max polling attempts
    HUNYUAN3D_RETRY_DELAY: int = 15  # Seconds between status checks
    
    # Hunyuan3D Generation Parameters
    HUNYUAN3D_DEFAULT_SEED: int = 1234
    HUNYUAN3D_GENERATE_TEXTURES: bool = True
    HUNYUAN3D_OCTREE_RESOLUTION: int = 256  # 256 for accessories, 512 for characters
    HUNYUAN3D_INFERENCE_STEPS: int = 5  # 5 for accessories, 10 for characters
    HUNYUAN3D_GUIDANCE_SCALE: float = 5.0  # 5.0 for accessories, 7.0 for characters
    HUNYUAN3D_FACE_COUNT: int = 40000  # 40k for accessories, 50k for characters
    HUNYUAN3D_OUTPUT_FORMAT: str = "glb"  # glb, obj, ply

    # Background Removal Configuration
    REMBG_MODEL: str = "u2net"  # u2net, u2net_human_seg, silueta, etc.
    BACKGROUND_REMOVAL_ENABLED: bool = True
    COMFYUI_SERVER: str = "35.170.49.109:8188"  # ✅ Added type annotation
    STATIC_FILES_URL: str = "http://35.170.49.109:8000"  # ✅ Added type annotation

    # Blender Configuration
    BLENDER_EXECUTABLE: str = "blender"  # Path to blender executable
    BLENDER_TIMEOUT: int = 180  # 3 minutes timeout for blender operations
    BLENDER_HEADLESS: bool = True  # Run blender in headless mode

    # Sticker Maker Configuration (replaces old BlenderProcessor)
    STICKER_MAKER_EXECUTABLE: str = "/home/ubuntu/SimpleMe/sticker_maker/PrintMaker"
    STICKER_MAKER_WORKDIR: str = "/home/ubuntu/SimpleMe/sticker_maker"
    STICKER_MAKER_DPI: int = 300  # Output DPI for printing
    STICKER_MAKER_MIN_SIZE_MM: float = 10.0  # Minimum sticker size in square mm
    STICKER_MAKER_CUT_MARGIN_MM: float = 1.0  # Extra cut margin (bleed) in mm
    STICKER_MAKER_CUT_SMOOTHING: int = 10  # Smoothing iterations for cut paths
    STICKER_MAKER_TIMEOUT: int = 300  # 5 minutes timeout for sticker generation

    # 3D Processing Configuration (deprecated - kept for compatibility)
    STL_OUTPUT_ENABLED: bool = True
    STL_SCALE_FACTOR: float = 1.0  # Scale factor for STL output
    STL_MERGE_MODELS: bool = True  # Merge all models into single STL

    # Final Output Configuration
    FINAL_OUTPUT_FORMATS: List[str] = ["stl", "glb"]  # Output formats to generate
    CLEANUP_INTERMEDIATE_FILES: bool = False  # Keep intermediate files for debugging

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Create settings instance
settings = Settings()

# Ensure directories exist
os.makedirs(settings.UPLOAD_PATH, exist_ok=True)
os.makedirs(settings.GENERATED_PATH, exist_ok=True)
os.makedirs(settings.PROCESSED_PATH, exist_ok=True)

# Create 3D processing subdirectories
os.makedirs(os.path.join(settings.PROCESSED_PATH, "3d_models"), exist_ok=True)
os.makedirs(os.path.join(settings.PROCESSED_PATH, "stl_files"), exist_ok=True)

# Validate OpenAI API key
if not settings.OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")

print(f"✅ Settings loaded:")
print(f" - OpenAI Model: {settings.OPENAI_MODEL}")
print(f" - Image Size: {settings.IMAGE_SIZE}")
print(f" - Image Quality: {settings.IMAGE_QUALITY}")
print(f" - API Key: {'✅ Set' if settings.OPENAI_API_KEY else '❌ Missing'}")
print(f" - Hunyuan3D API: {settings.HUNYUAN3D_API_URL}")
print(f" - Background Removal: {'✅ Enabled' if settings.BACKGROUND_REMOVAL_ENABLED else '❌ Disabled'}")
print(f" - Blender Executable: {settings.BLENDER_EXECUTABLE}")
print(f" - STL Output: {'✅ Enabled' if settings.STL_OUTPUT_ENABLED else '❌ Disabled'}")
