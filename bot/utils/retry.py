from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def with_retry(
    func: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 0.5,
) -> T:
    last_error = None
    for attempt in range(max_retries):
        try:
            return await func()
        except TelegramRetryAfter as e:
            last_error = e
            delay = e.retry_after + 0.1
            logger.warning("Telegram rate limit, waiting %.1fs (attempt %d/%d)", delay, attempt + 1, max_retries)
            await asyncio.sleep(delay)
        except TelegramAPIError as e:
            if "Too Many Requests" in str(e):
                last_error = e
                delay = base_delay * (2 ** attempt)
                logger.warning("Rate limit error, waiting %.1fs (attempt %d/%d)", delay, attempt + 1, max_retries)
                await asyncio.sleep(delay)
            else:
                raise
    raise last_error or RuntimeError("Max retries exceeded")
