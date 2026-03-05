"""FastAPI dependencies for database sessions and authentication."""

from typing import Generator
from fastapi import Depends, HTTPException, Header
import os

from src.database.session import get_session


def get_db() -> Generator:
    """Dependency for database session.
    
    Yields:
        Database session context manager
    """
    with get_session() as session:
        yield session


def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Verify API key for authentication (simple MVP auth).
    
    Args:
        x_api_key: API key from request header
        
    Returns:
        API key if valid
        
    Raises:
        HTTPException: If API key is invalid or missing
    """
    # For MVP, use simple API key from environment
    # In Phase 8, this will be replaced with proper user authentication
    expected_key = os.getenv("API_KEY")
    
    if not expected_key:
        # If no API key is configured, allow all requests (dev mode)
        return "dev-mode"
    
    if not x_api_key or x_api_key != expected_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )
    
    return x_api_key
