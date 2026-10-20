"""Import staff course workbooks into Altair: python scripts/import_professional_development.py files..."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from app.services.professional_development_service import import_courses  # noqa: E402


def main(paths):
    app = create_app()
    with app.app_context():
        for path in paths:
            result = import_courses(path.read_bytes(), path.name)
            print(
                f"{result['year']}/{result['year'] + 1}: "
                f"{result['total']} записей, {result['linked']} привязано, "
                f"{result['unlinked']} на проверке"
            )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Укажите хотя бы один файл .xlsx")
    main([Path(name) for name in sys.argv[1:]])
