"""Fail CI when generated files or obvious credentials are tracked."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_SCAN_BYTES = 1_000_000

BLOCKED_FILENAMES = {
    ".DS_Store",
    "firebase-service-account.json",
    "google-services.json",
}
BLOCKED_SUFFIXES = {".pyc", ".pyo", ".pyd", ".pem", ".p12", ".pfx"}
ALLOWED_ENV_FILES = {".env.production.example"}

SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("GitHub token", re.compile(r"\bgh[psuor]_[0-9A-Za-z]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "database URL with credentials",
        re.compile(r"\b(?:postgres(?:ql)?|mysql|mariadb)\+?[^:]*://[^\s:/]+:[^\s@/]+@"),
    ),
)

PLACEHOLDER_MARKERS = (
    "replace",
    "example",
    "strong_password",
    "://user:password@localhost",
    "dummy",
    "test-only",
    "ci-only",
)


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    return [item.decode() for item in result.stdout.split(b"\0") if item]


def blocked_path_reason(relative_path: str) -> str | None:
    path = PurePosixPath(relative_path)
    if any(part in {".venv", "__pycache__", ".pytest_cache"} for part in path.parts):
        return "generated directory"
    if path.name in BLOCKED_FILENAMES:
        return "credential or operating-system file"
    if path.suffix.lower() in BLOCKED_SUFFIXES:
        return "generated or private-key file"
    if path.name.startswith(".env") and path.name not in ALLOWED_ENV_FILES:
        return "environment file"
    return None


def scan_text(relative_path: str) -> list[tuple[int, str]]:
    path = PROJECT_ROOT / relative_path
    try:
        if path.stat().st_size > MAX_SCAN_BYTES:
            return []
        raw = path.read_bytes()
    except OSError:
        return []
    if b"\0" in raw:
        return []
    text = raw.decode("utf-8", errors="ignore")
    findings = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        normalized = line.lower()
        if any(marker in normalized for marker in PLACEHOLDER_MARKERS):
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append((line_number, label))
    return findings


def main() -> int:
    errors = []
    for relative_path in tracked_files():
        reason = blocked_path_reason(relative_path)
        if reason:
            errors.append(f"{relative_path}: tracked {reason}")
            continue
        for line_number, label in scan_text(relative_path):
            errors.append(f"{relative_path}:{line_number}: possible {label}")

    if errors:
        print("Repository hygiene check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Repository hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
