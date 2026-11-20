from typer.testing import CliRunner

from thinkbible_pipeline import __version__
from thinkbible_pipeline.cli import app


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output
