"""Router registry: adding a router is one line here."""

from app.mission.router import router as mission_intel_router
from app.routers import (
    analysis,
    assessments,
    checkins,
    crew,
    dashboard,
    demo,
    history,
    missions,
    overview,
)

ROUTERS = [
    crew.router,
    checkins.router,
    history.router,
    missions.router,
    assessments.router,
    analysis.router,
    dashboard.router,
    overview.router,
    mission_intel_router,
    demo.router,
]
