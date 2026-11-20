"""Only sources/importer.py may import networking modules (constitution II, pipeline/CLAUDE.md)."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "thinkbible_pipeline"
ALLOWED = {SRC / "sources" / "importer.py"}
NETWORK = {"urllib", "http", "httpx", "httpx2", "requests", "socket", "aiohttp", "urllib3"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_only_importer_touches_the_network() -> None:
    offenders = {}
    for path in SRC.rglob("*.py"):
        if path in ALLOWED:
            continue
        bad = {n for n in _imports(path) if n.split(".")[0] in NETWORK}
        if bad:
            offenders[str(path.relative_to(SRC))] = sorted(bad)
    assert offenders == {}
