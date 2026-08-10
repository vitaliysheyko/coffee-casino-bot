from aiogram import Router

from bot.handlers.game import setup, players, round, scoring, controls, calculator, settings_screen

router = Router(name="game")

router.include_router(setup.router)
router.include_router(players.router)
router.include_router(round.router)
router.include_router(scoring.router)
router.include_router(controls.router)
router.include_router(calculator.router)
router.include_router(settings_screen.router)
