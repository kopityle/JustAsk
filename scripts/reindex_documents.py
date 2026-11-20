import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.documents import safe_course_id
from app.core.config import settings
from app.services.pdf_loader import load_and_chunk_file
from app.services.vector_store import vector_store


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild the vector index from files in DOCS_DIR.",
    )
    parser.add_argument("--course-id", default="default_course")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    if not args.yes:
        print("This removes existing chunks for the course. Re-run with --yes.")
        return

    course_id = safe_course_id(args.course_id)
    docs_dir = Path(settings.DOCS_DIR) / course_id
    files = sorted(
        path
        for path in docs_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".pdf", ".txt", ".docx"}
    ) if docs_dir.exists() else []

    # Удаляем чанки только переиндексируемого курса — остальные курсы не трогаем.
    removed = vector_store.delete_course(course_id)
    total_chunks = 0

    for path in files:
        chunks = load_and_chunk_file(str(path))
        if not chunks:
            print(f"[SKIP] {path.name}: no text found")
            continue
        vector_store.add_chunks(chunks, course_id=course_id)
        total_chunks += len(chunks)
        print(f"[OK] {path.name}: {len(chunks)} chunks")

    print(
        f"Removed old chunks: {removed}; "
        f"indexed new chunks: {total_chunks}; files: {len(files)}"
    )


if __name__ == "__main__":
    main()
