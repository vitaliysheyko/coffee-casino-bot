import logging

from aiogram import Router
from aiogram.types import ErrorEvent
from aiogram.exceptions import TelegramAPIError

router = Router()
logger = logging.getLogger(__name__)


@router.error()
async def error_handler(event: ErrorEvent):
    exception = event.exception
    if isinstance(exception, TelegramAPIError):
        logger.warning("Telegram API error: %s", exception, exc_info=True)
        return
    logger.exception("Unhandled error: %s", exception)
