# Quick Start

## 1. Define your workflow

Create a `workflow.yaml` file describing the dependencies between your jobs:

```yaml
dependency:
  train: afterok:preprocess
  postprocess: afterok:train

jobs:
  preprocess: preprocess.sh
  train: train.sh
  postprocess: postprocess.sh
```

The `dependency` section maps each job to a Slurm dependency string.
The `jobs` section maps each job name to the shell command or script used to submit it.

!!! tip
    If a job command does not include `sbatch`, it is prepended automatically.
    You can pass raw `sbatch` flags directly, e.g. `--mem=40G my_script.sh`.

## 2. Visualize the graph

Before submitting, render the dependency graph to verify it looks correct:

```bash
sworkflow -f workflow.yaml vis
```

Output:

```
preprocess
   |
 train
   |
postprocess
```

## 3. Dry-run

Check the exact `sbatch` commands that will be generated without running anything:

```bash
sworkflow -f workflow.yaml submit --dry-run
```

Output:

```
preprocess=$(sbatch --parsable preprocess.sh)
train=$(sbatch --parsable --dependency=afterok:{preprocess} train.sh)
postprocess=$(sbatch --parsable --dependency=afterok:{train} postprocess.sh)
```

## 4. Submit

```bash
sworkflow -f workflow.yaml submit
```

Job IDs are printed and written back to `workflow.yaml` so `status` can find them later.

## 5. Check status

```bash
sworkflow -f workflow.yaml status
```

## Using the `SFILE` environment variable

Set `SFILE` once to avoid repeating `-f workflow.yaml` on every command:

```bash
export SFILE=workflow.yaml
sworkflow vis
sworkflow submit --dry-run
sworkflow submit
sworkflow status
```

---

## YAML schema

```yaml
dependency:        # map[job] -> "<condition>:<dep1>[:<dep2>...]"
  train: afterok:preprocess
  eval: afterany:train:postprocess

jobs:              # map[job] -> shell command or path to script
  preprocess: preprocess.sh
  train: train.sh
  postprocess: postprocess.sh
```

See [Dependency syntax](cli.md#dependency-syntax) for the full list of supported conditions.

---

## Python API

You can also define and run workflows entirely in Python:

```python
import sworkflow

dependency = {
    "train": "afterok:preprocess",
    "postprocess": "afterok:train",
}

jobs = {
    "preprocess": "preprocess.sh",
    "train": "train.sh",
    "postprocess": "postprocess.sh",
}

suite = sworkflow.Suite(dependency, jobs)

suite.visualize(as_ascii=True)      # print ASCII graph
suite.submit()                       # submit; saves job IDs to submit.yaml
suite.update_status()                # query sacct for current state
```

### Reload a submitted workflow

After `submit()`, job IDs are persisted to the YAML file. Reload it later to check status:

```python
suite = sworkflow.Suite.load_yaml("submit.yaml")
suite.update_status()
print(suite.status)
```

### Load from YAML

```python
suite = sworkflow.Suite.load_yaml("workflow.yaml")
suite.visualize()
suite.submit()
```
