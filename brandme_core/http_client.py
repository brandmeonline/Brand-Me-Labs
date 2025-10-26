# Brand.Me v7 — Stable Integrity Spine
# HTTP client utilities with retry logic and circuit breaker
# brandme_core/http_client.py

import asyncio
from typing import Optional, Callable, Any
import httpx
from .logging import get_logger

logger = get_logger("http_client")


class HTTPError(Exception):
    """Custom HTTP error with context."""
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[Any] = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


async def http_post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    json_data: dict,
    headers: dict = None,
    timeout: float = 10.0,
    max_retries: int = 3,
    retry_delay: float = 0.5
) -> httpx.Response:
    """
    Execute HTTP POST with exponential backoff retry logic.
    
    Args:
        client: httpx async client
        url: Target URL
        json_data: JSON payload
        headers: Optional headers
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        retry_delay: Base delay between retries (doubled each attempt)
    
    Returns:
        httpx.Response: Response object
    
    Raises:
        HTTPError: If request fails after all retries
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            response = await client.post(
                url,
                json=json_data,
                headers=headers or {},
                timeout=timeout,
            )
            response.raise_for_status()
            return response
            
        except httpx.TimeoutException as e:
            last_error = e
            logger.warning({
                "event": "http_post_timeout",
                "url": url,
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "error": str(e),
            })
            
        except httpx.HTTPStatusError as e:
            last_error = e
            
            # Don't retry on client errors (4xx)
            if 400 <= e.response.status_code < 500:
                logger.error({
                    "event": "http_post_client_error",
                    "url": url,
                    "status_code": e.response.status_code,
                    "error": str(e),
                })
                raise HTTPError(
                    f"Client error: {e.response.status_code}",
                    status_code=e.response.status_code,
                    response=e.response
                )
            
            # Retry on server errors (5xx)
            logger.warning({
                "event": "http_post_server_error",
                "url": url,
                "status_code": e.response.status_code,
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "error": str(e),
            })
            
        except Exception as e:
            last_error = e
            logger.warning({
                "event": "http_post_error",
                "url": url,
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "error": str(e),
            })
        
        # Retry with exponential backoff
        if attempt < max_retries - 1:
            delay = retry_delay * (2 ** attempt)
            logger.info({
                "event": "http_post_retry",
                "url": url,
                "attempt": attempt + 1,
                "delay_seconds": delay,
            })
            await asyncio.sleep(delay)
    
    # All retries exhausted
    logger.error({
        "event": "http_post_failed",
        "url": url,
        "max_retries": max_retries,
        "error": str(last_error),
    })
    raise HTTPError(
        f"Failed to execute POST to {url} after {max_retries} attempts",
        response=last_error.response if hasattr(last_error, 'response') else None
    )


async def http_get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict = None,
    headers: dict = None,
    timeout: float = 10.0,
    max_retries: int = 3,
    retry_delay: float = 0.5
) -> httpx.Response:
    """
    Execute HTTP GET with exponential backoff retry logic.
    
    Args:
        client: httpx async client
        url: Target URL
        params: Optional query parameters
        headers: Optional headers
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        retry_delay: Base delay between retries (doubled each attempt)
    
    Returns:
        httpx.Response: Response object
    
    Raises:
        HTTPError: If request fails after all retries
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            response = await client.get(
                url,
                params=params or {},
                headers=headers or {},
                timeout=timeout,
            )
            response.raise_for_status()
            return response
            
        except httpx.TimeoutException as e:
            last_error = e
            logger.warning({
                "event": "http_get_timeout",
                "url": url,
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "error": str(e),
            })
            
        except httpx.HTTPStatusError as e:
            last_error = e
            
            # Don't retry on client errors (4xx)
            if 400 <= e.response.status_code < 500:
                logger.error({
                    "event": "http_get_client_error",
                    "url": url,
                    "status_code": e.response.status_code,
                    "error": str(e),
                })
                raise HTTPError(
                    f"Client error: {e.response.status_code}",
                    status_code=e.response.status_code,
                    response=e.response
                )
            
            # Retry on server errors (5xx)
            logger.warning({
                "event": "http_get_server_error",
                "url": url,
                "status_code": e.response.status_code,
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "error": str(e),
            })
            
        except Exception as e:
            last_error = e
            logger.warning({
                "event": "http_get_error",
                "url": url,
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "error": str(e),
            })
        
        # Retry with exponential backoff
        if attempt < max_retries - 1:
            delay = retry_delay * (2 ** attempt)
            logger.info({
                "event": "http_get_retry",
                "url": url,
                "attempt": attempt + 1,
                "delay_seconds": delay,
            })
            await asyncio.sleep(delay)
    
    # All retries exhausted
    logger.error({
        "event": "http_get_failed",
        "url": url,
        "max_retries": max_retries,
        "error": str(last_error),
    })
    raise HTTPError(
        f"Failed to execute GET to {url} after {max_retries} attempts",
        response=last_error.response if hasattr(last_error, 'response') else None
    )
