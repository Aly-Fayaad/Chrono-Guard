"""Router registry: adding a router is one line here."""

from app.routers import (
    assessments,
    checkins,
    crew,
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
    demo.router,
    overview.router,
]
