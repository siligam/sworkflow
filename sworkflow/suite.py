# -*- coding: utf-8 -*-
# suite.py
import random
import shlex
import subprocess as sp
import graphviz
from . import utils

default_task = 'sbatch --wrap="sleep 2"'


class Suite:
    """Orchestrates a Slurm job workflow defined as a dependency graph.

    Holds the dependency relationships between jobs, their commands, and the
    Slurm job IDs captured after submission. Jobs are submitted in topological
    order so each job's dependencies are already running or complete when it
    starts.

    Attributes:
        dependency: Maps each job name to a Slurm dependency string, e.g.
            ``{"train": "afterok:preprocess"}``. Jobs not listed here are
            treated as roots with no dependencies.
        jobs: Maps each job name to the shell command or script path used to
            submit it. ``sbatch`` and ``--parsable`` are injected automatically
            if absent.
        job_ids: Maps each job name to its Slurm job ID string, populated
            after calling :meth:`submit`.
        job_template: Stores the fully-formed sbatch command strings built by
            :meth:`prepare_jobs`, with dependency flags and job-ID placeholders.
        status: Maps each job name to its Slurm state string (e.g. ``"RUNNING"``),
            populated by :meth:`update_status`.
        filename: Path to the YAML file this suite was loaded from or will be
            saved to.

    Example::

        dependency = {
            'D': 'afterany:C:B',
            'C': 'afterok:A',
            'B': 'after:A',
        }

        jobs = {
            'A': 'sleep.sh',
            'B': 'sbatch --mem 40G sleep.sh',
            'C': 'sbatch --parsable sleep.sh',
        }

        s = Suite(dependency, jobs)
        s.visualize()
        s.submit()
    """

    def __init__(self, dependency: dict, jobs: dict = None, job_ids: dict = None):
        """Initialize a Suite.

        Args:
            dependency: Maps job names to Slurm dependency strings. Each value
                follows Slurm's ``--dependency`` syntax, e.g.
                ``"afterok:preprocess"`` or ``"afterok:B:C"`` for multiple
                predecessors.
            jobs: Maps job names to the command or script used to submit them.
                If ``sbatch`` is absent from a command it is prepended
                automatically. Defaults to an empty dict.
            job_ids: Pre-populated mapping of job name to Slurm job ID, e.g.
                when loading a previously submitted workflow from YAML.
                Defaults to an empty dict.
        """
        self.dependency = dependency
        self.jobs = jobs or {}
        self.job_ids = job_ids or {}
        self.job_template = {}
        self.status = {}
        self.filename = None

    @classmethod
    def load_yaml(cls, filename):
        """Load a workflow from a YAML file.

        The file must contain a ``dependency`` key. ``jobs`` and ``job_ids``
        are optional and default to empty dicts if absent.

        Args:
            filename: Path to the YAML workflow file.

        Returns:
            A new :class:`Suite` instance with :attr:`filename` set to the
            given path.
        """
        d = utils.load_yaml(filename)
        dependency = d["dependency"]
        jobs = d.get("jobs", {})
        job_ids = d.get("job_ids", {})
        c = cls(dependency, jobs, job_ids)
        c.filename = filename
        return c

    def save_yaml(self, filename, include_job_ids=True):
        """Serialize the workflow to a YAML file.

        Args:
            filename: Destination path for the YAML file.
            include_job_ids: When ``True`` (default), the ``job_ids`` section
                is written so that a submitted workflow can be reloaded later
                to check status.
        """
        d = {"dependency": self.dependency, "jobs": self.jobs}
        if include_job_ids:
            d["job_ids"] = self.job_ids
        utils.save_yaml(d, filename)

    def prepare_jobs(self):
        """Build the sbatch command strings for all jobs.

        For each job, this method ensures:

        - ``sbatch`` is the first token.
        - ``--parsable`` appears immediately after ``sbatch`` so the job ID
          is the sole output of the command.
        - ``--dependency=<condition>:{id}:{id}...`` is injected for jobs that
          have predecessors, using ``{job_name}`` placeholders that are
          resolved to real Slurm IDs at submission time.

        Results are stored in :attr:`job_template`. Jobs not present in
        :attr:`jobs` receive the default command ``sbatch --wrap="sleep 2"``.
        """
        dependency = self.dependency
        ordering = utils.task_ordering(dependency)
        dependency_placeholder = utils.as_placeholder(dependency)
        jobs = self.jobs
        result = {}
        for task_name in ordering:
            job = jobs.get(task_name, default_task)
            parts = shlex.split(job)
            if "sbatch" not in parts:
                parts.insert(0, "sbatch")
            if "--parsable" not in parts:
                parts.insert(1, "--parsable")
            if task_name in dependency_placeholder:
                dep = dependency_placeholder.get(task_name)
                dep = "--dependency=" + dep
                parts.insert(2, dep)
            result[task_name] = shlex.join(parts)
        self.job_template.update(result)

    def submit(self, dry_run=False):
        """Submit all jobs to Slurm in dependency order.

        Calls :meth:`prepare_jobs`, then iterates jobs in topological order,
        substituting captured job IDs into dependency placeholders before each
        ``sbatch`` call. The resulting job IDs are written back to
        :attr:`job_ids` and the workflow is saved to :attr:`filename` (defaulting
        to ``"submit.yaml"``).

        Args:
            dry_run: When ``True``, commands are printed to stdout instead of
                executed and fake random job IDs are used. Useful for
                validating the generated sbatch commands before real submission.

        Returns:
            :attr:`job_ids` dict mapping each job name to its Slurm job ID
            string (or a fake ID string in dry-run mode).
        """
        func = (sp.check_output, utils.check_output)[dry_run]
        self.filename = self.filename or "submit.yaml"
        filename = self.filename
        ordering = utils.task_ordering(self.dependency)
        self.prepare_jobs()
        job_template = self.job_template
        job_ids = self.job_ids
        for task_name in ordering:
            job = job_template.get(task_name)
            job = job.format_map(utils.Default(job_ids))
            if dry_run:
                job_id = func(shlex.split(job), task_name=task_name)
            else:
                job_id = func(shlex.split(job))
            job_ids[task_name] = job_id.decode("utf-8").strip()
        self.save_yaml(filename)
        return self.job_ids

    def graph(self, rankdir="LR"):
        """Build a Graphviz directed graph of the workflow.

        Each node is labeled with the job name, its Slurm job ID (if
        submitted), and its current status (if available). Edges point from
        each prerequisite to its dependent job. Calls :meth:`update_status`
        internally so status information is current.

        Args:
            rankdir: Graphviz layout direction. One of ``"LR"`` (left-right,
                default), ``"RL"``, ``"TB"``, or ``"BT"``.

        Returns:
            A :class:`graphviz.Digraph` instance.
        """
        self.update_status()
        d = utils.as_dict(self.dependency)
        ordering = utils.task_ordering(self.dependency)
        g = graphviz.Digraph()
        g.graph_attr["rankdir"] = rankdir
        for name in ordering:
            label = [name, self.job_ids.get(name, ""), self.status.get(name, "")]
            label = " ".join(filter(None, label))
            g.node(name, label)
        for name, values in d.items():
            for item in values:
                g.edge(item, name)
        return g

    def visualize(self, rankdir="LR", as_ascii=True, view_pdf=True):
        """Render the workflow dependency graph.

        Behaviour depends on the execution environment:

        - **Jupyter notebook**: returns the :class:`graphviz.Digraph` object
          directly so Jupyter renders it inline.
        - **Terminal (default)**: converts the graph to ASCII art via an
          external HTTP API and prints it.
        - **PDF mode** (``as_ascii=False``): renders a PDF with Graphviz and
          optionally opens it in the default viewer.

        Args:
            rankdir: Graph layout direction passed to :meth:`graph`.
            as_ascii: When ``True`` (default), render ASCII art in the
                terminal. When ``False``, produce a PDF file.
            view_pdf: When ``as_ascii=False``, automatically open the rendered
                PDF. Has no effect in ASCII mode.

        Returns:
            The :class:`graphviz.Digraph` instance, or ``None`` in ASCII/PDF
            mode (side-effects only).
        """
        g = self.graph(rankdir=rankdir)
        if utils.in_jupyter():
            return g
        if as_ascii:
            utils.dot_to_ascii(g)
            return g
        g.render(f"slurmviz-{str(random.randint(0, 20))}", view=view_pdf)

    def update_status(self):
        """Query Slurm for the current state of all submitted jobs.

        Uses ``sacct`` to fetch job states for every ID in :attr:`job_ids`.
        Slurm array jobs (whose IDs contain ``_``) are collapsed into a
        compact summary string (e.g. ``"2C-1R"`` for 2 completed, 1 running).
        Results are stored in :attr:`status`.

        Returns:
            A list of ``(job_name, job_id, state)`` tuples for each job.
            Returns an empty list if :attr:`job_ids` is empty or if ``sacct``
            is not available on the current system.
        """
        sacct_cmd = 'sacct -n -P --format="jobid,state" -j {}'
        result = []
        if not self.job_ids:
            return result
        try:
            sp.call(["sacct"], stdout=sp.PIPE, close_fds=True)
        except FileNotFoundError:
            return result
        jobids = ",".join(self.job_ids.values())
        cmd = sacct_cmd.format(jobids)
        out = sp.check_output(shlex.split(cmd)).decode("utf-8")
        status = dict([line.strip().split("|") for line in out.splitlines()])
        array = utils.parse_array_status(status)
        for name, job_id in self.job_ids.items():
            st = array.get(job_id, status.get(job_id))
            self.status[name] = st
            result.append((name, job_id, st))
        return result
