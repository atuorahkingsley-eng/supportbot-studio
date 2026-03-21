import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.services.report_scheduler import start_scheduler, stop_scheduler
from backend.routers import (
    config_api, knowledge, chat, analytics, escalate, webhooks, reports
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="SupportBot Studio v2", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(config_api.router)
app.include_router(knowledge.router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(escalate.router)
app.include_router(webhooks.router)
app.include_router(reports.router)


@app.get("/api/health")
async def health(db=None):
    from backend.database import SessionLocal, FAQEntry
    db = SessionLocal()
    try:
        faq_count = db.query(FAQEntry).count()
    finally:
        db.close()

    return {
        "status": "ok",
        "has_api_key": bool(os.getenv("ANTHROPIC_API_KEY")),
        "faq_count": faq_count,
        "auto_reply_ready": faq_count > 0,
    }


# Serve React frontend in production
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        index = os.path.join(frontend_dist, "index.html")
        return FileResponse(index)
