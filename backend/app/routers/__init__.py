"""Router registry: adding a router is one line here."""

from app.mission.router import router as mission_intel_router
from app.routers import assessments, checkins, crew, demo, history, missions

ROUTERS = [
    crew.router,
    checkins.router,
    history.router,
    missions.router,
    assessments.router,
    demo.router,
    mission_intel_router,
]
