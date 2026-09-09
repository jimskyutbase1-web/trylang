"""Minimal local .env loader used by the EcoBin Python programs."""

from pathlib import Path
import os


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE pairs without overwriting existing environment values."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key:
            os.environ.setdefault(key, value)
