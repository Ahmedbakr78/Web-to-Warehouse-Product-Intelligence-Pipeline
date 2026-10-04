"""Typed application errors mapped to consistent HTTP responses."""

from __future__ import annotations

from typing import Any


class PipelineError(Exception):
    """Base class for every domain error raised by the pipeline."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, "details": self.details}


class ConfigurationError(PipelineError):
    status_code = 500
    code = "configuration_error"


class DatabaseUnavailableError(PipelineError):
    status_code = 503
    code = "database_unavailable"


class ComplianceError(PipelineError):
    """Raised when robots.txt / terms of service forbid the requested access."""

    status_code = 451
    code = "compliance_violation"


class RateLimitError(PipelineError):
    status_code = 429
    code = "rate_limited"


class SourceNotFoundError(PipelineError):
    status_code = 404
    code = "source_not_found"


class ProductNotFoundError(PipelineError):
    status_code = 404
    code = "product_not_found"


class ValidationError(PipelineError):
    status_code = 422
    code = "validation_error"


class IngestionError(PipelineError):
    status_code = 502
    code = "ingestion_error"


class AuthenticationError(PipelineError):
    status_code = 401
    code = "authentication_failed"


class PermissionDeniedError(PipelineError):
    status_code = 403
    code = "permission_denied"


class ConflictError(PipelineError):
    status_code = 409
    code = "conflict"


__all__ = [
    "PipelineError",
    "ConfigurationError",
    "DatabaseUnavailableError",
    "ComplianceError",
    "RateLimitError",
    "SourceNotFoundError",
    "ProductNotFoundError",
    "ValidationError",
    "IngestionError",
    "AuthenticationError",
    "PermissionDeniedError",
    "ConflictError",
]
