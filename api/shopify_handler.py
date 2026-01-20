# shopify_handler.py
# Handles all Shopify-related functionality for 3D generation orders

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Form, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import hmac
import hashlib
import json
import uuid
import os
from datetime import datetime
import logging
import asyncio
import aiohttp     
import aiofiles     

# Import your existing services
from config.settings import settings

logger = logging.getLogger(__name__)

# Shopify Configuration
SHOPIFY_WEBHOOK_SECRET = settings.SHOPIFY_WEBHOOK_SECRET
SHOPIFY_STORE_DOMAIN = settings.SHOPIFY_STORE_DOMAIN

# Shopify Models
class ShopifyOrder(BaseModel):
    id: int
    order_number: str
    email: str
    financial_status: str  # paid, pending, refunded, etc.
    fulfillment_status: Optional[str] = None  # fulfilled, partial, etc.
    total_price: str
    currency: str
    created_at: str
    customer: Dict[str, Any]
    line_items: List[Dict[str, Any]]

class ShopifyJobRecord(BaseModel):
    shopify_order_id: str
    order_number: str
    customer_email: str
    customer_name: str
    payment_status: str
    job_id: Optional[str] = None
    job_status: str = "pending"  # pending, processing, completed, failed
    stl_download_url: Optional[str] = None
    created_at: str
    updated_at: str

# Store for Shopify orders
shopify_orders = {}

