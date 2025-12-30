"""Health check router for API Gateway."""

from fastapi import APIRouter
from typing import Dict, Any
import time
import psutil

router = APIRouter()

@router.get("/")
async def health_check() -> Dict[str, Any]:
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "api-gateway",
        "version": "1.0.0"
    }

@router.get("/detailed")
async def detailed_health_check() -> Dict[str, Any]:
    """Detailed health check with system metrics."""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "api-gateway",
        "version": "1.0.0",
        "system": {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "uptime": time.time() - psutil.boot_time()
        }
    }
