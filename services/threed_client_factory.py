"""
3D Client Factory - Creates the appropriate 3D generation client based on settings
"""
from typing import Union
from config.settings import settings


def create_3d_client() -> Union["Hunyuan3DClient", "Tripo3DClient"]:
    """Create the appropriate 3D generation client based on THREED_PROVIDER setting

    Returns:
        Either Hunyuan3DClient or Tripo3DClient instance
    """
    provider = getattr(settings, 'THREED_PROVIDER', 'hunyuan').lower()

    if provider == 'tripo3d':
        from services.tripo3d_client import Tripo3DClient
        print(f"Using Tripo3D for 3D generation (model: {settings.TRIPO3D_MODEL_VERSION})")
        return Tripo3DClient()
    else:
        from services.hunyuan3d_client import Hunyuan3DClient
        print(f"Using Hunyuan3D for 3D generation (API: {settings.HUNYUAN3D_API_URL})")
        return Hunyuan3DClient()
