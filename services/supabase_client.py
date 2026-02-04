"""
Supabase Client for Order Management

Handles all database operations for orders.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from supabase import create_client, Client
from config.settings import settings

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Client for Supabase database operations"""

    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_SERVICE_KEY  # Use service key for server-side

        if not self.url or not self.key:
            logger.warning("⚠️ Supabase credentials not configured")
            self.client = None
        else:
            try:
                self.client: Client = create_client(self.url, self.key)
                logger.info(f"✅ Supabase client initialized: {self.url}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Supabase client: {e}")
                self.client = None

    def is_connected(self) -> bool:
        """Check if Supabase client is connected"""
        return self.client is not None

    # ============================================================
    # ORDER OPERATIONS
    # ============================================================

    async def create_order(self, order_data: Dict) -> Dict:
        """
        Create a new order in the database

        Args:
            order_data: {
                shopify_order_id, order_number, job_id,
                customer_name, customer_email,
                input_image_path, accessories (list),
                title, subtitle, text_color,
                background_type, background_color, background_image_path
            }

        Returns:
            Created order record or error
        """
        if not self.client:
            logger.error("❌ Supabase client not initialized")
            return {"success": False, "error": "Database not connected"}

        try:
            # Prepare order record
            record = {
                "shopify_order_id": order_data.get("shopify_order_id"),
                "order_number": order_data.get("order_number"),
                "job_id": order_data.get("job_id"),
                "customer_name": order_data.get("customer_name"),
                "customer_email": order_data.get("customer_email"),
                "status": order_data.get("status", "pending"),
                "input_image_path": order_data.get("input_image_path"),
                "accessories": order_data.get("accessories", []),
                "title": order_data.get("title", ""),
                "subtitle": order_data.get("subtitle", ""),
                "text_color": order_data.get("text_color", "red"),
                "background_type": order_data.get("background_type", "transparent"),
                "background_color": order_data.get("background_color", "white"),
                "background_image_path": order_data.get("background_image_path"),
                "is_test": order_data.get("is_test", False),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            result = self.client.table("orders").insert(record).execute()

            logger.info(f"✅ Order created: {order_data.get('job_id')}")
            return {"success": True, "data": result.data[0] if result.data else None}

        except Exception as e:
            logger.error(f"❌ Failed to create order: {e}")
            return {"success": False, "error": str(e)}

    async def update_order_status(self, job_id: str, status: str, error: str = None) -> Dict:
        """Update order status"""
        if not self.client:
            return {"success": False, "error": "Database not connected"}

        try:
            update_data = {
                "status": status,
                "updated_at": datetime.now().isoformat()
            }
            if error:
                update_data["error_message"] = error

            result = self.client.table("orders").update(update_data).eq("job_id", job_id).execute()

            logger.info(f"✅ Order {job_id} status updated to: {status}")
            return {"success": True, "data": result.data}

        except Exception as e:
            logger.error(f"❌ Failed to update order status: {e}")
            return {"success": False, "error": str(e)}

    async def update_order_outputs(self, job_id: str, outputs: Dict) -> Dict:
        """
        Update order with output file paths

        Args:
            job_id: The job ID
            outputs: {
                stl_path, texture_path, blend_path,
                stl_url, texture_url, blend_url
            }
        """
        if not self.client:
            return {"success": False, "error": "Database not connected"}

        try:
            update_data = {
                "stl_path": outputs.get("stl_path"),
                "texture_path": outputs.get("texture_path"),
                "blend_path": outputs.get("blend_path"),
                "stl_url": outputs.get("stl_url"),
                "texture_url": outputs.get("texture_url"),
                "blend_url": outputs.get("blend_url"),
                "status": "completed",
                "updated_at": datetime.now().isoformat()
            }

            result = self.client.table("orders").update(update_data).eq("job_id", job_id).execute()

            logger.info(f"✅ Order {job_id} outputs updated")
            return {"success": True, "data": result.data}

        except Exception as e:
            logger.error(f"❌ Failed to update order outputs: {e}")
            return {"success": False, "error": str(e)}

    async def get_order(self, job_id: str) -> Dict:
        """Get order by job_id"""
        if not self.client:
            return {"success": False, "error": "Database not connected"}

        try:
            result = self.client.table("orders").select("*").eq("job_id", job_id).execute()

            if result.data:
                return {"success": True, "data": result.data[0]}
            else:
                return {"success": False, "error": "Order not found"}

        except Exception as e:
            logger.error(f"❌ Failed to get order: {e}")
            return {"success": False, "error": str(e)}

    async def get_order_by_shopify_id(self, shopify_order_id: str) -> Dict:
        """Get order by Shopify order ID"""
        if not self.client:
            return {"success": False, "error": "Database not connected"}

        try:
            result = self.client.table("orders").select("*").eq("shopify_order_id", shopify_order_id).execute()

            if result.data:
                return {"success": True, "data": result.data[0]}
            else:
                return {"success": False, "error": "Order not found"}

        except Exception as e:
            logger.error(f"❌ Failed to get order: {e}")
            return {"success": False, "error": str(e)}

    async def list_orders(
        self,
        status: str = None,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "created_at",
        ascending: bool = False
    ) -> Dict:
        """
        List orders with optional filtering

        Args:
            status: Filter by status (pending, processing, completed, failed)
            limit: Max number of records
            offset: Pagination offset
            order_by: Column to sort by
            ascending: Sort direction
        """
        if not self.client:
            return {"success": False, "error": "Database not connected"}

        try:
            query = self.client.table("orders").select("*")

            if status:
                query = query.eq("status", status)

            query = query.order(order_by, desc=not ascending)
            query = query.range(offset, offset + limit - 1)

            result = query.execute()

            return {
                "success": True,
                "data": result.data,
                "count": len(result.data)
            }

        except Exception as e:
            logger.error(f"❌ Failed to list orders: {e}")
            return {"success": False, "error": str(e)}

    async def get_order_stats(self) -> Dict:
        """Get order statistics"""
        if not self.client:
            return {"success": False, "error": "Database not connected"}

        try:
            # Get counts by status
            all_orders = self.client.table("orders").select("status").execute()

            stats = {
                "total": 0,
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0
            }

            for order in all_orders.data:
                stats["total"] += 1
                status = order.get("status", "pending")
                if status in stats:
                    stats[status] += 1

            return {"success": True, "data": stats}

        except Exception as e:
            logger.error(f"❌ Failed to get order stats: {e}")
            return {"success": False, "error": str(e)}

    async def delete_order(self, job_id: str) -> Dict:
        """Delete an order"""
        if not self.client:
            return {"success": False, "error": "Database not connected"}

        try:
            result = self.client.table("orders").delete().eq("job_id", job_id).execute()

            logger.info(f"✅ Order {job_id} deleted")
            return {"success": True, "data": result.data}

        except Exception as e:
            logger.error(f"❌ Failed to delete order: {e}")
            return {"success": False, "error": str(e)}

    async def search_orders(self, query: str) -> Dict:
        """Search orders by customer name or email"""
        if not self.client:
            return {"success": False, "error": "Database not connected"}

        try:
            # Search in customer_name and customer_email
            result = self.client.table("orders").select("*").or_(
                f"customer_name.ilike.%{query}%,customer_email.ilike.%{query}%,order_number.ilike.%{query}%"
            ).execute()

            return {"success": True, "data": result.data, "count": len(result.data)}

        except Exception as e:
            logger.error(f"❌ Failed to search orders: {e}")
            return {"success": False, "error": str(e)}


# Singleton instance
_supabase_client = None


def get_supabase_client() -> SupabaseClient:
    """Get or create Supabase client singleton"""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
    return _supabase_client
