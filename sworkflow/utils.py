import re
import yaml
import shlex
import random
from collections import defaultdict, Counter
from graphlib import TopologicalSorter

keywords = {
    "after",
    "afterok",
    "afternotok",
    "afterany",
    "aftercorr",
    "afterburstbuffer",
    "singleton",
}


_SUFFIX = re.compile(r"^(.+?)([+_]\d+)$")


def _split_suffix(name):
    """Split ``jobA_10`` / ``jobA+1`` into ``("jobA", "_10")`` / ``("jobA", "+1")``.

    Only a numeric ``_taskid`` or ``+offset`` counts as a Slurm array suffix, so
    names such as ``post_process`` are returned unchanged with an empty suffix.
    """
    m = _SUFFIX.match(name)
    return m.groups() if m else (name, "")


def as_dict(dependency):
    """Return a predecessor-list mapping stripped of Slurm dependency keywords.

    Transforms the raw dependency dict into a form suitable for graph
    construction and topological sorting. Slurm condition keywords (e.g.
    ``afterok``) are discarded; only the job names remain.

    Handles Slurm job array suffixes: ``+offset`` (e.g. ``jobA+1``) and
    ``_taskid`` (e.g. ``jobA_10``) are stripped, leaving only the base name.
    All-digit tokens (e.g. ``afterok:123456``) are existing Slurm job IDs, not
    workflow jobs, and are omitted.

    Args:
        dependency: Maps each job name to a Slurm dependency string such as
            ``"afterok:preprocess"`` or ``"afterok:B:C"``.

    Returns:
        Dict mapping each job name to a list of its predecessor job names,
        e.g. ``{"train": ["preprocess"], "postprocess": ["train"]}``.
    """
    names = defaultdict(list)
    pattern = re.compile("[,?:]")
    for name, value in dependency.items():
        names[name]  # keep jobs without predecessors (e.g. ``singleton``)
        for val in pattern.split(value):
            if val in keywords:
                continue
            head = _split_suffix(val)[0]
            if not head.isdigit():  # all-digit tokens are existing Slurm job IDs
                names[name].append(head)
    return dict(names)


def as_tuple(dependency):
    """Parse dependency strings into ``[keyword, dep1, dep2, ...]`` lists.

    Unlike :func:`as_dict`, this preserves the Slurm condition keyword as the
    first element of each list. Handles comma-separated compound conditions
    (``afterok:A,afternotok:B``) and the ``?`` separator for alternative
    conditions.

    Args:
        dependency: Maps each job name to a Slurm dependency string.

    Returns:
        Dict mapping each job name to a flat list starting with the condition
        keyword followed by predecessor names, e.g.
        ``{"train": ["afterok", "preprocess"]}``.
    """
    names = defaultdict(list)
    pattern = re.compile("[,?]")
    for name, value in dependency.items():
        values = pattern.split(value)
        for val in values:
            items = iter(val.split(":"))
            _type = next(items)
            names[name].append(_type)
            for item in items:
                names[name].append(_split_suffix(item)[0])
    return dict(names)


def _formatted(job_str: str) -> str:
    """Convert a single dependency segment into a ``format_map``-ready string.

    Replaces each job name with a ``{name}`` placeholder while preserving the
    Slurm condition keyword and any array suffixes (``+offset`` or ``_taskid``).

    For example, ``"afterok:A:B"`` becomes ``"afterok:{A}:{B}"``, and
    ``"afterok:A+1"`` becomes ``"afterok:{A}+1"``.

    Args:
        job_str: A single colon-separated dependency segment such as
            ``"afterok:preprocess"`` or ``"afterok:B:C"``.

    Returns:
        The same segment with job names wrapped in curly braces.
    """
    keyword, *names = job_str.split(":")
    parts = [keyword]
    for name in names:
        head, tail = _split_suffix(name)
        parts.append(f"{head}{tail}" if head.isdigit() else f"{{{head}}}{tail}")
    return ":".join(parts)


def as_placeholder(dependency):
    """Transform a dependency dict so job names become ``{name}`` placeholders.

    Converts all job name references in the dependency values to Python
    ``str.format_map`` placeholders. The result is used in :meth:`Suite.submit`
    to interpolate real Slurm job IDs at submission time.

    For example, ``{"train": "afterok:preprocess"}`` becomes
    ``{"train": "afterok:{preprocess}"}``.

    Handles comma-separated (``afterok:A,afternotok:B``) and ``?``-separated
    alternative conditions.

    Args:
        dependency: Maps each job name to a Slurm dependency string.

    Returns:
        Dict with the same keys, but job name tokens replaced by
        ``{job_name}`` placeholders.
    """
    result = {}
    for name, value in dependency.items():
        comma_parts = []
        for parts in value.split(","):
            job_strs = [_formatted(job_str) for job_str in parts.split("?")]
            comma_parts.append("?".join(job_strs))
        result[name] = ",".join(comma_parts)
    return result


