from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.audio import router as audio_router
from app.api.calls import router as calls_router
from app.api.alerts import router as alerts_router
from app.api import analysis
from app.core.config import settings
from app.db.database import init_db




@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description="VoiceGuard AI backend API",
    version="0.1.0",
    lifespan=lifespan,
)


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(calls_router)
app.include_router(audio_router)
app.include_router(analysis.router)
app.include_router(alerts_router)

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }