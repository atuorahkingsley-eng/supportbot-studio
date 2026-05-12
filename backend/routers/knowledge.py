import os
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from backend.database import get_db, FAQEntry, Tenant
from backend.config import settings
from backend.services.auth import get_current_client

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class FAQCreate(BaseModel):
    question: str
    answer: str


class FAQResponse(BaseModel):
    id: int
    question: str
    answer: str
    source: str
    source_filename: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[FAQResponse])
def list_faqs(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    return db.query(FAQEntry).filter(
        FAQEntry.bot_id == tenant.bot_id
    ).order_by(FAQEntry.created_at.desc()).all()


@router.post("", response_model=FAQResponse)
def create_faq(
    data: FAQCreate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    faq = FAQEntry(
        bot_id=tenant.bot_id,
        question=data.question,
        answer=data.answer,
        source="manual",
        embedding_text=f"{data.question} {data.answer}",
    )
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq


@router.delete("/{faq_id}")
def delete_faq(
    faq_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    faq = db.query(FAQEntry).filter(
        FAQEntry.id == faq_id,
        FAQEntry.bot_id == tenant.bot_id,
    ).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    db.delete(faq)
    db.commit()
    return {"ok": True}


MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
_UPLOAD_CHUNK = 1024 * 1024          # 1 MB


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    from backend.services.doc_processor import process_document

    # Sanitize: strip any path components from client-supplied filename
    safe_filename = os.path.basename(file.filename or "")
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    allowed = {".pdf", ".docx", ".csv", ".txt"}
    ext = os.path.splitext(safe_filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    os.makedirs(settings.upload_dir, exist_ok=True)
    # Use a unique temp filename per upload to prevent concurrent uploads
    # with the same filename from corrupting each other's data.
    unique_name = f"{uuid.uuid4()}_{safe_filename}"
    save_path = os.path.join(settings.upload_dir, unique_name)

    # Stream-write with size cap so a 500 MB upload can't OOM the dyno
    total = 0
    with open(save_path, "wb") as f:
        while True:
            chunk = await file.read(_UPLOAD_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_SIZE:
                f.close()
                try:
                    os.remove(save_path)
                except OSError:
                    pass
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024 * 1024)} MB.",
                )
            f.write(chunk)

    try:
        pairs = await process_document(save_path, ext)

        added = 0
        for pair in pairs:
            q = pair.get("q", "").strip()
            a = pair.get("a", "").strip()
            if q and a:
                faq = FAQEntry(
                    bot_id=tenant.bot_id,
                    question=q,
                    answer=a,
                    source="uploaded_doc",
                    source_filename=safe_filename,
                    embedding_text=f"{q} {a}",
                )
                db.add(faq)
                added += 1

        db.commit()
        return {"ok": True, "extracted": len(pairs), "added": added, "filename": safe_filename, "pairs": pairs}
    finally:
        try:
            os.remove(save_path)
        except OSError:
            pass
