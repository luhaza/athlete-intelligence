"""Main FastAPI application setup."""

import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.api.routes import activities, athlete, training_load

# Load environment variables
load_dotenv()

# Determine if we're in production
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["200/hour", "50/minute"])

# Create FastAPI app
app = FastAPI(
    title="Athlete Intelligence API",
    description="The analytical complement to Strava - Backend API for training insights",
    version="1.0.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc"
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
# Get allowed origins from environment or use safe defaults
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Add security headers middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Include routers
app.include_router(activities.router, prefix="/activities", tags=["Activities"])
app.include_router(athlete.router, prefix="/athlete", tags=["Athlete"])
app.include_router(training_load.router, prefix="/activities", tags=["Training Load"])


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": "Athlete Intelligence API",
        "version": "1.0.0"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check with database verification."""
    from src.database.session import get_session
    from sqlalchemy import text
    import logging
    
    logger = logging.getLogger(__name__)
    db_status = "disconnected"
    
    try:
        with get_session() as session:
            # Try a simple query to verify database connection
            session.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception as e:
        # Log the actual error but don't expose it to clients
        logger.error(f"Database health check failed: {str(e)}")
        db_status = "error"
    
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "api_version": "1.0.0"
    }
