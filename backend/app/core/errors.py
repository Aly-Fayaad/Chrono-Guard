"""Shared HTTP error shapes.

Every ``422`` response in the API uses the same body shape as FastAPI's
request-validation handler::

    {"detail": [{"loc": ["body", "field"], "msg": "...", "type": "..."}]}

Keeping this in one module prevents the domain validators, the mission
intelligence router, and FastAPI's own validation from drifting apart.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def validation_item(
    message: str,
    *,
    loc: Sequence[str | int] = ("body",),
    error_type: str = "value_error",
) -> dict[str, Any]:
    """Build one item in the unified validation-error list."""
    return {"loc": list(loc), "msg": message, "type": error_type}


def validation_response(
    items: Sequence[dict[str, Any]],
    *,
    status_code: int = 422,
) -> JSONResponse:
    """Return a ``422`` response with the unified ``detail`` list."""
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({"detail": list(items)}),
    )


def domain_validation_response(
    message: str,
    *,
    loc: Sequence[str | int] = ("body",),
    error_type: str = "value_error",
) -> JSONResponse:
    """Convert a domain validation string into the unified response."""
    return validation_response(
        [validation_item(message, loc=loc, error_type=error_type)]
    )


def request_validation_response(exc: RequestValidationError) -> JSONResponse:
    """Normalise Pydantic request errors to the stable three-field shape."""
    items: list[dict[str, Any]] = []
    for error in exc.errors():
        items.append(
            validation_item(
                str(error.get("msg", "Invalid value")),
                loc=error.get("loc", ("body",)),
                error_type=str(error.get("type", "value_error")),
            )
        )
    return validation_response(items)
