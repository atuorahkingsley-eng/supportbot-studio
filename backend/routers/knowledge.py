import os
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


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_current_client),
):
    from backend.services.doc_processor import process_document

    allowed = {".pdf", ".docx", ".csv", ".txt"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    os.makedirs(settings.upload_dir, exist_ok=True)
    save_path = os.path.join(settings.upload_dir, file.filename)

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

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
                source_filename=file.filename,
                embedding_text=f"{q} {a}",
            )
            db.add(faq)
            added += 1

    db.commit()
    return {"ok": True, "extracted": len(pairs), "added": added, "filename": file.filename, "pairs": pairs}
