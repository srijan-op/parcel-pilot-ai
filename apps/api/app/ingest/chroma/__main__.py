"""Chroma ingest entrypoint: python -m app.ingest.chroma"""

from app.config import get_settings
from app.ingest.chroma_ingest import ingest_pdfs_to_chroma


def main() -> None:
    settings = get_settings()
    result = ingest_pdfs_to_chroma(settings, reset=True)
    print("Chroma ingest complete:")
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
