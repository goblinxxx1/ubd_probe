from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError
from app.routers import admin as admin_router
from app.routers import public as public_router

app = FastAPI(title="UBD Discounts API")


@app.exception_handler(AppError)
def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": exc.detail, "code": exc.code})


@app.exception_handler(StarletteHTTPException)
def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": str(exc.detail), "code": "http_error"})


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422,
                        content={"detail": str(exc.errors()), "code": "validation_error"})


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(public_router.router)
app.include_router(admin_router.router)
