"""Aggregates every v1 router behind a single APIRouter."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import health

api_router = APIRouter()
api_router.include_router(health.router)
