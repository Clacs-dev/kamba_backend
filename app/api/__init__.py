"""
Agrega todos os routers da API v1 num único api_router.
"""
from fastapi import APIRouter

from app.api.routes import auth, collaborators, profiles, dossier

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(collaborators.router)
api_router.include_router(profiles.router)
api_router.include_router(dossier.router)