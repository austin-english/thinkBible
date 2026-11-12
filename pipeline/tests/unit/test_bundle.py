"""The Lambda bundle is laid out like the repo, so find_repo_root() works from /var/task."""

import importlib.util
import json
import zipfile
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_bundle.py"


def load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_bundle", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_layout_without_dependencies(tmp_path: Path) -> None:
    zip_path = load_builder().build(tmp_path, with_dependencies=False)
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        info = json.loads(zf.read("BUILD_INFO.json"))
    assert "thinkbible_pipeline/cloud/handlers.py" in names
    assert "thinkbible_core/models/section.py" in names
    assert "content/schema/section.schema.json" in names
    assert "pipeline/config/settings.toml" in names
    assert "pipeline/prompts/_shared/context-v1.md" in names
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)
    assert info["platform"] == "aarch64-manylinux2014" and info["gitHead"]


def test_bundle_is_reproducible(tmp_path: Path) -> None:
    builder = load_builder()
    a = builder.build(tmp_path / "a", with_dependencies=False)
    b = builder.build(tmp_path / "b", with_dependencies=False)
    with zipfile.ZipFile(a) as za, zipfile.ZipFile(b) as zb:
        names = [n for n in za.namelist() if n != "BUILD_INFO.json"]
        assert names == [n for n in zb.namelist() if n != "BUILD_INFO.json"]
        assert all(za.read(n) == zb.read(n) for n in names)
