# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

Start the application:
```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Start ComfyUI (required for background removal):
```bash
cd ComfyUI && python main.py --listen 0.0.0.0 --port 8188
```

Install dependencies:
```bash
pip install -r requirements.txt
```

## Architecture Overview

SimpleMe is an AI-powered 3D action figure generation service that transforms user photos into custom 3D printable models. The system processes user images through multiple AI services to create complete action figure starter packs.

### Core Components

**API Layer** (`api/main.py`)
- FastAPI application serving REST endpoints
- Handles job submission, status tracking, and file serving
- Background task processing with job queuing system
- Shopify webhook integration for e-commerce orders

**AI Services** (`services/`)
- `ai_image_generator.py` - OpenAI gpt-image-1 integration for character and accessory generation
- `hunyuan3d_client.py` - 3D model generation from 2D images via Hunyuan3D API
- `background_remover.py` - ComfyUI integration for professional background removal
- `blender_processor.py` - Blender automation for 3D model processing and STL generation

**Configuration** (`config/settings.py`)
- Centralized settings using Pydantic with environment variable support
- API keys, model parameters, file paths, and service configurations

### Processing Pipeline

1. **Image Upload** - User uploads photo and specifies 3 accessories
2. **AI Generation** - Generate base character (from user photo) + 3 accessory images using OpenAI
3. **Background Removal** - ComfyUI processes all images for clean backgrounds
4. **3D Conversion** - Hunyuan3D converts 2D images to 3D models
5. **Blender Processing** - Automated 3D model cleanup, scaling, and STL export
6. **Final Output** - Complete action figure starter pack with multiple file formats

### Storage Structure

```
storage/
├── uploads/{job_id}/          # Original user images
├── generated/{job_id}/        # AI-generated images
└── processed/{job_id}/        # Final 3D models and STL files
```

### External Dependencies

- **ComfyUI Server** - Background removal (runs on separate instance at port 8188)
- **Hunyuan3D API** - 3D model generation (configured via HUNYUAN3D_API_URL)
- **Blender** - 3D processing (headless mode via BLENDER_EXECUTABLE setting)
- **OpenAI API** - Image generation using gpt-image-1 model

### Key Configuration

All configuration is in `config/settings.py`:
- OpenAI API key (required)
- ComfyUI server endpoint
- Hunyuan3D API URL
- Blender executable path
- File size limits and output formats

### Job Processing

Jobs are processed asynchronously with detailed progress tracking:
- `queued` → `processing` → `completed`/`failed`
- Each step (upload, AI generation, background removal, 3D conversion, Blender processing) tracked individually
- Full error handling and logging throughout pipeline

### Shopify Integration

The system includes Shopify webhook handlers for automated order processing:
- Order webhooks trigger job creation
- Customer email notifications
- Admin dashboard for order management
- STL file downloads for shop owners