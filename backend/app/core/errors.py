class AppError(Exception):
    def __init__(self, status_code: int, code: str, detail: str):
        self.status_code = status_code
        self.code = code
        self.detail = detail


def not_found(detail: str = "Not found") -> AppError:
    return AppError(404, "not_found", detail)


def conflict(detail: str) -> AppError:
    return AppError(409, "conflict", detail)


def forbidden(detail: str = "Forbidden") -> AppError:
    return AppError(403, "forbidden", detail)


def unauthorized(detail: str = "Not authenticated") -> AppError:
    return AppError(401, "unauthorized", detail)


def validation_error(detail: str) -> AppError:
    return AppError(422, "validation_error", detail)
