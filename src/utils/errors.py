"""Application-level exceptions for explicit API error responses."""


class AppError(Exception):
    """Base class for application errors exposed through JSON responses."""

    status_code: int = 500
    message: str = "Internal server error"

    def __init__(self, message: str | None = None):
        if message:
            self.message = message
        super().__init__(self.message)


class NotFoundError(AppError):
    """404 for missing application resources."""

    status_code = 404
    message = "Resource not found"


class UnprocessableEntityError(AppError):
    """422 for valid JSON that violates business rules."""

    status_code = 422
    message = "Unprocessable entity"


class ConflictError(AppError):
    """409 for state-transition conflicts."""

    status_code = 409
    message = "Conflict"
