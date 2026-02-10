"""
Main FastAPI application for Status Window
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import (
    API_VERSION,
    API_TITLE,
    API_DESCRIPTION,
    ALLOWED_ORIGINS,
    OLLAMA_HOST,
    OLLAMA_MODEL,
)
from app.utils.logging_config import configure_logging

@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    yield


# Create FastAPI app instance
app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def check_ollama_connection() -> dict:
    """
    Check if Ollama is running and accessible

    Returns:
        dict: Connection status with details
    """
    try:
        import ollama

        # Try to list models to verify connection
        models_response = ollama.list()
        models = models_response.get("models", [])
        model_names = [m.get("name", m.get("model", "unknown")) for m in models]

        # Check if our preferred model is available
        has_preferred_model = any(OLLAMA_MODEL in name for name in model_names)

        return {
            "connected": True,
            "host": OLLAMA_HOST,
            "models_available": len(models),
            "preferred_model": OLLAMA_MODEL,
            "preferred_model_available": has_preferred_model,
            "available_models": model_names,
        }
    except ImportError:
        return {
            "connected": False,
            "error": "Ollama Python package not installed",
            "solution": "Run: pip install ollama",
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "solution": "Make sure Ollama is running (ollama serve) and accessible",
        }


@app.get("/")
async def root():
    """
    Root endpoint - API welcome message
    """
    return {
        "message": f"{API_TITLE} v{API_VERSION}",
        "tagline": "Life Sucks But You Got a Status Window Now",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "status": "operational",
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint

    Verifies:
    - API is running
    - Ollama connection status
    - Database status (TODO: add when DB is set up)
    """
    ollama_status = check_ollama_connection()

    # Determine overall health
    is_healthy = ollama_status.get("connected", False)

    response = {
        "status": "healthy" if is_healthy else "degraded",
        "api_version": API_VERSION,
        "ollama": ollama_status,
        "database": {
            "status": "not_configured",
            "message": "Database health check will be added in Week 1 Day 3-4"
        }
    }

    # Return 200 for healthy, 503 for degraded
    status_code = 200 if is_healthy else 503
    return JSONResponse(content=response, status_code=status_code)


# TODO: Add API routes
# - /api/v1/journal (Week 3)
# - /api/v1/character (Week 5)
# - /api/v1/quests (Week 4)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
