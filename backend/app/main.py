from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import SessionLocal
from app.api.connections import router as connections_router
from app.api.grid import router as grid_router
from app.services.connections import ensure_demo_user


def create_app() -> FastAPI:
    application = FastAPI(title="Slot availability")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(connections_router, prefix="/api")
    application.include_router(grid_router, prefix="/api")

    @application.get("/health")
    @application.get("/api/health")
    def health():
        return {"ok": True}

    @application.on_event("startup")
    def _startup():
        session = SessionLocal()
        try:
            ensure_demo_user(session)
            session.commit()
        finally:
            session.close()

    return application


app = create_app()
