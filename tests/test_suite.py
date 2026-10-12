import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, call, MagicMock

from sworkflow.suite import Suite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIMPLE_DEP = {"train": "afterok:preprocess", "postprocess": "afterok:train"}
SIMPLE_JOBS = {
    "preprocess": "preprocess.sh",
    "train": "train.sh",
    "postprocess": "postprocess.sh",
}


def make_suite(**kwargs):
    return Suite(
        dependency=kwargs.get("dependency", SIMPLE_DEP),
        jobs=kwargs.get("jobs", SIMPLE_JOBS),
        job_ids=kwargs.get("job_ids", {}),
    )


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestSuiteInit:
    def test_attributes_set(self):
        s = Suite(dependency=SIMPLE_DEP, jobs=SIMPLE_JOBS, job_ids={"preprocess": "1"})
        assert s.dependency == SIMPLE_DEP
        assert s.jobs == SIMPLE_JOBS
        assert s.job_ids == {"preprocess": "1"}

    def test_defaults_are_empty_dicts(self):
        s = Suite(dependency={})
        assert s.jobs == {}
        assert s.job_ids == {}
        assert s.job_template == {}
        assert s.status == {}
        assert s.filename is None


# ---------------------------------------------------------------------------
# load_yaml / save_yaml
# ---------------------------------------------------------------------------

class TestYamlRoundTrip:
    def test_roundtrip(self, tmp_path):
        path = tmp_path / "workflow.yaml"
        s = make_suite()
        s.filename = str(path)
        s.save_yaml(str(path))

        loaded = Suite.load_yaml(str(path))
        assert loaded.dependency == SIMPLE_DEP
        assert loaded.jobs == SIMPLE_JOBS
        assert loaded.filename == str(path)

    def test_job_ids_included_by_default(self, tmp_path):
        path = tmp_path / "workflow.yaml"
        s = make_suite(job_ids={"preprocess": "42"})
        s.save_yaml(str(path))

        with open(path) as f:
            data = yaml.safe_load(f)
        assert "job_ids" in data
        assert data["job_ids"]["preprocess"] == "42"

    def test_job_ids_excluded_when_flag_false(self, tmp_path):
        path = tmp_path / "workflow.yaml"
        s = make_suite(job_ids={"preprocess": "42"})
        s.save_yaml(str(path), include_job_ids=False)

        with open(path) as f:
            data = yaml.safe_load(f)
        assert "job_ids" not in data

    def test_load_yaml_without_jobs_section(self, tmp_path):
        path = tmp_path / "minimal.yaml"
        path.write_text("dependency:\n  B: afterok:A\n")
        s = Suite.load_yaml(str(path))
        assert s.jobs == {}
        assert s.job_ids == {}


# ---------------------------------------------------------------------------
# prepare_jobs
# ---------------------------------------------------------------------------

class TestPrepareJobs:
    def test_sbatch_injected(self):
        s = Suite(
            dependency={"B": "afterok:A"},
            jobs={"A": "a.sh", "B": "b.sh"},
        )
        s.prepare_jobs()
        assert s.job_template["A"].startswith("sbatch")
        assert s.job_template["B"].startswith("sbatch")

    def test_parsable_injected(self):
        s = Suite(
            dependency={"B": "afterok:A"},
            jobs={"A": "a.sh", "B": "b.sh"},
        )
        s.prepare_jobs()
        assert "--parsable" in s.job_template["A"]
        assert "--parsable" in s.job_template["B"]

    def test_dependency_flag_injected_for_dependents(self):
        s = Suite(
            dependency={"B": "afterok:A"},
            jobs={"A": "a.sh", "B": "b.sh"},
        )
        s.prepare_jobs()
        assert "--dependency=afterok:{A}" in s.job_template["B"]

    def test_no_dependency_flag_for_roots(self):
        s = Suite(
            dependency={"B": "afterok:A"},
            jobs={"A": "a.sh", "B": "b.sh"},
        )
        s.prepare_jobs()
        assert "--dependency" not in s.job_template["A"]

    def test_default_command_used_for_missing_job(self):
        s = Suite(
            dependency={"B": "afterok:A"},
            jobs={},  # no job definitions
        )
        s.prepare_jobs()
        assert "sleep" in s.job_template["A"]
        assert "sleep" in s.job_template["B"]

    def test_sbatch_not_duplicated(self):
        s = Suite(
            dependency={"B": "afterok:A"},
            jobs={"A": "sbatch a.sh", "B": "sbatch b.sh"},
        )
        s.prepare_jobs()
        assert s.job_template["A"].count("sbatch") == 1


