from aiogram import Router

from bot.handlers.game import setup, players, round, scoring, controls

router = Router(name="game")

router.include_router(setup.router)
router.include_router(players.router)
router.include_router(round.router)
router.include_router(scoring.router)
router.include_router(controls.router)