def task_ordering(dependency, jobs=()):
    """Return jobs in a valid submission order respecting all dependencies.

    Uses :class:`graphlib.TopologicalSorter` on the predecessor graph produced
    by :func:`as_dict`. Root jobs (those with no predecessors) appear first.

    Args:
        dependency: Maps each job name to a Slurm dependency string.
        jobs: Optional iterable of job names. Any not mentioned in
            ``dependency`` are included as independent roots.

    Returns:
        List of job name strings in topological order.

    Raises:
        graphlib.CycleError: If the dependency graph contains a cycle.
    """
    d = as_dict(dependency)
    for name in jobs:
        d.setdefault(name, [])
    return list(TopologicalSorter(d).static_order())


def load_yaml(filename):
    """Read a YAML file and return its contents as a Python object.

    Args:
        filename: Path to the YAML file.

    Returns:
        The parsed YAML content (typically a dict).
    """
    with open(filename, "r") as fid:
        d = yaml.safe_load(fid)
    return d


def save_yaml(content, filename):
    """Write a Python object to a YAML file.

    Args:
        content: The object to serialize (typically a dict).
        filename: Destination file path.
    """
    with open(filename, "w") as fid:
        yaml.safe_dump(content, fid)
    return


def check_output(task, *args, **kwargs):
    """Dry-run replacement for ``subprocess.check_output``.

    Prints the command to stdout instead of executing it, then returns a
    random integer encoded as bytes to simulate a Slurm job ID.

    If ``task_name`` is provided via keyword argument, the output is formatted
    as a shell assignment (``task_name=$(command ...)``), matching how a real
    submission script would capture job IDs.

    Args:
        task: List of command tokens (the same format as
            ``subprocess.check_output``).
        task_name: Optional job name used to format the printed output as a
            shell variable assignment.

    Returns:
        A fake job ID as ``bytes``, e.g. ``b"742"``.
    """
    task_name = kwargs.get("task_name", None)
    if task_name:
        print(f"{task_name}=$({shlex.join(task)})")
    else:
        print(shlex.join(task))
    return bytes(str(random.randint(0, 1000)), encoding="utf-8")


def ascii_graph(dependency, jobs=(), labels=None):
    """Render the workflow as indented plain text, one job per line.

    Jobs are listed in submission order and indented by their depth in the
    DAG; each line ends with ``<- predecessors``. Runs locally, so job names
    never leave the machine.

    Args:
        dependency: Maps each job name to a Slurm dependency string.
        jobs: Optional iterable of job names to include as independent roots.
        labels: Optional mapping of job name to display text.

    Returns:
        The multi-line string.
    """
    deps = as_dict(dependency)
    for name in jobs:
        deps.setdefault(name, [])
    level = {}
    lines = []
    for name in TopologicalSorter(deps).static_order():
        preds = deps.get(name, [])
        level[name] = 1 + max((level[p] for p in preds), default=-1)
        text = (labels or {}).get(name, name)
        if preds:
            text += "  <- " + ", ".join(preds)
        lines.append("    " * level[name] + text)
    return "\n".join(lines)


def in_jupyter():
    """Return ``True`` if the current process is running inside a Jupyter kernel.

    Distinguishes Jupyter notebooks from terminal IPython sessions by checking
    the IPython shell class name.

    Returns:
        ``True`` when running in a Jupyter notebook or JupyterLab cell,
        ``False`` otherwise (including plain Python, terminal IPython, and
        environments where IPython is not installed).
    """
    try:
        from IPython.core import getipython
    except ImportError:
        return False
    ipy = getipython.get_ipython()
    if ipy is None:
        return False
    if "terminal" in str(ipy):
        return False
    return True


class Default(dict):
    """A dict subclass that returns ``"{key}"`` for missing keys.

    Used with :meth:`str.format_map` so that unresolved job-name placeholders
    are left intact in the command string rather than raising a ``KeyError``.
    This allows :meth:`Suite.submit` to build dependency flags progressively as
    each job ID becomes known.
    """

    def __missing__(self, key):
        """Return ``"{key}"`` so unresolved placeholders survive ``format_map``."""
        return f"{{{key}}}"


def parse_array_status(mapping):
    """Collapse Slurm array job entries into a per-parent summary.

    Slurm reports array tasks as separate rows with IDs like ``12345_1``,
    ``12345_2``, etc. This function groups them by parent job ID and produces
    a compact state summary such as ``"2C-1R"`` (2 COMPLETED, 1 RUNNING).

    Only entries whose ID contains ``_`` but not ``.`` are treated as array
    tasks; all others are ignored.

    Args:
        mapping: Dict mapping Slurm job ID strings to state strings, as
            returned by parsing ``sacct`` output.

    Returns:
        Dict mapping each parent array job ID to a summary string like
        ``"3C-1F"`` where each segment is ``<count><first-letter-of-state>``.
    """
    result = {}
    array = defaultdict(Counter)
    for job_id, state in mapping.items():
        if "_" in job_id and "." not in job_id:
            name, _ = job_id.split("_")
            state = state[0]
            array[name][state] += 1
    for job_id, counts in array.items():
        tmp = []
        for name, count in counts.items():
            tmp.append(f"{count}{name}")
        result[job_id] = "-".join(tmp)
    return result