# ---------------------------------------------------------------------------
# submit (mocked)
# ---------------------------------------------------------------------------

class TestSubmit:
    def _fake_check_output(self, cmd, *args, **kwargs):
        """Return a different fake job ID for each successive call."""
        self._call_count = getattr(self, "_call_count", 0) + 1
        return f"{self._call_count}00".encode()

    def test_job_ids_populated(self, tmp_path):
        s = Suite(dependency=SIMPLE_DEP, jobs=SIMPLE_JOBS)
        s.filename = str(tmp_path / "out.yaml")
        counter = {"n": 0}

        def fake_sp(cmd, *a, **kw):
            counter["n"] += 1
            return f"{counter['n']}00".encode()

        with patch("subprocess.check_output", side_effect=fake_sp):
            ids = s.submit()

        assert set(ids.keys()) == {"preprocess", "train", "postprocess"}
        assert all(v.isdigit() for v in ids.values())

    def test_yaml_written_after_submit(self, tmp_path):
        outfile = tmp_path / "out.yaml"
        s = Suite(dependency=SIMPLE_DEP, jobs=SIMPLE_JOBS)
        s.filename = str(outfile)

        counter = {"n": 0}

        def fake_sp(cmd, *a, **kw):
            counter["n"] += 1
            return f"{counter['n']}00".encode()

        with patch("subprocess.check_output", side_effect=fake_sp):
            s.submit()

        assert outfile.exists()
        with open(outfile) as f:
            data = yaml.safe_load(f)
        assert "job_ids" in data

    def test_submission_order_respects_dependencies(self, tmp_path):
        s = Suite(dependency=SIMPLE_DEP, jobs=SIMPLE_JOBS)
        s.filename = str(tmp_path / "out.yaml")
        submitted_names = []
        counter = {"n": 0}

        def fake_sp(cmd, *a, **kw):
            counter["n"] += 1
            return f"{counter['n']}00".encode()

        original_prepare = s.prepare_jobs

        def tracking_prepare():
            original_prepare()
            # record the topological order from job_template
            submitted_names.extend(s.job_template.keys())

        s.prepare_jobs = tracking_prepare

        with patch("subprocess.check_output", side_effect=fake_sp):
            s.submit()

        assert submitted_names.index("preprocess") < submitted_names.index("train")
        assert submitted_names.index("train") < submitted_names.index("postprocess")

    def test_dry_run_does_not_call_sbatch(self, tmp_path):
        s = Suite(dependency=SIMPLE_DEP, jobs=SIMPLE_JOBS)
        s.filename = str(tmp_path / "out.yaml")
        with patch("subprocess.check_output") as mock_sp:
            s.submit(dry_run=True)
            mock_sp.assert_not_called()

    def test_dry_run_populates_job_ids(self, tmp_path):
        s = Suite(dependency=SIMPLE_DEP, jobs=SIMPLE_JOBS)
        s.filename = str(tmp_path / "out.yaml")
        s.submit(dry_run=True)
        assert set(s.job_ids.keys()) == {"preprocess", "train", "postprocess"}


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------

class TestGraph:
    def test_returns_digraph(self):
        import graphviz
        s = make_suite()
        with patch.object(s, "update_status"):
            g = s.graph()
        assert isinstance(g, graphviz.Digraph)

    def test_node_count(self):
        s = make_suite()
        with patch.object(s, "update_status"):
            g = s.graph()
        src = str(g)
        # One node per job
        for name in ["preprocess", "train", "postprocess"]:
            assert name in src

    def test_edges_reflect_dependencies(self):
        s = make_suite()
        with patch.object(s, "update_status"):
            g = s.graph()
        src = str(g)
        # preprocess -> train and train -> postprocess edges
        assert "preprocess" in src
        assert "train" in src


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------

class TestUpdateStatus:
    def test_empty_job_ids_returns_empty(self):
        s = Suite(dependency=SIMPLE_DEP)
        result = s.update_status()
        assert result == []

    def test_returns_empty_when_sacct_missing(self):
        s = make_suite(job_ids={"preprocess": "100"})
        with patch("subprocess.call", side_effect=FileNotFoundError):
            result = s.update_status()
        assert result == []

    def test_parses_sacct_output(self):
        s = make_suite(job_ids={"preprocess": "100", "train": "200"})

        sacct_output = "100|COMPLETED\n200|RUNNING\n"

        with patch("subprocess.call"):
            with patch("subprocess.check_output", return_value=sacct_output.encode()):
                result = s.update_status()

        statuses = {name: st for name, _, st in result}
        assert statuses["preprocess"] == "COMPLETED"
        assert statuses["train"] == "RUNNING"

    def test_status_stored_on_instance(self):
        s = make_suite(job_ids={"preprocess": "100"})
        sacct_output = "100|PENDING\n"

        with patch("subprocess.call"):
            with patch("subprocess.check_output", return_value=sacct_output.encode()):
                s.update_status()

        assert s.status["preprocess"] == "PENDING"


