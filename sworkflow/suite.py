# -*- coding: utf-8 -*-
# suite.py
import os
import shlex
import shutil
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

        All of ``dependency``, ``jobs`` and ``job_ids`` are optional and
        default to empty dicts if absent.

        Args:
            filename: Path to the YAML workflow file.

        Returns:
            A new :class:`Suite` instance with :attr:`filename` set to the
            given path.
        """
        d = utils.load_yaml(filename)
        d = d or {}
        dependency = d.get("dependency", {})
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
        :attr:`jobs` receive the default command ``sbatch --wrap="sleep 2"``
        only when :attr:`jobs` is empty (a quick demo); otherwise a job named
        in the dependencies but missing from :attr:`jobs` is an error.

        ``sbatch`` may appear anywhere in the command (e.g. after ``env X=1``);
        the extra flags are inserted right after it.

        Raises:
            ValueError: If :attr:`jobs` is non-empty and a job named in
                :attr:`dependency` has no entry in it (usually a typo), or if a
                job both sets its own ``--dependency`` and has a dependency
                entry.
        """
        dependency = self.dependency
        ordering = utils.task_ordering(dependency, self.jobs)
        dependency_placeholder = utils.as_placeholder(dependency)
        jobs = self.jobs
        missing = [n for n in ordering if jobs and n not in jobs]
        if missing:
            raise ValueError(f"jobs not defined in 'jobs': {', '.join(missing)}")
        result = {}
        for task_name in ordering:
            job = jobs.get(task_name, default_task)
            parts = shlex.split(job)
            at = next(
                (i for i, p in enumerate(parts) if os.path.basename(p) == "sbatch"),
                None,
            )
            if at is None:
                parts.insert(0, "sbatch")
                at = 0
            extra = [] if "--parsable" in parts else ["--parsable"]
            if task_name in dependency_placeholder:
                if any(
                    p in ("-d", "--dependency") or p.startswith("--dependency=")
                    for p in parts
                ):
                    raise ValueError(
                        f"job '{task_name}' has its own --dependency flag and an "
                        "entry under 'dependency'; use only one"
                    )
                extra.append("--dependency=" + dependency_placeholder[task_name])
            parts[at + 1 : at + 1] = extra
            result[task_name] = shlex.join(parts)
        self.job_template.update(result)

    def submit(self, dry_run=False, force=False):
        """Submit all jobs to Slurm in dependency order.

        Calls :meth:`prepare_jobs`, then iterates jobs in topological order,
        substituting captured job IDs into dependency placeholders before each
        ``sbatch`` call. The resulting job IDs are written back to
        :attr:`job_ids` and the workflow is saved to :attr:`filename` (defaulting
        to ``"submit.yaml"``). If a later ``sbatch`` call fails, the IDs of the
        jobs already submitted are still saved before the error propagates. A
        dry run never writes the file or changes :attr:`job_ids`.

        Args:
            dry_run: When ``True``, commands are printed to stdout instead of
                executed and fake random job IDs are used. Useful for
                validating the generated sbatch commands before real submission.
            force: Resubmit even though :attr:`job_ids` is already populated
                (the workflow was submitted before). The old IDs are discarded;
                the earlier jobs keep running in Slurm.

        Returns:
            Dict mapping each job name to its Slurm job ID string (a fake ID
            in dry-run mode).

        Raises:
            ValueError: If :attr:`job_ids` is populated and ``force`` is false.
        """
        if self.job_ids and not (dry_run or force):
            raise ValueError(
                "workflow already has job_ids (submitted before?); "
                "pass force=True to submit it again"
            )
        func = (sp.check_output, utils.check_output)[dry_run]
        ordering = utils.task_ordering(self.dependency, self.jobs)
        self.prepare_jobs()
        if dry_run:
            job_ids = dict(self.job_ids)
        else:
            self.filename = self.filename or "submit.yaml"
            job_ids = self.job_ids
            job_ids.clear()
        submitted = 0
        try:
            for task_name in ordering:
                fill = utils.Default(job_ids)
                # only the dependency flag holds placeholders; braces elsewhere
                # in the user's command must be left alone
                cmd = [
                    p.format_map(fill) if p.startswith("--dependency=") else p
                    for p in shlex.split(self.job_template[task_name])
                ]
                if dry_run:
                    job_id = func(cmd, task_name=task_name)
                else:
                    job_id = func(cmd)
                job_ids[task_name] = job_id.decode("utf-8").strip()
                submitted += 1
        finally:
            if submitted and not dry_run:
                self.save_yaml(self.filename)
        return job_ids

    def _label(self, name):
        parts = [name, self.job_ids.get(name), self.status.get(name)]
        return " ".join(filter(None, parts))

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
        ordering = utils.task_ordering(self.dependency, self.jobs)
        g = graphviz.Digraph()
        g.graph_attr["rankdir"] = rankdir
        for name in ordering:
            g.node(name, self._label(name))
        for name, values in d.items():
            for item in values:
                g.edge(item, name)
        return g

    def visualize(self, rankdir="LR", as_ascii=True, view_pdf=True):
        """Render the workflow dependency graph.

        Behaviour depends on the execution environment:

        - **Jupyter notebook**: returns the :class:`graphviz.Digraph` object
          directly so Jupyter renders it inline.
        - **Terminal (default)**: prints a local plain-text rendering (see
          :func:`~sworkflow.utils.ascii_graph`). Nothing leaves the machine.
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
            order = utils.task_ordering(self.dependency, self.jobs)
            labels = {n: self._label(n) for n in order}
            print(utils.ascii_graph(self.dependency, self.jobs, labels))
            return g
        stem = os.path.splitext(os.path.basename(self.filename or "sworkflow"))[0]
        g.render(f"{stem}-graph", view=view_pdf, cleanup=True)

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
        if shutil.which("sacct") is None:
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
