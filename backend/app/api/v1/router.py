from fastapi import APIRouter

from app.api.v1 import auth, documents, follow_ups, health, observations, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(documents.router)
api_router.include_router(observations.router)
api_router.include_router(follow_ups.router)