# ---------------------------------------------------------------------------
# regressions
# ---------------------------------------------------------------------------

def _counter_sp():
    n = {"n": 0}

    def fake(cmd, *a, **kw):
        n["n"] += 1
        return f"{n['n']}00".encode()

    return fake


class TestJobValidation:
    def test_typo_in_dependency_raises(self):
        s = Suite(
            dependency={"b": "afterok:prepocess"},
            jobs={"preprocess": "p.sh", "b": "b.sh"},
        )
        with pytest.raises(ValueError, match="prepocess"):
            s.prepare_jobs()

    def test_typo_submits_nothing(self, tmp_path):
        s = Suite(
            dependency={"b": "afterok:prepocess"},
            jobs={"preprocess": "p.sh", "b": "b.sh"},
        )
        s.filename = str(tmp_path / "out.yaml")
        with patch("subprocess.check_output") as sp:
            with pytest.raises(ValueError):
                s.submit()
        sp.assert_not_called()

    def test_independent_and_singleton_jobs_submitted(self, tmp_path):
        s = Suite(
            dependency={"b": "afterok:a", "d": "singleton"},
            jobs={"a": "a.sh", "b": "b.sh", "c": "c.sh", "d": "d.sh"},
        )
        s.filename = str(tmp_path / "out.yaml")
        with patch("subprocess.check_output", side_effect=_counter_sp()):
            ids = s.submit()
        assert set(ids) == {"a", "b", "c", "d"}

    def test_underscored_names_submit_with_dependency(self, tmp_path, capsys):
        s = Suite(
            dependency={"post_process": "afterok:pre_process"},
            jobs={"pre_process": "a.sh", "post_process": "b.sh"},
        )
        s.submit(dry_run=True)
        out = capsys.readouterr().out
        dep = f"--dependency=afterok:{s.job_ids['pre_process']}"
        assert dep in out


class TestSubmitSafety:
    def test_dry_run_does_not_write_file(self, tmp_path):
        path = tmp_path / "wf.yaml"
        path.write_text("# mine\ndependency:\n  b: afterok:a\n")
        s = Suite.load_yaml(str(path))
        s.submit(dry_run=True)
        assert path.read_text() == "# mine\ndependency:\n  b: afterok:a\n"

    def test_partial_job_ids_saved_on_failure(self, tmp_path):
        path = tmp_path / "out.yaml"
        s = Suite(dependency=SIMPLE_DEP, jobs=SIMPLE_JOBS)
        s.filename = str(path)
        ok = _counter_sp()
        calls = {"n": 0}

        def flaky(cmd, *a, **kw):
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("sbatch failed")
            return ok(cmd)

        with patch("subprocess.check_output", side_effect=flaky):
            with pytest.raises(RuntimeError):
                s.submit()
        saved = yaml.safe_load(path.read_text())["job_ids"]
        assert set(saved) == {"preprocess", "train"}

    def test_nothing_saved_when_first_job_fails(self, tmp_path):
        path = tmp_path / "out.yaml"
        s = Suite(dependency=SIMPLE_DEP, jobs=SIMPLE_JOBS)
        s.filename = str(path)
        with patch("subprocess.check_output", side_effect=RuntimeError):
            with pytest.raises(RuntimeError):
                s.submit()
        assert not path.exists()

    def test_braces_in_user_command_untouched(self, tmp_path):
        s = Suite(
            dependency={"b": "afterok:a"},
            jobs={"a": "a.sh", "b": "sbatch --wrap='echo {1..3} {} ${HOME}'"},
        )
        s.filename = str(tmp_path / "out.yaml")
        seen = []

        def fake(cmd, *a, **kw):
            seen.append(cmd)
            return b"7"

        with patch("subprocess.check_output", side_effect=fake):
            s.submit()
        assert "--wrap=echo {1..3} {} ${HOME}" in seen[1]
        assert "--dependency=afterok:7" in seen[1]
