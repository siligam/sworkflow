import re
import yaml
import shlex
import random
import requests
from collections import defaultdict
from graphlib import TopologicalSorter

keywords = {'after', 'afterok', 'afternotok', 'afterany',
            'aftercorr', 'afterburstbuffer', 'singleton'}


def as_dict(dependency):
    """
    task dependency mapping stripping off keywords
    """
    names = defaultdict(list)
    pattern = re.compile('[,?:]')
    for name, value in dependency.items():
        values = pattern.split(value)
        for val in values:
            if val in keywords:
                continue
            elif '+' in val:
                val, _ = val.split('+')
            elif '_' in val:
                val, _ = val.split('_')
            names[name].append(val)
    return dict(names)


def as_tuple(dependency):
    names = defaultdict(list)
    pattern = re.compile('[,?]')
    for name, value in dependency.items():
        values = pattern.split(value)
        for val in values:
            items = iter(val.split(':'))
            _type = next(items)
            names[name].append(_type)
            for item in items:
                if '+' in item:
                    item, _ = item.split('+')
                elif '_' in item:
                    item, _ = item.split('_')
                names[name].append(item)
    return dict(names)


def _formatted(job_str: str) -> str:
    keyword, *names = job_str.split(':')
    parts = [keyword]
    for name in names:
        if '+' in name:
            head, tail = name.split('+')
            s = f"{{{head}}}+{tail}"
        elif '_' in name:
            head, tail = name.split('_')
            s = f"{{{head}}}_{tail}"
        else:
            s = f"{{{name}}}"
        parts.append(s)
    return ":".join(parts)


def as_placeholder(dependency):
    result = {}
    for name, value in dependency.items():
        comma_parts = []
        for parts in value.split(','):
            job_strs = [_formatted(job_str)
                        for job_str in parts.split('?')]
            comma_parts.append('?'.join(job_strs))
        result[name] = ",".join(comma_parts)
    return result


def task_ordering(dependency):
    """
    ordering of tasks
    """
    d = as_dict(dependency)
    return list(TopologicalSorter(d).static_order())


def load_yaml(filename):
    with open(filename, 'r') as fid:
        d = yaml.safe_load(fid)
    return d


def save_yaml(content, filename):
    with open(filename, 'w') as fid:
        yaml.safe_dump(content, fid)
    return


def check_output(task, *args, **kwargs):
    print(shlex.join(task))
    return bytes(str(random.randint(0, 1000)), encoding='utf-8')


def dot_to_ascii(g):
    url = 'https://dot-to-ascii.ggerganov.com/dot-to-ascii.php'
    params = {'boxart': 1, 'src': str(g)}
    res = requests.get(url, params=params).text
    print(res)
    return res


def in_jupyter():
    try:
        from IPython.core import getipython
    except ImportError:
        return False
    ipy = getipython.get_ipython()
    if ipy is None:
        return False
    if 'terminal' in str(ipy):
        return False
    return True


class Default(dict):
    def __missing__(self, key):
        return f'{{{key}}}'
