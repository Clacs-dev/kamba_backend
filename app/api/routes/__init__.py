"""
Agrega todos os routers da API v1 num único api_router.
"""
from fastapi import APIRouter

from app.api.routes import (
    auth, collaborators, profiles, dossier, evaluation, disciplinary,
    training, survey, notification, occupational, compensation, career,
    dashboard, report, audit, onboarding, evaluation_settings,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(collaborators.router)
api_router.include_router(profiles.router)
api_router.include_router(dossier.router)
api_router.include_router(evaluation.router)
api_router.include_router(disciplinary.router)
api_router.include_router(training.router)
api_router.include_router(survey.router)
api_router.include_router(notification.router)
api_router.include_router(occupational.router)
api_router.include_router(compensation.router)
api_router.include_router(career.router)
api_router.include_router(dashboard.router)
api_router.include_router(report.router)
api_router.include_router(audit.router)
api_router.include_router(onboarding.router)
api_router.include_router(evaluation_settings.router)
