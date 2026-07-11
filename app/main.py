import logging
import sys
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.web.router import router as web_router
from app.yasno.router import router as yasno_router
from app.outages.router import router as outages_router
from app.dtek.router import router as dtek_router

from app.core.exceptions import (
    AddressNotFoundError,
    OutageGroupNotFoundError,
    InvalidInputError,
    GeocodingError,
    ClientConnectionError,
    ClientResponseError
)

from app.core.logger import request_context, setup_logging
import uuid

setup_logging()
logger = logging.getLogger(__name__)

# Initialize FastAPI App
app = FastAPI(
    title="Yasno/DTEK Outage Parser & Map API",
    description="A production-ready FastAPI wrapper for Yasno blackout status schedules with Leaflet map.",
    version="1.0.0"
)

# CORS middleware config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_request_context(request: Request, call_next):
    req_id = str(uuid.uuid7()) if hasattr(uuid, "uuid7") else str(uuid.uuid4())
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(",")[0].strip()
    else:
        ip_address = request.client.host if request.client else "127.0.0.1"
    client_name = request.headers.get("x-client-name") or request.headers.get("client-name")
    if not client_name:
        client_name = request.headers.get("user-agent", "Unknown")
    token = request_context.set({
        "request_id": req_id,
        "ip_address": ip_address,
        "client_name": client_name
    })
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        
        # Access log generation
        status_code = response.status_code
        method = request.method
        path = request.url.path
        query = f"?{request.url.query}" if request.url.query else ""
        client_port = request.client.port if request.client else 0
        log_msg = f"{ip_address}:{client_port} - \"{method} {path}{query} HTTP/1.1\" {status_code}"
        
        if status_code >= 400:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
            
        return response
    finally:
        request_context.reset(token)

# Domain Exception Handlers
@app.exception_handler(AddressNotFoundError)
async def address_not_found_handler(request: Request, exc: AddressNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

@app.exception_handler(OutageGroupNotFoundError)
async def outage_group_not_found_handler(request: Request, exc: OutageGroupNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

@app.exception_handler(InvalidInputError)
async def invalid_input_handler(request: Request, exc: InvalidInputError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})

@app.exception_handler(GeocodingError)
async def geocoding_error_handler(request: Request, exc: GeocodingError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})

@app.exception_handler(ClientConnectionError)
async def client_connection_handler(request: Request, exc: ClientConnectionError):
    return JSONResponse(status_code=504, content={"detail": str(exc)})

@app.exception_handler(ClientResponseError)
async def client_response_handler(request: Request, exc: ClientResponseError):
    status = exc.status_code if exc.status_code else 502
    return JSONResponse(status_code=status, content={"detail": str(exc)})

# Generic Exception Handler
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception occurred: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error. Please try again later."}
    )

# Include Routers
app.include_router(web_router, tags=["Web Examples / Frontends"])
app.include_router(yasno_router, tags=["Yasno Outages API v1"])
app.include_router(outages_router, tags=["Outages API v1"])
app.include_router(dtek_router, tags=["Dtek Outages API v1"])
