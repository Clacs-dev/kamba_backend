"""
Agrega todos os routers da API v1 num único api_router.
"""
from fastapi import APIRouter

from app.api.routes import (
    auth, collaborators, profiles, dossier, evaluation, disciplinary,
    training, development, survey, notification, occupational, compensation, career,
    dashboard, report, audit, onboarding, evaluation_settings, ficha_correction, leave, admin, ai,
    shifts, chat, talent, organs, company,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(collaborators.router)
api_router.include_router(profiles.router)
api_router.include_router(dossier.router)
api_router.include_router(evaluation.router)
api_router.include_router(disciplinary.router)
api_router.include_router(training.router)
api_router.include_router(development.router)
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
api_router.include_router(ficha_correction.router)
api_router.include_router(leave.router)
api_router.include_router(admin.router)
api_router.include_router(ai.router)
api_router.include_router(shifts.router)
api_router.include_router(chat.router)
api_router.include_router(talent.router)
api_router.include_router(organs.router)
api_router.include_router(company.router)
