"""main.py — Remedi Chronic Care API entry point."""
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime
from fastapi import FastAPI

from utils.logger import logger
from config.settings import settings
from database.mongodb import MongoDB
from database.redis_client import redis_client
from database.minio_client import minio_client
from workflows.conversation_graph import ConversationGraph
from utils.whatsapp_client import WhatsAppClient
from core.audit import AuditMiddleware
from routes.auth import router as auth_router
from routes.webhook import router as webhook_router
from routes.admin import router as admin_router
from routes.doctor import router as doctor_router
from prometheus_fastapi_instrumentator import Instrumentator

# ── App and shared singletons ─────────────────────────────────────────────────

app = FastAPI(title="Remedi Chronic Care API")

# Expose Prometheus metrics at /metrics
Instrumentator(
    should_instrument_requests_inprogress=True
).instrument(app).expose(app)

db = MongoDB()
whatsapp = WhatsAppClient()
conversation_graph = ConversationGraph(db, whatsapp, redis_client)

# ── Middleware and routers ────────────────────────────────────────────────────

app.add_middleware(AuditMiddleware, db=db)

app.include_router(webhook_router)
app.include_router(auth_router,   prefix="/auth",   tags=["auth"])
app.include_router(admin_router,  prefix="/admin",  tags=["admin"])
app.include_router(doctor_router, prefix="/doctor", tags=["doctor"])

# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    await db.connect()
    await redis_client.connect()
    await minio_client.connect()
    app.state.db = db
    app.state.whatsapp = whatsapp
    app.state.graph = conversation_graph
    app.state.redis = redis_client
    # Background jobs handled by ARQ worker process
    # See jobs/worker.py and docker-compose.yml worker service
    logger.info("Remedi Chronic Care Bot Started")


@app.on_event("shutdown")
async def shutdown_event():
    await db.disconnect()
    await redis_client.disconnect()
    logger.info("Remedi Chronic Care Bot Stopped")

# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
async def health_check():
    redis_ok = await redis_client.health_check()
    minio_ok = await minio_client.health_check()
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "connected" if db.client else "disconnected",
        "redis": "healthy" if redis_ok else "unhealthy",
        "minio": "healthy" if minio_ok else "unhealthy",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
