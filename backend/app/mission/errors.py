"""Mission-intelligence API errors and consistent error responses.

Every mission endpoint uses :class:`MissionRoute`, a thin ``APIRoute`` subclass
that converts mission-specific 404/409 errors into one stable JSON body::

    {
      "error": {
        "code": "crew_not_found",
        "message": "Crew member 'crew-x' was not found.",
        "details": null
      },
      "data_warnings": []
    }

``422`` responses are the exception: they use the API-wide
``{"detail": [{"loc", "msg", "type"}]}`` shape so request-validation and domain
errors look the same across every router. The ``data_warnings`` key is present
even on mission-specific errors so every non-422 error from this router has the
same top-level shape.

The error classes are deliberately small. They describe HTTP concerns only; no
scientific or policy decision is encoded here.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.core.errors import (
    domain_validation_response,
    request_validation_response,
)


class MissionError(Exception):
    """Base class for a mission-intelligence API error.

    Args:
        message: Human-readable explanation.
        details: Optional JSON-serialisable context for debugging.
        code: Optional machine-readable code overriding the class default.
        status_code: Optional HTTP status overriding the class default.
    """

    status_code: int = 500
    code: str = "mission_error"

    def __init__(
        self,
        message: str,
        *,
        details: Any = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class MissionCrewNotFound(MissionError):
    """The requested crew id does not exist."""

    status_code = 404
    code = "crew_not_found"

    def __init__(self, crew_id: str) -> None:
        super().__init__(
            f"Crew member '{crew_id}' was not found.",
            details={"crew_id": crew_id},
        )


class MissionValidationError(MissionError):
    """A semantic validation failure, such as a reversed or naive window."""

    status_code = 422
    code = "validation_error"


class MissionRecommendationNotFound(MissionError):
    """The recommendation id is not in the current evaluation."""

    status_code = 404
    code = "recommendation_not_found"

    def __init__(self, recommendation_id: str) -> None:
        super().__init__(
            f"Recommendation '{recommendation_id}' was not found for this crew "
            "and window.",
            details={"recommendation_id": recommendation_id},
        )


class MissionFollowUpNotFound(MissionError):
    """The follow-up id does not exist for this crew."""

    status_code = 404
    code = "follow_up_not_found"

    def __init__(self, follow_up_id: str) -> None:
        super().__init__(
            f"Follow-up '{follow_up_id}' was not found for this crew.",
            details={"follow_up_id": follow_up_id},
        )


class MissionStatusConflict(MissionError):
    """The requested follow-up transition is not allowed from its current state."""

    status_code = 409
    code = "invalid_status_transition"


class MissionApprovalRequired(MissionError):
    """Completing an approval-gated follow-up requires explicit approval."""

    status_code = 422
    code = "mission_approval_required"


def error_body(
    code: str,
    message: str,
    details: Any = None,
) -> dict[str, Any]:
    """Build the consistent mission error body."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
        "data_warnings": [],
    }


def mission_error_response(exc: MissionError) -> JSONResponse:
    """Convert a :class:`MissionError` into a JSON response."""
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(
            error_body(exc.code, exc.message, exc.details)
        ),
    )


class MissionRoute(APIRoute):
    """APIRoute that renders mission errors with the shared body shape."""

    def get_route_handler(self):
        """Wrap the normal route handler with mission error conversion."""
        original_handler = super().get_route_handler()

        async def mission_handler(request: Request):
            try:
                return await original_handler(request)
            except MissionError as exc:
                # Every 422 uses the same detail-list shape as the rest of the
                # API. Mission-specific 404/409 bodies remain unchanged.
                if exc.status_code == 422:
                    return domain_validation_response(exc.message)
                return mission_error_response(exc)
            except RequestValidationError as exc:
                return request_validation_response(exc)

        return mission_handler
