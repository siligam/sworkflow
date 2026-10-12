import pytest
from click.testing import CliRunner
from unittest.mock import patch

from sworkflow import cli
from sworkflow.suite import Suite


@pytest.fixture
def wf(tmp_path):
    path = tmp_path / "wf.yaml"
    path.write_text("dependency:\n  b: afterok:a\n")
    return str(path)


@pytest.mark.parametrize(
    "arg, expected",
    [("BT", "BT"), ("bt", "BT"), ("up", "BT"), ("tb", "TB"), ("right", "LR")],
)
def test_vis_rankdir(wf, arg, expected):
    with patch.object(Suite, "visualize") as vis:
        res = CliRunner().invoke(cli, ["-f", wf, "vis", "--rankdir", arg])
    assert res.exit_code == 0
    assert "not valid" not in res.output
    vis.assert_called_once_with(rankdir=expected)


def test_vis_invalid_rankdir_falls_back(wf):
    with patch.object(Suite, "visualize") as vis:
        res = CliRunner().invoke(cli, ["-f", wf, "vis", "--rankdir", "nope"])
    assert "not valid" in res.output
    vis.assert_called_once_with(rankdir="LR")


def test_status_with_unknown_state(wf):
    rows = [("a", "1", "COMPLETED"), ("b", "2", None)]
    with patch.object(Suite, "update_status", return_value=rows):
        res = CliRunner().invoke(cli, ["-f", wf, "status"])
    assert res.exit_code == 0, res.output
    assert "a  1  COMPLETED" in res.output
    assert "b  2  UNKNOWN" in res.output
