import json
import re
from typing import List
import anthropic
import structlog
from fastapi import HTTPException
from backend.config import settings

log = structlog.get_logger(__name__)

# Module-level Anthropic client — reused across document uploads.
# Matches the pattern in ai_chat.py:22. Per-call construction
# wastes a connection pool on every upload.
_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=30.0)


async def process_document(file_path: str, ext: str) -> List[dict]:
    text = ""

    if ext == ".pdf":
        text = _extract_pdf(file_path)
    elif ext == ".docx":
        text = _extract_docx(file_path)
    elif ext == ".csv":
        return _extract_csv(file_path)
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

    if not text.strip():
        return []

    return await _generate_qa_pairs(text)


def _extract_pdf(path: str) -> str:
    try:
        import PyPDF2
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="PDF processing not available — contact administrator",
        )
    try:
        text_parts = []
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
        return "\n".join(text_parts)
    except Exception as e:
        log.warning("pdf_extraction_failed", path=path, error=str(e)[:200])
        return ""


def _extract_docx(path: str) -> str:
    try:
        from docx import Document
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="DOCX processing not available — contact administrator",
        )
    try:
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        log.warning("docx_extraction_failed", path=path, error=str(e)[:200])
        return ""


def _extract_csv(path: str) -> List[dict]:
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="CSV processing not available — contact administrator",
        )
    try:
        df = pd.read_csv(path, quotechar='"', escapechar='\\', on_bad_lines='skip')
        df.columns = [c.lower().strip() for c in df.columns]
        if "question" in df.columns and "answer" in df.columns:
            pairs = []
            for _, row in df.iterrows():
                q = str(row.get("question", "")).strip()
                a = str(row.get("answer", "")).strip()
                if q and a:
                    pairs.append({"q": q, "a": a})
            return pairs
        return []
    except Exception as e:
        print(f"CSV ERROR: {e}")
        return []


async def _generate_qa_pairs(text: str) -> List[dict]:
    if not settings.anthropic_api_key:
        return []

    # Split into chunks of ~2000 chars
    chunks = _chunk_text(text, max_chars=2000)
    all_pairs = []

    client = _client

    for chunk in chunks[:5]:  # Limit to 5 chunks per upload
        prompt = (
            "Given this text from a business document, generate FAQ-style question and answer pairs.\n"
            "Each pair should be a common customer question and a helpful answer.\n"
            "Return JSON array: [{\"q\": \"...\", \"a\": \"...\"}]\n"
            "Only generate questions a customer would actually ask.\n"
            "Return ONLY the JSON array, no other text.\n\n"
            f"Text: {chunk}"
        )

        try:
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text.strip()
            # Extract JSON array
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                pairs = json.loads(match.group())
                all_pairs.extend(pairs)
        except Exception:
            continue

    return all_pairs


def _chunk_text(text: str, max_chars: int = 2000) -> List[str]:
    paragraphs = re.split(r'\n{2,}', text)
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > max_chars:
            if current:
                chunks.append(current.strip())
            current = para
        else:
            current += "\n\n" + para
    if current.strip():
        chunks.append(current.strip())
    return chunks
