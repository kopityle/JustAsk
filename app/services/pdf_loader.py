import pymupdf  # PyMuPDF
import re
from typing import List, Dict


def _docx_has_page_break(paragraph) -> bool:
    """Явный разрыв страницы или разрыв, проставленный Word при pagination."""
    xml = paragraph._p.xml
    return 'w:type="page"' in xml or "lastRenderedPageBreak" in xml


def _docx_is_heading(paragraph) -> bool:
    name = (paragraph.style.name or "").lower()
    return bool(re.match(r"^(heading|заголовок)\s*[12]$", name))


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


def _hard_split_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Режет слишком длинный фрагмент, стараясь попасть в границу слова."""
    pieces = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            space = text.rfind(" ", start + 1, end)
            if space > start:
                end = space
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return pieces


def split_text_clean(text: str, chunk_size: int = 1000, overlap: int = 150) -> List[str]:
    """Разбивает текст по абзацам и предложениям, гарантируя отсутствие разорванных слов."""
    if not text:
        return []
    
    # 1. Делим на смысловые блоки (абзацы)
    raw_blocks = re.split(r'\n\s*\n', text)
    blocks = []
    
    # Если абзац больше chunk_size, делим его по предложениям, затем принудительно по словам
    for b in raw_blocks:
        b = b.strip()
        if not b:
            continue
        if len(b) > chunk_size:
            for sentence in re.split(r'(?<=[.!?])\s+', b):
                sentence = sentence.strip()
                if not sentence:
                    continue
                if len(sentence) > chunk_size:
                    blocks.extend(_hard_split_text(sentence, chunk_size, overlap))
                else:
                    blocks.append(sentence)
        else:
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
        with open(file_path, "rb") as f:
            raw = f.read()
        text = ""
        for encoding in ("utf-8-sig", "cp1251"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if not text:
            text = raw.decode("utf-8", errors="ignore")
        text = clean_pdf_text(text)
        txt_chunks = split_text_clean(text, chunk_size=1000, overlap=150)
        for c in txt_chunks:
            chunks.append({
                "document": doc_name,
                "page": 1,
                "text": c
            })
    elif file_path.lower().endswith(".docx"):
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(file_path)
        page_no = 1
        block_parts: List[str] = []

        def flush_block() -> None:
            nonlocal page_no, block_parts
            text = clean_pdf_text("\n".join(block_parts))
            for chunk in split_text_clean(text, chunk_size=1000, overlap=150):
                chunks.append({"document": doc_name, "page": page_no, "text": chunk})

        def next_page() -> None:
            nonlocal page_no, block_parts
            if not block_parts:
                return
            flush_block()
            block_parts = []
            page_no += 1

        for item in doc.iter_inner_content():
            if isinstance(item, Paragraph):
                if _docx_has_page_break(item) or _docx_is_heading(item):
                    next_page()
                text = (item.text or "").strip()
            elif isinstance(item, Table):
                rows = [
                    " | ".join(cell.text.strip() for cell in row.cells)
                    for row in item.rows
                ]
                text = "\n".join(row for row in rows if row.strip(" |"))
            else:
                continue

            if not text:
                continue
            if len("\n".join(block_parts)) + len(text) > 3000:
                next_page()
            block_parts.append(text)

        flush_block()
    return chunks

