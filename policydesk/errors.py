"""Domain errors. Integrations raise them, the API maps them to the error contract (ADR-005)."""


class StartupError(Exception):
    """Configuration, index or model problem found before serving traffic. The process exits."""


class PolicydeskError(Exception):
    status: int = 500
    code: str = "internal_error"
    retryable: bool = False

    def __init__(self, message: str, *, retryable: bool | None = None, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if retryable is not None:
            self.retryable = retryable
        self.retry_after = retry_after


class ModelTimeout(PolicydeskError):
    status, code, retryable = 504, "model_timeout", True


class ModelRateLimited(PolicydeskError):
    status, code, retryable = 503, "model_rate_limited", True


class Overloaded(PolicydeskError):
    status, code, retryable = 503, "overloaded", True


class ModelError(PolicydeskError):
    """Provider unreachable or failing (retryable) or rejecting the call (not retryable: a config problem)."""

    status, code = 502, "model_error"
