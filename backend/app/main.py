from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.auth import router as auth_router
from app.api.connections import router as connections_router
from app.api.grid import router as grid_router
from app.api.meetings import router as meetings_router
from app.api.teams import router as teams_router


@asynccontextmanager
async def lifespan(_application: FastAPI):
    settings.require_secret()
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="Slot availability", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(auth_router, prefix="/api")
    application.include_router(teams_router, prefix="/api")
    application.include_router(connections_router, prefix="/api")
    application.include_router(grid_router, prefix="/api")
    application.include_router(meetings_router, prefix="/api")

    @application.get("/health")
    @application.get("/api/health")
    def health():
        return {"ok": True}

    return application


app = create_app()
