# brandme_core/http_client.py
"""
Resilient HTTP client for inter-service communication.
Provides automatic retries, circuit breaking, timeouts, and error handling.
"""
import asyncio
from typing import Optional, Dict, Any
import httpx
from .config import config
from .logging import get_logger
from .exceptions import ServiceUnavailableError, TimeoutError as BrandMeTimeoutError

logger = get_logger("http_client")


class ResilientHttpClient:
    """
    HTTP client with built-in resilience patterns:
    - Automatic retries with exponential backoff
    - Configurable timeouts
    - Connection pooling
    - Structured error logging
    """

    def __init__(
        self,
        service_name: str,
        base_url: str,
        timeout: int = None,
        max_retries: int = None,
        retry_backoff: float = None
    ):
        self.service_name = service_name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or config.HTTP_TIMEOUT
        self.max_retries = max_retries or config.HTTP_MAX_RETRIES
        self.retry_backoff = retry_backoff or config.HTTP_RETRY_BACKOFF

        # Create httpx client with connection pooling
        limits = httpx.Limits(
            max_connections=config.HTTP_POOL_CONNECTIONS,
            max_keepalive_connections=config.HTTP_POOL_MAXSIZE
        )
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            limits=limits,
            follow_redirects=True
        )

    async def close(self):
        """Close the HTTP client and release connections."""
        await self.client.aclose()

    async def _execute_with_retry(
        self,
        method: str,
        path: str,
        request_id: Optional[str] = None,
        **kwargs
    ) -> httpx.Response:
        """
        Execute HTTP request with retry logic.

        Retries on:
        - Connection errors
        - Timeout errors
        - 5xx server errors

        Does NOT retry on:
        - 4xx client errors
        - Successful responses (2xx, 3xx)
        """
        headers = kwargs.pop("headers", {})
        if request_id:
            headers["X-Request-Id"] = request_id

        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(
                    f"{method} {path}",
                    extra={
                        "service": self.service_name,
                        "attempt": attempt + 1,
                        "max_retries": self.max_retries,
                        "request_id": request_id
                    }
                )

                response = await self.client.request(
                    method=method,
                    url=path,
                    headers=headers,
                    **kwargs
                )

                # Success - return response
                if response.status_code < 500:
                    return response

                # 5xx error - retry
                logger.warning(
                    f"Server error from {self.service_name}",
                    extra={
                        "status_code": response.status_code,
                        "attempt": attempt + 1,
                        "request_id": request_id
                    }
                )

                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_backoff * (2 ** attempt))
                    continue

                # Max retries exceeded - raise
                raise ServiceUnavailableError(
                    self.service_name,
                    {"status_code": response.status_code, "body": response.text[:500]}
                )

            except httpx.TimeoutException as e:
                last_exception = e
                logger.warning(
                    f"Timeout calling {self.service_name}",
                    extra={"attempt": attempt + 1, "request_id": request_id}
                )

                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_backoff * (2 ** attempt))
                    continue

            except httpx.ConnectError as e:
                last_exception = e
                logger.warning(
                    f"Connection error to {self.service_name}",
                    extra={"attempt": attempt + 1, "request_id": request_id}
                )

                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_backoff * (2 ** attempt))
                    continue

            except Exception as e:
                # Unexpected error - don't retry
                logger.error(
                    f"Unexpected error calling {self.service_name}",
                    extra={"error": str(e), "request_id": request_id}
                )
                raise ServiceUnavailableError(
                    self.service_name,
                    {"error": str(e)}
                )

        # If we get here, all retries exhausted
        if isinstance(last_exception, httpx.TimeoutException):
            raise BrandMeTimeoutError(
                f"HTTP {method} {path}",
                self.timeout
            )
        else:
            raise ServiceUnavailableError(
                self.service_name,
                {"error": str(last_exception)}
            )

    async def get(
        self,
        path: str,
        request_id: Optional[str] = None,
        **kwargs
    ) -> httpx.Response:
        """Execute GET request with retries."""
        return await self._execute_with_retry("GET", path, request_id, **kwargs)

    async def post(
        self,
        path: str,
        request_id: Optional[str] = None,
        **kwargs
    ) -> httpx.Response:
        """Execute POST request with retries."""
        return await self._execute_with_retry("POST", path, request_id, **kwargs)

    async def put(
        self,
        path: str,
        request_id: Optional[str] = None,
        **kwargs
    ) -> httpx.Response:
        """Execute PUT request with retries."""
        return await self._execute_with_retry("PUT", path, request_id, **kwargs)

    async def delete(
        self,
        path: str,
        request_id: Optional[str] = None,
        **kwargs
    ) -> httpx.Response:
        """Execute DELETE request with retries."""
        return await self._execute_with_retry("DELETE", path, request_id, **kwargs)


# Singleton client instances (initialized on first use)
_clients: Dict[str, ResilientHttpClient] = {}


def get_http_client(service_name: str, base_url: str) -> ResilientHttpClient:
    """
    Get or create a resilient HTTP client for a service.
    Clients are cached as singletons for connection pooling.
    """
    key = f"{service_name}:{base_url}"
    if key not in _clients:
        _clients[key] = ResilientHttpClient(service_name, base_url)
    return _clients[key]


async def close_all_clients():
    """Close all HTTP clients. Call during application shutdown."""
    for client in _clients.values():
        await client.close()
    _clients.clear()
