"""Run data ingest: python -m app.ingest"""

from app.config import get_settings
from app.ingest.run import run_ingest


def main() -> None:
    settings = get_settings()
    result = run_ingest(settings)
    print("Ingest complete:")
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
