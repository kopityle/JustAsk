import pymupdf  # PyMuPDF
import re
from typing import List, Dict


def clean_pdf_text(text: str) -> str:
    """Normalize typography produced by PDF extractors.

    Keeps paragraph breaks, removes soft hyphens/non-breaking spaces and glues
    words split by a hyphen at a line break. The rules are language-agnostic.
    """
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w+)-\xad(\w+)", r"\1\2", text)
    text = text.replace("\xad", "")
    text = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", text)
    text = text.replace("\xa0", " ").replace("\u202f", " ").replace("\u2009", " ")
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def split_text_clean(text: str, chunk_size: int = 1000, overlap: int = 150) -> List[str]:
    """Разбивает текст по абзацам и предложениям, гарантируя отсутствие разорванных слов."""
    if not text:
        return []
    
    # 1. Делим на смысловые блоки (абзацы)
    raw_blocks = re.split(r'\n\s*\n', text)
    blocks = []
    
    # Если абзац больше chunk_size, делим его по предложениям
    for b in raw_blocks:
        b = b.strip()
        if len(b) > chunk_size:
            sentences = re.split(r'(?<=[.!?])\s+', b)
            blocks.extend(sentences)
        elif b:
            blocks.append(b)

    chunks = []
    current_chunk = ""

    for b in blocks:
        if len(current_chunk) + len(b) + 1 <= chunk_size:
            current_chunk = f"{current_chunk}\n\n{b}".strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
                # Безопасный overlap: ищем границу слова, а не рубим по символам
                overlap_text = current_chunk[-overlap:]
                first_space = overlap_text.find(" ")
                if first_space != -1:
                    overlap_clean = overlap_text[first_space:].strip()
                else:
                    overlap_clean = ""
                current_chunk = f"{overlap_clean}\n\n{b}".strip()
            else:
                chunks.append(b[:chunk_size])
                current_chunk = b[chunk_size - overlap:]

    if current_chunk:
        chunks.append(current_chunk)

    return chunks

def load_and_chunk_file(file_path: str) -> List[Dict]:
    chunks = []
    doc_name = file_path.replace("\\", "/").split("/")[-1]

    if file_path.lower().endswith(".pdf"):
        with pymupdf.open(file_path) as doc:
            for page_idx, page in enumerate(doc, 1):
                text = clean_pdf_text(page.get_text("text"))
                if not text:
                    continue
                page_chunks = split_text_clean(text, chunk_size=1000, overlap=150)
                for c in page_chunks:
                    chunks.append({
                        "document": doc_name,
                        "page": page_idx,
                        "text": c
                    })
    elif file_path.lower().endswith(".txt"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = clean_pdf_text(f.read())
            txt_chunks = split_text_clean(text, chunk_size=1000, overlap=150)
            for c in txt_chunks:
                chunks.append({
                    "document": doc_name,
                    "page": 1,
                    "text": c
                })
    return chunks

