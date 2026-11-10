from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base application exception with structured error envelope support."""

    def __init__(
        self,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        code: str = "BAD_REQUEST",
        message: str = "An error occurred while processing the request.",
        details: Any | None = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(self.message)


class ResourceNotFoundException(AppException):
    """Exception raised when a requested resource is not found."""

    def __init__(
        self,
        resource_name: str,
        identifier: Any | None = None,
    ):
        ident_str = f" with identifier '{identifier}'" if identifier else ""
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code="RESOURCE_NOT_FOUND",
            message=f"{resource_name}{ident_str} was not found.",
        )


class InsufficientStockException(AppException):
    """Exception raised when raw materials or single items are insufficient."""

    def __init__(
        self,
        details: list[dict[str, Any]],
        message: str = "Insufficient inventory stock to fulfill order requirements.",
    ):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code="INSUFFICIENT_STOCK",
            message=message,
            details=details,
        )


class UnauthorizedException(AppException):
    """Exception raised when authentication fails or token is invalid."""

    def __init__(
        self,
        message: str = "Authentication credentials were not provided or are invalid.",
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTHENTICATION_REQUIRED",
            message=message,
        )


class ForbiddenException(AppException):
    """Exception raised when user does not have permission for an action."""

    def __init__(
        self,
        message: str = "You do not have sufficient permissions to perform this operation.",
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="INSUFFICIENT_PERMISSIONS",
            message=message,
        )


class ConflictException(AppException):
    """Exception raised when a conflict occurs (e.g. invalid state transition or duplicate SKU)."""

    def __init__(
        self,
        code: str = "CONFLICT",
        message: str = "A resource conflict occurred.",
        details: Any | None = None,
    ):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code=code,
            message=message,
            details=details,
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Register centralized application exception handlers on the FastAPI app."""

    @app.exception_handler(AppException)
    async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "message": exc.message,
                "error": {
                    "code": exc.code,
                    "details": exc.details,
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = []
        for err in exc.errors():
            loc = " -> ".join([str(loc_part) for loc_part in err.get("loc", [])])
            errors.append(
                {
                    "field": loc,
                    "message": err.get("msg", "Invalid value"),
                    "type": err.get("type", "value_error"),
                }
            )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "data": None,
                "message": "Validation error on request payload.",
                "error": {
                    "code": "VALIDATION_ERROR",
                    "details": errors,
                },
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "data": None,
                "message": "An unexpected internal server error occurred.",
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "details": str(exc) if app.debug else None,
                },
            },
        )
