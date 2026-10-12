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


def test_missing_filename_is_usage_error(monkeypatch):
    monkeypatch.delenv("SFILE", raising=False)
    res = CliRunner().invoke(cli, ["submit"])
    assert res.exit_code == 2
    assert "SFILE" in res.output


def test_missing_file_is_clean_error(tmp_path):
    res = CliRunner().invoke(cli, ["-f", str(tmp_path / "nope.yaml"), "vis"])
    assert res.exit_code == 1
    assert res.exception is None or isinstance(res.exception, SystemExit)
    assert "Error" in res.output


def test_cycle_is_clean_error(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("dependency:\n  a: afterok:b\n  b: afterok:a\n")
    res = CliRunner().invoke(cli, ["-f", str(path), "vis"])
    assert res.exit_code == 1
    assert "dependency cycle" in res.output
    assert "Traceback" not in res.output


def test_submit_refused_when_already_submitted(tmp_path):
    path = tmp_path / "s.yaml"
    path.write_text("dependency:\n  b: afterok:a\njob_ids:\n  a: '1'\n")
    with patch("subprocess.check_output") as sp:
        res = CliRunner().invoke(cli, ["-f", str(path), "submit"])
    assert res.exit_code == 1
    assert "--force" in res.output or "force" in res.output
    sp.assert_not_called()


def test_submit_force_flag_passed(wf):
    with patch.object(Suite, "submit", return_value={}) as sub:
        res = CliRunner().invoke(cli, ["-f", wf, "submit", "--force"])
    assert res.exit_code == 0
    sub.assert_called_once_with(dry_run=False, force=True)
