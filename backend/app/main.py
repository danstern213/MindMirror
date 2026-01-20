from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import traceback
from fastapi.responses import JSONResponse, StreamingResponse

from .core.config import get_settings
from .api.routes import router as api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Initialize FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API for the Big Brain application",
    version="1.0.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    redoc_url="/api/v1/redoc"
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests and their processing time"""
    logger.info(f"Request path: {request.url.path}")
    logger.info(f"Client Host: {request.client.host if request.client else 'Unknown'}")
    logger.info(f"Headers: {request.headers}")
    
    try:
        response = await call_next(request)
        logger.info(f"Response status: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={"detail": str(e), "traceback": traceback.format_exc()}
        )

@app.middleware("http")
async def add_keep_alive_header(request: Request, call_next):
    """Add keep-alive headers to improve streaming performance"""
    response = await call_next(request)
    # Only update headers if not already set (StreamingResponse sets its own headers)
    if not isinstance(response, StreamingResponse):
        response.headers.update({
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        })
    return response

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://mind-mirror-delta.vercel.app",  # Explicit domain instead of wildcard
        "https://ainotecopilot.com",
        "https://www.ainotecopilot.com"  # New production domain
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",  # Allow all Vercel preview deployments
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With", "Cache-Control"],
    expose_headers=["Content-Length", "Content-Type", "Cache-Control", "Connection", "X-Accel-Buffering"],
    max_age=600,
)

# Root endpoint for testing
@app.get("/")
async def root():
    return {"message": "Welcome to Big Brain API"}

# Health check endpoint with environment verification
@app.get("/health")
async def health_check():
    """Enhanced health check that verifies critical services"""
    try:
        # Log environment setup
        logger.info("Checking environment configuration...")
        required_vars = [
            "SUPABASE_URL",
            "SUPABASE_KEY",
            "OPENAI_API_KEY",
            "SECRET_KEY"
        ]
        missing_vars = [var for var in required_vars if not getattr(settings, var, None)]
        
        if missing_vars:
            logger.error(f"Missing required environment variables: {missing_vars}")
            return {
                "status": "unhealthy",
                "missing_config": missing_vars
            }
            
        return {
            "status": "healthy",
            "config_status": "complete"
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

# Include API routes
app.include_router(api_router, prefix=settings.API_V1_STR)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 