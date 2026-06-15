from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Print or validate the project release version.")
    parser.add_argument("--tag", action="store_true", help="Print the Git tag for the current project version.")
    parser.add_argument("--check", action="store_true", help="Validate version consistency across release files.")
    args = parser.parse_args()

    version = project_version()
    if args.check:
        validate_versions(version)
    print(f"v{version}" if args.tag else version)
    return 0


def project_version() -> str:
    return extract_assignment(ROOT / "pyproject.toml", "version")


def package_version() -> str:
    return extract_assignment(ROOT / "fusion_lite" / "__init__.py", "__version__")


def extract_assignment(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    pattern = rf'(?m)^\s*{re.escape(name)}\s*=\s*["\']([^"\']+)["\']\s*$'
    match = re.search(pattern, text)
    if not match:
        raise SystemExit(f"{path.relative_to(ROOT)} missing {name}")
    return match.group(1)


def validate_versions(version: str) -> None:
    package = package_version()
    if package != version:
        raise SystemExit(f"version mismatch: pyproject.toml={version}, fusion_lite/__init__.py={package}")

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(rf"(?m)^##\s+{re.escape(version)}\s+-\s+", changelog):
        raise SystemExit(f"CHANGELOG.md missing section for {version}")


if __name__ == "__main__":
    raise SystemExit(main())
