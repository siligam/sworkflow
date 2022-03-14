# -*- coding: utf-8 -*-
# sdepend.py

from collections import defaultdict
from graphlib import TopologicalSorter
import subprocess as sp
import random


"""
A python interface to script slurm dependency.

Specify dependencies between tasks as a python dictionary mapping.
Tasks are to be defined in a seperate mapping.

task dependency example:

dependency = {
    'D': 'afterany:C:B',
    'C': 'afterok:A',
    'B': 'after:A',
  }

tasks = {
    'A': 'sleep.sh',
    'B': 'sbatch --parsable sleep.sh',
    'C': 'sbatch --mem 40G sleep.sh'
}
"""

__all__ = ['submit', 'visualize', 'sDepend']

keywords = "after afterok afternotok afterany aftercorr singleton".split()
default_task = "sbatch sleep_for_second.sh"


def submit(dependency, tasks=None, dryrun=False):
    s = sDepend(dependency, tasks=tasks)
    s.submit(dryrun=dryrun)
    return s


def visualize(dependency, tasks=None, as_ascii=True):
    s = sDepend(dependency, tasks=tasks)
    s.visualize(as_ascii=as_ascii)
    return s


def is_valid(dependency):
    res = task_ordering(dependency)
    return True if res else False


def transform(dependency):
    """
    task dependency mapping stripping off keywords
    """
    names = defaultdict(set)
    for name, value in dependency.items():
        value = value.replace(',', ':')
        for item in value.split(':'):
            if item not in keywords:
                names[name].add(item)
    return dict(names)


def task_ordering(dependency):
    "ordering of tasks"
    d = transform(dependency)
    return list(TopologicalSorter(d).static_order())


class sDepend:
    def __init__(self, dependency, tasks=None):
        self.dependency = dependency
        self.tasks = tasks
        self.task_ids = {}
        self.jobs = {}

    def update_dependency(self, task_dependency):
        result = []
        for part in task_dependency.split(','):
            sub = []
            for item in part.split(':'):
                if item in keywords:
                    sub.append(item)
                    continue
                task_id = self.task_ids[item]
                sub.append(task_id)
            result.append(':'.join(sub))
        return ",".join(result)

    def format_task(self, task, task_name=None):
        parts = task.split()
        if 'sbatch' not in parts:
            parts.insert(0, 'sbatch')
        if '--parsable' not in parts:
            parts.insert(1, '--parsable')
        dep = self.dependency.get(task_name)
        if dep is None:
            return " ".join(parts)
        dep = self.update_dependency(dep)
        dep = "--depend=" + dep
        parts.insert(2, dep)
        return " ".join(parts)

    def submit(self, dryrun=False):
        ordering = task_ordering(self.dependency)
        for task_name in ordering:
            task = self.tasks.get(task_name, default_task)
            task = self.format_task(task, task_name)
            self.process(task, task_name, dryrun)
            self.jobs[task_name] = task

    def process(self, task, task_name, dryrun):
        func = sp.check_output
        if dryrun:
            func = FakeProcess.check_output
        job_id = func(task.split())
        job_id = job_id.decode().strip()
        self.task_ids[task_name] = job_id

    def visualize(self, as_ascii=False):
        import graphviz
        d = transform(self.dependency)
        ordering = task_ordering(self.dependency)
        g = graphviz.Digraph()
        for name in ordering:
            task_id = self.task_ids.get(name)
            if task_id is None:
                g.node(name, name)
            else:
                g.node(name, f"{name} - {task_id}")
        for name, values in d.items():
            for item in values:
                g.edge(item, name)
        if as_ascii:
            import requests
            url = 'https://dot-to-ascii.ggerganov.com/dot-to-ascii.php'
            g.graph_attr['rankdir'] = 'LR'
            params = {'boxart': 1, 'src': str(g)}
            res = requests.get(url, params=params).text
            print(res)
            return
        g.render(f"slurmviz-{str(random.randint(0, 10))}", view=True)


class FakeProcess:
    @staticmethod
    def check_output(task):
        print(" ".join(task))
        return bytes(str(random.randint(0, 1000)), encoding='utf-8')
        
