"""
Logging middleware for request/response logging.
"""
from __future__ import annotations

import time
import logging
import json
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests and responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()
        
        # Log incoming request
        request_id = request.headers.get("x-request-id", "-")
        user_agent = request.headers.get("user-agent", "-")
        
        logger.info(
            "Incoming request | %s | %s | %s | %s",
            request.method,
            request.url.path,
            request.client.host if request.client else "-",
            user_agent[:50] if len(user_agent) > 50 else user_agent,
        )

        # Process request
        try:
            response = await call_next(request)
        except Exception as exc:
            # Log error before re-raising
            duration = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Request failed | %s | %s | %s | %dms | Error: %s",
                request.method,
                request.url.path,
                request_id,
                duration,
                str(exc),
                exc_info=True,
            )
            raise

        # Log response
        duration = (time.perf_counter() - start_time) * 1000
        log_level = logger.warning if response.status_code >= 400 else logger.info
        
        log_level(
            "Response | %s | %s | %d | %dms",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )

        # Add custom header with duration
        response.headers["X-Process-Time-Ms"] = str(round(duration, 2))
        
        return response