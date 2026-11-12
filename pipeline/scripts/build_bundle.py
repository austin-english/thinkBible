"""Build the pipeline Lambda bundle: ``pipeline/out/lambda.zip`` (research R19).

One zip for all five handlers, Python 3.12 on arm64. It holds the locked dependencies, both
packages, and the data the code reads, laid out like the repo so ``paths.find_repo_root`` works
with ``/var/task`` as the root:

    thinkbible_core/  thinkbible_pipeline/  <dependencies>/
    content/schema/   content/sources/manifest.json
    pipeline/config/  pipeline/prompts/  pipeline/evals/
    BUILD_INFO.json   (git HEAD, so every run record knows which code produced it)

Usage: ``uv run python pipeline/scripts/build_bundle.py`` (``make lambda-bundle``).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "pipeline" / "out"
PLATFORM = "aarch64-manylinux2014"
PYTHON = "3.12"
FIXED_TIME = (2020, 1, 1, 0, 0, 0)  # zip entries get a fixed timestamp: same input, same zip

PACKAGES = {
    "thinkbible_core": ROOT / "shared" / "src" / "thinkbible_core",
    "thinkbible_pipeline": ROOT / "pipeline" / "src" / "thinkbible_pipeline",
}
DATA = {
    "content/schema": ROOT / "content" / "schema",
    "content/sources/manifest.json": ROOT / "content" / "sources" / "manifest.json",
    "pipeline/config": ROOT / "pipeline" / "config",
    "pipeline/prompts": ROOT / "pipeline" / "prompts",
    "pipeline/evals": ROOT / "pipeline" / "evals",
}
SKIP = {"__pycache__", ".DS_Store", "fixtures"}


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout


def git_info() -> dict[str, object]:
    try:
        head = _run(["git", "rev-parse", "--short=12", "HEAD"]).strip()
        dirty = bool(_run(["git", "status", "--porcelain", "--untracked-files=no"]).strip())
    except (OSError, subprocess.CalledProcessError):
        head, dirty = "unknown", True
    return {
        "gitHead": head + ("-dirty" if dirty else ""),
        "builtAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "platform": PLATFORM,
        "python": PYTHON,
    }


def install_dependencies(staging: Path) -> None:
    """Install the locked, non-dev dependencies of thinkbible-pipeline for Lambda arm64."""
    reqs = staging.parent / "requirements.txt"
    _run(
        [
            "uv",
            "export",
            "--package",
            "thinkbible-pipeline",
            "--no-dev",
            "--no-emit-workspace",
            "--no-hashes",
            "--frozen",
            "--format",
            "requirements-txt",
            "--output-file",
            str(reqs),
        ]
    )
    _run(
        [
            "uv",
            "pip",
            "install",
            "--requirement",
            str(reqs),
            "--target",
            str(staging),
            "--python-platform",
            PLATFORM,
            "--python-version",
            PYTHON,
            "--only-binary",
            ":all:",
            "--quiet",
        ]
    )


def _copy(src: Path, dest: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*SKIP, "*.pyc"))
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def stage_files(staging: Path) -> list[str]:
    """Copy packages and data into ``staging``. Returns warnings for optional missing data."""
    warnings: list[str] = []
    for name, src in PACKAGES.items():
        _copy(src, staging / name)
    for rel, src in DATA.items():
        if not src.exists():
            warnings.append(f"{rel} is missing; the bundle will not include it")
            continue
        _copy(src, staging / rel)
    (staging / "BUILD_INFO.json").write_text(json.dumps(git_info(), indent=2) + "\n")
    return warnings


def write_zip(staging: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in staging.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in files:
            info = zipfile.ZipInfo(p.relative_to(staging).as_posix(), FIXED_TIME)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, p.read_bytes())


def build(out_dir: Path = OUT, *, with_dependencies: bool = True) -> Path:
    staging = out_dir / "lambda"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    if with_dependencies:
        install_dependencies(staging)
    for warning in stage_files(staging):
        print(f"warning: {warning}", file=sys.stderr)
    zip_path = out_dir / "lambda.zip"
    write_zip(staging, zip_path)
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--no-deps", action="store_true", help="Skip dependencies (for tests and quick checks)."
    )
    args = parser.parse_args()
    zip_path = build(args.out, with_dependencies=not args.no_deps)
    size_mb = zip_path.stat().st_size / 1_000_000
    print(f"{zip_path} ({size_mb:.1f} MB)")
    if size_mb > 50:
        sys.exit("bundle is over Lambda's 50 MB direct-upload limit")


if __name__ == "__main__":
    main()
