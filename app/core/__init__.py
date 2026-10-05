"""Core infrastructure: configuration, logging, database engines and shared errors.

Authentication helpers live in `app.api.security` because they depend on the
request/response layer, not on `core`.
"""

__all__ = ["config", "db", "errors", "features", "logging"]
