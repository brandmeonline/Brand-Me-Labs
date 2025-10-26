# Brand.Me v7 — Stable Integrity Spine
# Graceful shutdown utilities
# brandme_core/graceful_shutdown.py

import asyncio
import signal
from typing import List, Callable, Any
from .logging import get_logger

logger = get_logger("shutdown")


class GracefulShutdown:
    """Manage graceful shutdown with resource cleanup."""
    
    def __init__(self):
        self.cleanup_functions: List[Callable[[], Any]] = []
        self._shutdown_requested = False
        
    def add_cleanup(self, func: Callable[[], Any]):
        """Add a cleanup function to execute on shutdown."""
        self.cleanup_functions.append(func)
    
    async def shutdown(self):
        """Execute all cleanup functions."""
        if self._shutdown_requested:
            return
        
        self._shutdown_requested = True
        logger.info({"event": "graceful_shutdown_started", "cleanup_count": len(self.cleanup_functions)})
        
        for i, cleanup_func in enumerate(self.cleanup_functions):
            try:
                if asyncio.iscoroutinefunction(cleanup_func):
                    await cleanup_func()
                else:
                    cleanup_func()
                logger.info({"event": "cleanup_completed", "index": i + 1, "total": len(self.cleanup_functions)})
            except Exception as e:
                logger.error({"event": "cleanup_failed", "index": i + 1, "error": str(e)})
        
        logger.info({"event": "graceful_shutdown_completed"})


def setup_graceful_shutdown(shutdown_handler: GracefulShutdown):
    """Set up signal handlers for graceful shutdown."""
    
    def signal_handler(signum, frame):
        logger.info({"event": "shutdown_signal_received", "signal": signum})
        asyncio.create_task(shutdown_handler.shutdown())
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    logger.info({"event": "graceful_shutdown_handlers_registered"})

