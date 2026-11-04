"""Aggregates every v1 router behind a single APIRouter."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import (
    ai,
    diagnostics,
    exercises,
    health,
    knowledge,
    lessons,
    progress,
    skills,
    study_plan,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(users.router)
api_router.include_router(skills.router)
api_router.include_router(diagnostics.router)
api_router.include_router(lessons.router)
api_router.include_router(study_plan.router)
api_router.include_router(exercises.router)
api_router.include_router(ai.router)
api_router.include_router(knowledge.router)
api_router.include_router(progress.router)
