#!/usr/bin/env python3
"""Run the FastAPI development server.

Usage:
    python run_api.py
    
The API will be available at:
    - http://localhost:8000
    - API docs: http://localhost:8000/docs
    - Alternative docs: http://localhost:8000/redoc
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Auto-reload on code changes
        log_level="info"
    )
