"""Generate the three academic benchmark sample PDFs in samples/input/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "engine" / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from fixtures_generator import generate_all_samples  # noqa: E402


def main() -> None:
    out_dir = ROOT / "samples" / "input"
    created = generate_all_samples(out_dir)
    for name, path in created.items():
        print(f"Generated {name}: {path}")


if __name__ == "__main__":
    main()
