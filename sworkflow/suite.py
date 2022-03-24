# -*- coding: utf-8 -*-
# suite.py
import random
import shlex
import subprocess as sp
import graphviz
from . import utils

"""
A python interface to script slurm dependency.

Specify dependencies between tasks as a python dictionary mapping.
Tasks are to be defined in a separate mapping.

task dependency example:

dependency = {
    'D': 'afterany:C:B',
    'C': 'afterok:A',
    'B': 'after:A',
  }

jobs = {
    'A': 'sleep.sh',
    'B': 'sbatch --parsable sleep.sh',
    'C': 'sbatch --mem 40G sleep.sh'
}

s = Suite(dependency, jobs)
"""

default_task = 'sbatch --wrap="sleep 2"'


class Suite:

    def __init__(self, dependency: dict, jobs: dict = None, job_ids: dict = None):
        self.dependency = dependency
        self.jobs = jobs or {}
        self.job_ids = job_ids or {}
        self.job_template = {}
        self.status = {}
        self.filename = None

    @classmethod
    def load_yaml(cls, filename):
        d = utils.load_yaml(filename)
        dependency = d['dependency']
        jobs = d.get('jobs', {})
        job_ids = d.get('job_ids', {})
        c = cls(dependency, jobs, job_ids)
        c.filename = filename
        return c

    def save_yaml(self, filename, include_job_ids=True):
        d = {'dependency': self.dependency, 'jobs': self.jobs}
        if include_job_ids:
            d['job_ids'] = self.job_ids
        utils.save_yaml(d, filename)

    def prepare_jobs(self):
        dependency = self.dependency
        ordering = utils.task_ordering(dependency)
        dependency_placeholder = utils.as_placeholder(dependency)
        jobs = self.jobs
        result = {}
        for task_name in ordering:
            job = jobs.get(task_name, default_task)
            parts = shlex.split(job)
            if 'sbatch' not in parts:
                parts.insert(0, 'sbatch')
            if '--parsable' not in parts:
                parts.insert(1, '--parsable')
            if task_name in dependency_placeholder:
                dep = dependency_placeholder.get(task_name)
                dep = "--dependency=" + dep
                parts.insert(2, dep)
            result[task_name] = shlex.join(parts)
        self.job_template.update(result)

    def submit(self, dry_run=False):
        func = (sp.check_output, utils.check_output)[dry_run]
        self.filename = self.filename or 'submit.yaml'
        filename = self.filename
        ordering = utils.task_ordering(self.dependency)
        self.prepare_jobs()
        job_template = self.job_template
        job_ids = self.job_ids
        for task_name in ordering:
            job = job_template.get(task_name)
            job = job.format_map(utils.Default(job_ids))
            job_id = func(shlex.split(job))
            job_ids[task_name] = job_id.decode('utf-8').strip()
        self.save_yaml(filename)
        return self.job_ids

    def graph(self, rankdir='LR'):
        d = utils.as_dict(self.dependency)
        ordering = utils.task_ordering(self.dependency)
        g = graphviz.Digraph()
        g.graph_attr['rankdir'] = rankdir
        for name in ordering:
            label = [name, self.job_ids.get(name, ''), self.status.get(name, '')]
            label = ' '.join(filter(None, label))
            g.node(name, label)
        for name, values in d.items():
            for item in values:
                g.edge(item, name)
        return g

    def visualize(self, rankdir='LR', as_ascii=True, view_pdf=True):
        g = self.graph(rankdir=rankdir)
        if utils.in_jupyter():
            return g
        if as_ascii:
            utils.dot_to_ascii(g)
            return g
        g.render(f"slurmviz-{str(random.randint(0, 20))}", view=view_pdf)

    def update_status(self):
        sacct_cmd = 'sacct -n -P --format="jobid,state" -j {}'
        result = []
        if not self.job_ids:
            return result
        try:
            sp.call(['sacct'])
        except FileNotFoundError:
            return result
        jobids = ','.join(self.job_ids.values())
        cmd = sacct_cmd.format(jobids)
        out = sp.check_output(shlex.split(cmd)).decode('utf-8')
        status = dict([line.strip().split('|') for line in out.splitlines()])
        for name, job_id in self.job_ids.items():
            st = status.get(job_id)
            self.status[name] = st
            result.append((name, job_id, st))
        return result