class ShopifyHandler:
    def __init__(self, job_storage, process_job_func):
        """
        Initialize Shopify handler
        
        Args:
            job_storage: Reference to main job storage dict
            process_job_func: Reference to main process_job function
        """
        self.job_storage = job_storage
        self.process_job = process_job_func
    
    def verify_webhook(self, body: bytes, signature: str) -> bool:
        """Verify Shopify webhook signature"""
        if not signature or not SHOPIFY_WEBHOOK_SECRET:
            logger.warning("Missing webhook signature or secret")
            return False
        
        try:
            import base64
            
            # Shopify sends signature as base64 - COMPUTE IN BASE64 TOO
            computed_signature = base64.b64encode(
                hmac.new(
                    SHOPIFY_WEBHOOK_SECRET.encode('utf-8'),
                    body,
                    hashlib.sha256
                ).digest()
            ).decode('utf-8')
            
            logger.info(f"🔐 Webhook verification:")
            logger.info(f"   Received signature: {signature}")
            logger.info(f"   Computed signature: {computed_signature}")
            logger.info(f"   Secret length: {len(SHOPIFY_WEBHOOK_SECRET)}")
            
            return hmac.compare_digest(computed_signature, signature)
            
        except Exception as e:
            logger.error(f"Error verifying webhook: {e}")
            return False
    
    def extract_customization_data(self, line_item: Dict) -> Optional[Dict]:
        """Extract 3D customization data from Shopify line item"""
        properties = line_item.get('properties', [])
        
        # 🔍 DEBUG: Log everything Shopify is sending
        logger.info(f"🔍 DEBUG: Line item data:")
        logger.info(f"   Product ID: {line_item.get('product_id')}")
        logger.info(f"   Title: {line_item.get('title')}")
        logger.info(f"   Properties count: {len(properties)}")
        
        for i, prop in enumerate(properties):
            logger.info(f"   Property {i}: name='{prop.get('name')}', value='{prop.get('value')[:100]}...' (truncated)")
        
        customization = {}
        accessories = []
        
        for prop in properties:
            name = prop.get('name', '').lower().strip()
            value = prop.get('value', '').strip()
            
            logger.info(f"🔍 Processing property: '{name}' = '{value[:50]}...'")
            
            if not value:
                continue
                
            # Updated property name matching
            if 'custom image url' in name or 'image' in name:
                customization['image_url'] = value
                logger.info(f"✅ Found image (length: {len(value)})")
            elif 'accessoire' in name or 'accessory' in name:
                accessories.append(value)
                logger.info(f"✅ Found accessory: {value}")
        
        if accessories:
            customization['accessories'] = accessories
        
        logger.info(f"🎯 Final customization data:")
        logger.info(f"   Image: {'Present' if customization.get('image_url') else 'Missing'}")
        logger.info(f"   Accessories: {customization.get('accessories', [])}")
        
        # Check if this line item has customization data
        has_customization = (
            customization.get('accessories') and 
            len(customization.get('accessories', [])) >= 3
        )
        
        logger.info(f"🎯 Has customization: {has_customization}")
        
        return customization if has_customization else None
    
    async def handle_order_webhook(self, request: Request, background_tasks: BackgroundTasks):
        """Handle Shopify order creation webhook"""
        
        # Verify webhook
        body = await request.body()
        signature = request.headers.get("X-Shopify-Hmac-Sha256")
        
        if not self.verify_webhook(body, signature):
            logger.warning("Invalid Shopify webhook signature")
            raise HTTPException(status_code=401, detail="Unauthorized")
    
        try:
            # Parse JSON FIRST
            order_data = json.loads(body.decode('utf-8'))
            order_id = str(order_data['id'])
            order_number = str(order_data.get('order_number', f"#{order_id}"))
            
            logger.info(f"📦 Processing Shopify order: {order_number}")
    
            # 🔍 DEBUG: Log full order structure (AFTER parsing)
            logger.info(f"🔍 FULL ORDER DEBUG:")
            logger.info(f"   Order ID: {order_data['id']}")
            logger.info(f"   Line items count: {len(order_data.get('line_items', []))}")
            
            for i, item in enumerate(order_data.get('line_items', [])):
                logger.info(f"   Line item {i}:")
                logger.info(f"     Product: {item.get('title')}")
                logger.info(f"     Properties: {len(item.get('properties', []))}")
                for prop in item.get('properties', [])[:5]:  # First 5 properties
                    logger.info(f"       '{prop.get('name')}' = '{str(prop.get('value'))[:100]}'")
            
            # Create Shopify order record
            shopify_record = ShopifyJobRecord(
                shopify_order_id=order_id,
                order_number=order_number,
                customer_email=order_data.get('email', ''),
                customer_name=f"{order_data.get('customer', {}).get('first_name', '')} {order_data.get('customer', {}).get('last_name', '')}".strip(),
                payment_status=order_data.get('financial_status', 'pending'),
                job_status="pending",
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat()
            )
            
            # Store the order
            shopify_orders[order_id] = shopify_record.dict()
            
            # Check for customizable line items
            customizable_items = []
            for line_item in order_data.get('line_items', []):
                customization = self.extract_customization_data(line_item)
                if customization:
                    customizable_items.append({
                        'line_item_id': line_item['id'],
                        'product_id': line_item['product_id'],
                        'quantity': line_item['quantity'],
                        'customization': customization
                    })
            
            if customizable_items:
                logger.info(f"🎨 Found {len(customizable_items)} customizable items")
                
                # Process first customizable item (assuming one per order for now)
                item = customizable_items[0]
                background_tasks.add_task(
                    self.process_shopify_customization,
                    order_id,
                    item
                )
                
                # Update status
                shopify_orders[order_id]['job_status'] = 'processing'
                shopify_orders[order_id]['updated_at'] = datetime.now().isoformat()
            else:
                logger.info(f"ℹ️ No customizable items found in order {order_number}")
            
            return JSONResponse({"status": "received", "order_id": order_id})
            
        except Exception as e:
            logger.error(f"❌ Error processing Shopify webhook: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def process_shopify_customization(self, order_id: str, item: Dict):
        """Process a customization request from Shopify order"""
        try:
            customization = item['customization']
            
            # Generate job ID
            job_id = str(uuid.uuid4())
            logger.info(f"🎯 Processing customization job: {job_id} for order: {order_id}")
            
            # Download image from URL if provided
            image_path = None
            if customization.get('image_url'):
                image_path = await self.download_customer_image(job_id, customization['image_url'])
            
            if not image_path:
                raise Exception("Could not process customer image")
            
            # Create job data (similar to your existing process_job)
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
                    "line_item_id": str(item['line_item_id']),
                    "product_id": str(item['product_id'])
                },
                "input_data": {
                    "accessories": customization.get('accessories', [])[:3],  # Take first 3
                    "user_image_path": image_path
                },
                "result": None,
                "error": None
            }
            
            # Store job
            self.job_storage[job_id] = job_data
            
            # Update Shopify order record
            shopify_orders[order_id]['job_id'] = job_id
            shopify_orders[order_id]['updated_at'] = datetime.now().isoformat()
            
            # Start processing
            await self.process_job_with_shopify_context(job_id)
            
        except Exception as e:
            logger.error(f"❌ Error processing Shopify customization: {e}")
            # Update order status to failed
            if order_id in shopify_orders:
                shopify_orders[order_id]['job_status'] = 'failed'
                shopify_orders[order_id]['updated_at'] = datetime.now().isoformat()
    
    async def download_customer_image(self, job_id: str, image_url: str) -> Optional[str]:
        """Download customer image from URL"""
        try:
            import aiohttp
            import aiofiles
            
            # Create upload directory
            upload_path = os.path.join(settings.UPLOAD_PATH, job_id)
            os.makedirs(upload_path, exist_ok=True)
            
            image_path = os.path.join(upload_path, "user_image.jpg")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        async with aiofiles.open(image_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                await f.write(chunk)
                        
                        logger.info(f"📥 Downloaded image for job {job_id}")
                        return image_path
                    else:
                        logger.error(f"Failed to download image: HTTP {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None
    
    async def process_job_with_shopify_context(self, job_id: str):
        """Process job with Shopify-specific handling"""
        try:
            # Use existing process_job function
            await self.process_job(job_id)
            
            # After completion, update Shopify order
            job_data = self.job_storage.get(job_id)
            if job_data and job_data.get("status") == "completed":
                await self.handle_job_completion(job_id)
                
        except Exception as e:
            logger.error(f"❌ Shopify job processing failed: {e}")
            self.job_storage[job_id]["status"] = "failed"
            self.job_storage[job_id]["error"] = str(e)
            
            # Update Shopify order status
            shopify_context = self.job_storage[job_id].get("shopify_context", {})
            order_id = shopify_context.get("order_id")
            if order_id and order_id in shopify_orders:
                shopify_orders[order_id]['job_status'] = 'failed'
                shopify_orders[order_id]['updated_at'] = datetime.now().isoformat()
    
    async def handle_job_completion(self, job_id: str):
        """Handle job completion for Shopify orders"""
        try:
            job_data = self.job_storage.get(job_id)
            shopify_context = job_data.get("shopify_context", {})
            order_id = shopify_context.get("order_id")
            
            if not order_id or order_id not in shopify_orders:
                logger.warning(f"No Shopify order found for job {job_id}")
                return
            
            # Get files from results
            result = job_data.get("result", {})
            sticker_result = result.get("sticker_result", {})
            output_files = sticker_result.get("output_files", [])
            models_3d = result.get("models_3d", [])

            # Find available files
            starter_pack_stl = None
            starter_pack_blend = None
            keychain_stl = None
            keychain_blend = None
            base_character_glb = None
            card_printing_png = None
            keychain_printing_png = None

            # Check sticker_result output files
            for file_info in output_files:
                filename = file_info.get("filename", "")
                file_type = file_info.get("file_type", "")

                # Match by file_type (more reliable than filename)
                if file_type == "starter_pack_stl":
                    starter_pack_stl = file_info
                elif file_type == "starter_pack_blend":
                    starter_pack_blend = file_info
                elif file_type == "keychain_stl":
                    keychain_stl = file_info
                elif file_type == "keychain_blend":
                    keychain_blend = file_info
                elif file_type == "card_printing_file":
                    card_printing_png = file_info
                elif file_type == "keychain_printing_file":
                    keychain_printing_png = file_info

            # Check for base character GLB in 3D models
            for model in models_3d:
                if isinstance(model, dict) and "base_character_3d" in model.get("model_filename", ""):
                    base_character_glb = model
                    break
            
            if starter_pack_stl:
                # Create download URLs
                download_urls = {
                    'stl_download_url': f"/shopify/download/{job_id}/stl",
                    'keychain_stl_download_url': f"/shopify/download/{job_id}/keychain_stl" if keychain_stl else None,
                    'base_character_glb_download_url': f"/shopify/download/{job_id}/base_character_glb" if base_character_glb else None,
                    'starter_pack_blend_download_url': f"/shopify/download/{job_id}/starter_pack_blend" if starter_pack_blend else None,
                    'keychain_blend_download_url': f"/shopify/download/{job_id}/keychain_blend" if keychain_blend else None,
                    'card_printing_png_download_url': f"/shopify/download/{job_id}/card_printing_png" if card_printing_png else None,
                    'keychain_printing_png_download_url': f"/shopify/download/{job_id}/keychain_printing_png" if keychain_printing_png else None
                }

                # Update Shopify order record
                shopify_orders[order_id].update({
                    'job_status': 'completed',
                    'updated_at': datetime.now().isoformat(),
                    **download_urls
                })

                logger.info(f"✅ Shopify order {order_id} completed with files: starter_pack_stl={bool(starter_pack_stl)}, keychain_stl={bool(keychain_stl)}, base_character_glb={bool(base_character_glb)}, starter_pack_blend={bool(starter_pack_blend)}, keychain_blend={bool(keychain_blend)}, card_printing_png={bool(card_printing_png)}, keychain_printing_png={bool(keychain_printing_png)}")
            else:
                logger.warning(f"No starter pack STL file found for job {job_id}")
                shopify_orders[order_id]['job_status'] = 'failed'
                shopify_orders[order_id]['updated_at'] = datetime.now().isoformat()
                
        except Exception as e:
            logger.error(f"❌ Error handling job completion: {e}")
    
    def get_order_status(self, order_id: str) -> Dict:
        """Get status of a Shopify order"""
        if order_id not in shopify_orders:
            raise HTTPException(status_code=404, detail="Order not found")
        
        order_record = shopify_orders[order_id]
        
        # Get job details if available
        job_details = None
        if order_record.get('job_id'):
            job_data = self.job_storage.get(order_record['job_id'])
            if job_data:
                job_details = {
                    'status': job_data.get('status'),
                    'progress': job_data.get('progress', {}),
                    'accessories': job_data.get('input_data', {}).get('accessories', []),
                    'error': job_data.get('error')
                }
        
        return {
            **order_record,
            'job_details': job_details
        }
    
    def list_all_orders(self) -> Dict:
        """List all Shopify orders"""
        return {
            "total_orders": len(shopify_orders),
            "orders": list(shopify_orders.values())
        }
    
    async def get_stl_download(self, job_id: str):
        """Get STL file for download"""
        if job_id not in self.job_storage:
            raise HTTPException(status_code=404, detail="Job not found")

        job_data = self.job_storage[job_id]

        if job_data["status"] != "completed":
            raise HTTPException(status_code=404, detail="Job not completed")

        # Find STL file (regular starter pack)
        result = job_data.get("result", {})
        sticker_result = result.get("sticker_result", {})
        output_files = sticker_result.get("output_files", [])

        stl_file = None
        for file_info in output_files:
            if file_info.get("file_type") == "starter_pack_stl":
                stl_file = file_info
                break

        if not stl_file or not os.path.exists(stl_file.get("file_path", "")):
            raise HTTPException(status_code=404, detail="STL file not found")

        from fastapi.responses import FileResponse
        return FileResponse(
            path=stl_file["file_path"],
            filename=stl_file["filename"],
            media_type="application/octet-stream"
        )

    async def get_keychain_stl_download(self, job_id: str):
        """Get keychain STL file for download"""
        if job_id not in self.job_storage:
            raise HTTPException(status_code=404, detail="Job not found")

        job_data = self.job_storage[job_id]

        if job_data["status"] != "completed":
            raise HTTPException(status_code=404, detail="Job not completed")

        # Find keychain STL file
        result = job_data.get("result", {})
        sticker_result = result.get("sticker_result", {})
        output_files = sticker_result.get("output_files", [])

        keychain_stl_file = None
        for file_info in output_files:
            if file_info.get("file_type") == "keychain_stl":
                keychain_stl_file = file_info
                break

        if not keychain_stl_file or not os.path.exists(keychain_stl_file.get("file_path", "")):
            raise HTTPException(status_code=404, detail="Keychain STL file not found")

        from fastapi.responses import FileResponse
        return FileResponse(
            path=keychain_stl_file["file_path"],
            filename=keychain_stl_file["filename"],
            media_type="application/octet-stream"
        )

    async def get_base_character_glb_download(self, job_id: str):
        """Get base character GLB file for download"""
        if job_id not in self.job_storage:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job_data = self.job_storage[job_id]
        
        if job_data["status"] != "completed":
            raise HTTPException(status_code=404, detail="Job not completed")
        
        # Find base character GLB file
        result = job_data.get("result", {})
        models_3d = result.get("models_3d", [])
        
        base_character_glb = None
        # Check if we have the base character file in the results
        for model in models_3d:
            if isinstance(model, dict) and "base_character_3d" in model.get("model_filename", ""):
                base_character_glb = {
                    "file_path": model.get("model_path"),
                    "filename": model.get("model_filename")
                }
                break
        
        if not base_character_glb or not os.path.exists(base_character_glb.get("file_path", "")):
            raise HTTPException(status_code=404, detail="Base character GLB file not found")
        
        from fastapi.responses import FileResponse
        return FileResponse(
            path=base_character_glb["file_path"],
            filename=base_character_glb["filename"],
            media_type="application/octet-stream"
        )

    async def get_starter_pack_blend_download(self, job_id: str):
        """Get starter pack Blender file for download"""
        if job_id not in self.job_storage:
            raise HTTPException(status_code=404, detail="Job not found")

        job_data = self.job_storage[job_id]

        if job_data["status"] != "completed":
            raise HTTPException(status_code=404, detail="Job not completed")

        # Find starter pack Blender file
        result = job_data.get("result", {})
        sticker_result = result.get("sticker_result", {})
        output_files = sticker_result.get("output_files", [])

        starter_pack_blend_file = None
        for file_info in output_files:
            if file_info.get("file_type") == "starter_pack_blend":
                starter_pack_blend_file = file_info
                break

        if not starter_pack_blend_file or not os.path.exists(starter_pack_blend_file.get("file_path", "")):
            raise HTTPException(status_code=404, detail="Starter pack Blender file not found")

        from fastapi.responses import FileResponse
        return FileResponse(
            path=starter_pack_blend_file["file_path"],
            filename=starter_pack_blend_file["filename"],
            media_type="application/octet-stream"
        )

    async def get_keychain_blend_download(self, job_id: str):
        """Get keychain Blender file for download"""
        if job_id not in self.job_storage:
            raise HTTPException(status_code=404, detail="Job not found")

        job_data = self.job_storage[job_id]

        if job_data["status"] != "completed":
            raise HTTPException(status_code=404, detail="Job not completed")

        # Find keychain Blender file
        result = job_data.get("result", {})
        sticker_result = result.get("sticker_result", {})
        output_files = sticker_result.get("output_files", [])

        keychain_blend_file = None
        for file_info in output_files:
            if file_info.get("file_type") == "keychain_blend":
                keychain_blend_file = file_info
                break

        if not keychain_blend_file or not os.path.exists(keychain_blend_file.get("file_path", "")):
            raise HTTPException(status_code=404, detail="Keychain Blender file not found")

        from fastapi.responses import FileResponse
        return FileResponse(
            path=keychain_blend_file["file_path"],
            filename=keychain_blend_file["filename"],
            media_type="application/octet-stream"
        )

    async def get_card_printing_png_download(self, job_id: str):
        """Get card printing PNG file for download"""
        if job_id not in self.job_storage:
            raise HTTPException(status_code=404, detail="Job not found")

        job_data = self.job_storage[job_id]

        if job_data["status"] != "completed":
            raise HTTPException(status_code=404, detail="Job not completed")

        # Find card printing PNG file
        result = job_data.get("result", {})
        sticker_result = result.get("sticker_result", {})
        output_files = sticker_result.get("output_files", [])

        card_printing_file = None
        for file_info in output_files:
            if file_info.get("file_type") == "card_printing_file":
                card_printing_file = file_info
                break

        if not card_printing_file or not os.path.exists(card_printing_file.get("file_path", "")):
            raise HTTPException(status_code=404, detail="Card printing PNG file not found")

        from fastapi.responses import FileResponse
        return FileResponse(
            path=card_printing_file["file_path"],
            filename=card_printing_file["filename"],
            media_type="image/png"
        )

    async def get_keychain_printing_png_download(self, job_id: str):
        """Get keychain printing PNG file for download"""
        if job_id not in self.job_storage:
            raise HTTPException(status_code=404, detail="Job not found")

        job_data = self.job_storage[job_id]

        if job_data["status"] != "completed":
            raise HTTPException(status_code=404, detail="Job not completed")

        # Find keychain printing PNG file
        result = job_data.get("result", {})
        sticker_result = result.get("sticker_result", {})
        output_files = sticker_result.get("output_files", [])

        keychain_printing_file = None
        for file_info in output_files:
            if file_info.get("file_type") == "keychain_printing_file":
                keychain_printing_file = file_info
                break

        if not keychain_printing_file or not os.path.exists(keychain_printing_file.get("file_path", "")):
            raise HTTPException(status_code=404, detail="Keychain printing PNG file not found")

        from fastapi.responses import FileResponse
        return FileResponse(
            path=keychain_printing_file["file_path"],
            filename=keychain_printing_file["filename"],
            media_type="image/png"
        )