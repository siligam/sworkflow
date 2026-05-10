import graphlib
import pytest
from unittest.mock import patch, MagicMock
from io import StringIO

from sworkflow.utils import (
    as_dict,
    as_tuple,
    as_placeholder,
    task_ordering,
    check_output,
    in_jupyter,
    parse_array_status,
    Default,
)


# ---------------------------------------------------------------------------
# as_dict
# ---------------------------------------------------------------------------

class TestAsDict:
    def test_linear_chain(self):
        dep = {"B": "afterok:A"}
        assert as_dict(dep) == {"B": ["A"]}

    def test_multiple_predecessors(self):
        dep = {"D": "afterok:B:C"}
        result = as_dict(dep)
        assert set(result["D"]) == {"B", "C"}

    def test_keyword_stripped(self):
        dep = {"B": "afterok:A"}
        result = as_dict(dep)
        assert "afterok" not in result["B"]

    def test_array_suffix_stripped(self):
        dep = {"B": "afterok:A_10"}
        assert as_dict(dep) == {"B": ["A"]}

    def test_offset_suffix_stripped(self):
        dep = {"B": "afterok:A+1"}
        assert as_dict(dep) == {"B": ["A"]}

    def test_diamond_dag(self):
        dep = {"B": "afterok:A", "C": "afterok:A", "D": "afterok:B:C"}
        result = as_dict(dep)
        assert result["B"] == ["A"]
        assert result["C"] == ["A"]
        assert set(result["D"]) == {"B", "C"}

    def test_all_keywords_stripped(self):
        for kw in ("after", "afterok", "afternotok", "afterany",
                   "aftercorr", "afterburstbuffer"):
            dep = {"B": f"{kw}:A"}
            result = as_dict(dep)
            assert kw not in result["B"]
            assert "A" in result["B"]


# ---------------------------------------------------------------------------
# as_tuple
# ---------------------------------------------------------------------------

class TestAsTuple:
    def test_keyword_is_first_element(self):
        dep = {"B": "afterok:A"}
        result = as_tuple(dep)
        assert result["B"][0] == "afterok"
        assert "A" in result["B"]

    def test_multiple_predecessors(self):
        dep = {"D": "afterok:B:C"}
        result = as_tuple(dep)
        assert result["D"][0] == "afterok"
        assert "B" in result["D"]
        assert "C" in result["D"]

    def test_array_suffix_stripped(self):
        dep = {"B": "afterok:A_10"}
        result = as_tuple(dep)
        assert "A" in result["B"]
        assert "A_10" not in result["B"]

    def test_offset_suffix_stripped(self):
        dep = {"B": "afterok:A+1"}
        result = as_tuple(dep)
        assert "A" in result["B"]
        assert "A+1" not in result["B"]


# ---------------------------------------------------------------------------
# as_placeholder
# ---------------------------------------------------------------------------

class TestAsPlaceholder:
    def test_single_predecessor(self):
        dep = {"B": "afterok:A"}
        assert as_placeholder(dep) == {"B": "afterok:{A}"}

    def test_multiple_predecessors(self):
        dep = {"D": "afterok:B:C"}
        result = as_placeholder(dep)
        assert result["D"] == "afterok:{B}:{C}"

    def test_array_suffix_preserved(self):
        dep = {"B": "afterok:A_10"}
        result = as_placeholder(dep)
        assert result["B"] == "afterok:{A}_10"

    def test_offset_suffix_preserved(self):
        dep = {"B": "afterok:A+1"}
        result = as_placeholder(dep)
        assert result["B"] == "afterok:{A}+1"

    def test_comma_separated_conditions(self):
        dep = {"B": "afterok:A,afternotok:A"}
        result = as_placeholder(dep)
        assert "{A}" in result["B"]
        assert result["B"] == "afterok:{A},afternotok:{A}"


# ---------------------------------------------------------------------------
# task_ordering
# ---------------------------------------------------------------------------

class TestTaskOrdering:
    def test_linear_chain_order(self):
        dep = {"B": "afterok:A", "C": "afterok:B"}
        order = task_ordering(dep)
        assert order.index("A") < order.index("B") < order.index("C")

    def test_diamond_dag_order(self):
        dep = {"B": "afterok:A", "C": "afterok:A", "D": "afterok:B:C"}
        order = task_ordering(dep)
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")

    def test_all_jobs_present(self):
        dep = {"B": "afterok:A", "C": "afterok:B"}
        order = task_ordering(dep)
        assert set(order) == {"A", "B", "C"}

    def test_cycle_raises(self):
        dep = {"A": "afterok:B", "B": "afterok:A"}
        with pytest.raises(graphlib.CycleError):
            task_ordering(dep)


# ---------------------------------------------------------------------------
# parse_array_status
# ---------------------------------------------------------------------------

class TestParseArrayStatus:
    def test_non_array_entries_ignored(self):
        mapping = {"12345": "RUNNING", "12346": "COMPLETED"}
        result = parse_array_status(mapping)
        assert result == {}

    def test_dot_entries_ignored(self):
        # sacct reports batch steps as jobid.batch — should be ignored
        mapping = {"12345_1.batch": "COMPLETED"}
        result = parse_array_status(mapping)
        assert result == {}

    def test_array_tasks_grouped(self):
        mapping = {
            "12345_1": "COMPLETED",
            "12345_2": "COMPLETED",
            "12345_3": "RUNNING",
        }
        result = parse_array_status(mapping)
        assert "12345" in result
        # should contain counts for C and R
        summary = result["12345"]
        assert "2C" in summary
        assert "1R" in summary

    def test_single_state(self):
        mapping = {"99_1": "FAILED", "99_2": "FAILED"}
        result = parse_array_status(mapping)
        assert "99" in result
        assert "2F" in result["99"]


# ---------------------------------------------------------------------------
# Default dict
# ---------------------------------------------------------------------------

class TestDefault:
    def test_present_key_returned_normally(self):
        d = Default({"A": "123"})
        assert d["A"] == "123"

    def test_missing_key_returns_placeholder(self):
        d = Default()
        assert d["foo"] == "{foo}"

    def test_format_map_leaves_unknown_intact(self):
        d = Default({"A": "111"})
        result = "afterok:{A}:{B}".format_map(d)
        assert result == "afterok:111:{B}"


# ---------------------------------------------------------------------------
# check_output (dry-run helper)
# ---------------------------------------------------------------------------

class TestCheckOutput:
    def test_returns_bytes(self):
        result = check_output(["sbatch", "--parsable", "job.sh"])
        assert isinstance(result, bytes)

    def test_prints_command(self, capsys):
        check_output(["sbatch", "job.sh"])
        out = capsys.readouterr().out
        assert "sbatch" in out
        assert "job.sh" in out

    def test_task_name_prints_assignment(self, capsys):
        check_output(["sbatch", "job.sh"], task_name="myjob")
        out = capsys.readouterr().out
        assert "myjob=" in out


# ---------------------------------------------------------------------------
# in_jupyter
# ---------------------------------------------------------------------------

class TestInJupyter:
    def test_returns_false_outside_jupyter(self):
        # In a pytest runner there is no IPython kernel
        assert in_jupyter() is False
