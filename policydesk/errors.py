"""Domain errors. Integrations raise them; the API layer maps their codes to HTTP statuses (ADR-005)."""


class StartupError(Exception):
    """Configuration, index or model problem found before serving traffic. The process exits."""


class PolicydeskError(Exception):
    code: str = "internal_error"
    retryable: bool = False

    def __init__(self, message: str, *, retryable: bool | None = None, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if retryable is not None:
            self.retryable = retryable
        self.retry_after = retry_after


class ModelTimeout(PolicydeskError):
    code, retryable = "model_timeout", True


class ModelRateLimited(PolicydeskError):
    code, retryable = "model_rate_limited", True


class Overloaded(PolicydeskError):
    code, retryable = "overloaded", True


class ModelError(PolicydeskError):
    """Provider unreachable or failing (retryable) or rejecting the call (not retryable: a config problem)."""

    code = "model_error"
