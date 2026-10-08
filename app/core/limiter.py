import asyncio
from app.core.config import settings

inference_semaphore = asyncio.BoundedSemaphore(settings.MAX_CONCURRENT_REQUESTS)
