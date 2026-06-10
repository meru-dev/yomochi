from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.application.chat.ports.chat_token_budget import ChatTokenBudgetExceededError
from app.application.common.ai_errors import OpenAICallError
from app.application.common.exceptions import StorageError
from app.application.common.ports.quota_check import QuotaExceededError
from app.application.ingestion.ports.receipt_extractor import ReceiptExtractionFailedError
from app.application.insights.use_cases.request_insight import InsufficientTransactionsError
from app.application.transactions.use_cases.get_transaction import TransactionNotFoundError
from app.application.users.use_cases.change_password import (
    InvalidCurrentPasswordError,
    UserNotFoundError,
)
from app.application.users.use_cases.confirm_password_reset import InvalidPasswordResetTokenError
from app.application.users.use_cases.create_user import UserAlreadyExistsError
from app.application.users.use_cases.login import InvalidCredentialsError
from app.domain.exceptions.domain_errors import (
    CategoryIsGroupError,
    CategoryNameAlreadyExistsError,
    CategoryParentIsLeafError,
    CategoryParentNotFoundError,
    CategoryTypeMismatchError,
    FileTooLargeError,
    InvalidCurrencyError,
    InvalidCursorError,
    InvalidEmailError,
    InvalidMoneyError,
    InvalidRecurrenceScheduleError,
    InvalidTransactionTextError,
    WeakPasswordError,
)
from app.inbound.http.auth.identity import UnauthenticatedError

_logger = structlog.get_logger(__name__)


def _error_body(
    code: str,
    message: str,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            **({"details": details} if details else {}),
        }
    }


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@dataclass(frozen=True)
class _H:
    code: str
    status: int
    message: Callable[[Exception], str] = field(default=lambda e: str(e))
    log_warning: bool = False


def _static(msg: str) -> Callable[[Exception], str]:
    return lambda _: msg


_REGISTRY: dict[type[Exception], _H] = {
    UnauthenticatedError: _H("auth.required", 401, _static("Authentication required")),
    UserAlreadyExistsError: _H("user.already_exists", 409, _static("User already exists")),
    InvalidCredentialsError: _H("auth.invalid_credentials", 401, _static("Invalid credentials")),
    InvalidCurrentPasswordError: _H(
        "user.invalid_current_password", 400, _static("Current password is incorrect")
    ),
    UserNotFoundError: _H("user.not_found", 404, _static("User not found")),
    InvalidPasswordResetTokenError: _H(
        "auth.invalid_reset_token", 400, _static("Invalid or expired token")
    ),
    InsufficientTransactionsError: _H(
        "insights.insufficient_transactions",
        422,
        _static("Not enough transactions for this period"),
    ),
    TransactionNotFoundError: _H("transaction.not_found", 404, _static("Transaction not found")),
    InvalidCurrencyError: _H("transaction.invalid_currency", 400),
    InvalidMoneyError: _H("transaction.invalid_amount", 400),
    InvalidRecurrenceScheduleError: _H("recurring.invalid_schedule", 422),
    CategoryNameAlreadyExistsError: _H("category.name_conflict", 409),
    StorageError: _H("storage.error", 503, _static("A storage error occurred. Please try again.")),
    OpenAICallError: _H(
        "ai.error",
        502,
        _static("AI service temporarily unavailable. Please try again."),
        log_warning=True,
    ),
    InvalidEmailError: _H("user.invalid_email", 400),
    WeakPasswordError: _H("user.weak_password", 400, _static("Password is too weak")),
    InvalidCursorError: _H(
        "pagination.invalid_cursor", 400, _static("Invalid or expired pagination cursor")
    ),
    CategoryParentNotFoundError: _H("category.parent_not_found", 404),
    CategoryParentIsLeafError: _H("category.parent_is_leaf", 422),
    CategoryTypeMismatchError: _H("category.type_mismatch", 422),
    CategoryIsGroupError: _H("category.is_group", 422),
    ReceiptExtractionFailedError: _H("ingestion.parse_failed", 422),
    QuotaExceededError: _H(
        "quota.exceeded",
        429,
        lambda e: f"Monthly {e.resource} quota exceeded ({e.current}/{e.limit})",  # type: ignore[attr-defined]
    ),
    ChatTokenBudgetExceededError: _H(
        "chat.token_budget_exceeded",
        429,
        lambda e: f"Daily chat token budget exceeded ({e.current}/{e.limit})",  # type: ignore[attr-defined]
    ),
    FileTooLargeError: _H(
        "ingestion.file_too_large",
        413,
        lambda e: f"File exceeds {e.max_bytes // (1024 * 1024)} MB limit",  # type: ignore[attr-defined]
    ),
}


def _make_handler(cfg: _H) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        if cfg.log_warning:
            _logger.warning("openai_call_error", error=str(exc))
        return JSONResponse(
            _error_body(cfg.code, cfg.message(exc), _request_id(request)),
            status_code=cfg.status,
        )

    return handler


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type, cfg in _REGISTRY.items():
        app.add_exception_handler(exc_type, _make_handler(cfg))

    # InvalidTransactionTextError: code depends on message content
    @app.exception_handler(InvalidTransactionTextError)
    async def _tx_text_handler(request: Request, exc: InvalidTransactionTextError) -> JSONResponse:
        msg = str(exc)
        code = "transaction_text.too_long" if "exceeds" in msg else "transaction_text.empty"
        return JSONResponse(
            _error_body(code, msg, _request_id(request)),
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            _error_body("internal_error", "An unexpected error occurred", _request_id(request)),
            status_code=500,
        )
