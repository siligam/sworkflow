# sworkflow

A lightweight Python toolkit for composing, visualizing, and submitting **Slurm job workflows** with complex dependencies.

Instead of writing fragile Bash scripts with nested `sbatch --dependency` calls, `sworkflow` lets you
**declare dependencies** cleanly in Python or YAML, visualize them as a graph, and submit jobs in the
correct order.

## ❓ Why sworkflow?

Traditional Bash or “Python-flavored Bash” workflows for Slurm often suffer from:

- Fragile chaining: manual `sbatch --dependency` wiring, brittle string parsing
- Hard fan-in/out: merging branches and complex DAGs is error-prone
- Little validation/visibility: cycles and typos appear late at submit/run time
- Poor reuse: copy-pasted scripts with ad-hoc parameters

`sworkflow` addresses this by:

- Declarative DAGs: dependencies as data (YAML/Python), not shell glue
- Built-in validation: uses `graphlib.TopologicalSorter` to prevent cycles and order jobs
- Visualization first: render the DAG before submitting
- Consistent submission: captures job IDs and applies dependency rules uniformly
- Python API + CLI: use as a library or via simple commands

Quick contrast:

**Bash (fragile):**

```bash
jid_pre=$(sbatch --parsable preprocess.sh)
jid_train=$(sbatch --parsable --dependency=afterok:$jid_pre train.sh)
jid_post=$(sbatch --parsable --dependency=afterok:$jid_train postprocess.sh)

echo "preprocess=$jid_pre train=$jid_train postprocess=$jid_post"
```

**sworkflow (declarative):**

```yaml
dependency:
  train: afterok:preprocess
  postprocess: afterok:train
jobs:
  preprocess: preprocess.sh
  train: train.sh
  postprocess: postprocess.sh
```

## 🧭 Table of Contents

- [sworkflow](#sworkflow)
  - [❓ Why sworkflow?](#-why-sworkflow)
  - [🧭 Table of Contents](#-table-of-contents)
  - [🚀 Features](#-features)
  - [📦 Prerequisites](#-prerequisites)
  - [🔧 Installation](#-installation)
  - [⚡ Quick Start](#-quick-start)
    - [Example workflow (`workflow.yaml`)](#example-workflow-workflowyaml)
    - [Submit and visualize](#submit-and-visualize)
  - [🧾 YAML schema (quick reference)](#-yaml-schema-quick-reference)
  - [🐍 Python API](#-python-api)
  - [🌳 Advanced Workflows](#-advanced-workflows)
    - [Branch and Merge](#branch-and-merge)
    - [Job Arrays](#job-arrays)
  - [🔗 Dependency syntax](#-dependency-syntax)
  - [📊 Visualization](#-visualization)
  - [❓ CLI Reference](#-cli-reference)
  - [🧪 Examples](#-examples)
  - [⚠️ Error Handling](#️-error-handling)
  - [🛠️ Troubleshooting](#️-troubleshooting)
  - [🧭 Scope \& limitations](#-scope--limitations)
  - [📚 Resources](#-resources)
  - [🤝 Contributing](#-contributing)
  - [📜 License](#-license)

---

## 🚀 Features

- **Declarative workflow definition** – express dependencies in a dictionary or YAML file
- **Visualization** – generate ASCII or graph-based DAGs before submission
- **Python API & CLI** – use as a library or standalone tool
- **Safer workflows** – prevents dependency cycles, ensures correct ordering
- **Config-driven** – define jobs in YAML for reuse and easy editing

---

## 📦 Prerequisites

- Python **3.9+** (uses `graphlib.TopologicalSorter`)
- A working Slurm environment (`sbatch`, `squeue`, `sacct` available)
- Optional: [Graphviz](https://graphviz.org) for advanced graph visualization

---

## 🔧 Installation

Clone the repository and install:

```bash
git clone https://github.com/siligam/sworkflow.git
cd sworkflow

# Option A: Conda environment
conda env create -f environment.yaml -n sworkflow
conda activate sworkflow
pip install .

# Option B: Virtualenv / system install
python3 -m venv venv
source venv/bin/activate
pip install .
```

---

## ⚡ Quick Start

### Example workflow (`workflow.yaml`)

```yaml
dependency:
  train: afterok:preprocess
  postprocess: afterok:train

jobs:
  preprocess: preprocess.sh
  train: train.sh
  postprocess: postprocess.sh
```

### Submit and visualize

```bash
# Visualize the dependency graph
sworkflow -f workflow.yaml vis

# Dry-run first to verify the generated sbatch commands
sworkflow -f workflow.yaml submit --dry-run

# Submit for real — job IDs are saved back to workflow.yaml
sworkflow -f workflow.yaml submit

# Check job status (reads saved job IDs from workflow.yaml)
sworkflow -f workflow.yaml status
```

## 🧾 YAML schema (quick reference)

```yaml
dependency:        # map[job] -> "<condition>:<dep1>[:<dep2>...]"
  train: afterok:preprocess
  eval: afterany:train:postprocess

jobs:              # map[job] -> shell command or path to script
  preprocess: preprocess.sh
  train: train.sh
  postprocess: postprocess.sh
```

**Note:** If a job value does not include the word `sbatch`, `sworkflow` will automatically prepend
`sbatch --parsable` and inject the appropriate `--dependency=...` flag based on your `dependency`
mapping. You may also pass raw sbatch flags directly (e.g., `--array=... --wrap=...`).

---

## 🐍 Python API

Define workflows directly in Python:

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

suite.visualize(as_ascii=True)
suite.submit()           # submits jobs; saves job IDs to submit.yaml
suite.update_status()    # queries sacct and populates suite.status
```

After `submit()`, job IDs are persisted to a YAML file (defaults to `submit.yaml`, or the file the suite was loaded from). You can reload a previously submitted workflow to check status:

```python
suite = sworkflow.Suite.load_yaml("submit.yaml")
suite.update_status()
```

---

## 🌳 Advanced Workflows

### Branch and Merge

```yaml
dependency:
  B: afterok:A
  C: afterok:A
  D: afterok:B:C
  E: afterok:D

jobs:
  A: A.sh
  B: B.sh
  C: C.sh
  D: D.sh
  E: E.sh
```

This produces:

```text
    A
   / \
  B   C
   \ /
    D
    |
    E
```

### Job Arrays

```yaml
dependency:
  analyze: afterok:array

jobs:
  array: --array=10,20,30 --wrap='sleep $SLURM_ARRAY_TASK_ID'
  analyze: analyze.sh
```

## 🔗 Dependency syntax

All standard Slurm dependency conditions are supported:

| Condition | Meaning |
|-----------|---------|
| `afterok` | Run after all predecessors complete successfully |
| `afterany` | Run after all predecessors finish (any exit status) |
| `afternotok` | Run after any predecessor fails |
| `after` | Run after predecessors start (no status check) |
| `aftercorr` | Run after corresponding array tasks complete |
| `afterburstbuffer` | Run after burst buffer stage-out completes |
| `singleton` | Run once no other job with the same name is running |

Multiple predecessors are colon-separated: `afterok:B:C` means run after both B and C succeed.
All referenced predecessors must be defined under `jobs`.

Example:

```yaml
dependency:
  D: afterok:B:C
jobs:
  B: sbatch B.sh
  C: sbatch C.sh
  D: sbatch D.sh
```

---

## 📊 Visualization

`sworkflow` can render ASCII or Graphviz diagrams.

```bash
sworkflow -f workflow.yaml vis
```

Output:

```text
preprocess
   |
 train
   |
postprocess
```

---

## ❓ CLI Reference

All commands accept `-f/--filename` or the `SFILE` environment variable to specify the workflow file.

```bash
export SFILE=workflow.yaml   # set once, all commands use it
```

### `sworkflow vis`

Render the dependency graph as ASCII art.

```bash
sworkflow -f workflow.yaml vis [--rankdir LR|RL|TB|BT]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--rankdir` | `LR` | Graph layout direction. Aliases accepted: `right`/`left`/`down`/`up` |

### `sworkflow submit`

Submit all jobs to Slurm in dependency order. Job IDs are written back to the YAML file on completion so `status` can find them.

```bash
sworkflow -f workflow.yaml submit [--dry-run]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Print the sbatch commands without executing them; uses fake job IDs |

### `sworkflow status`

Query Slurm for the current state of all submitted jobs.

```bash
sworkflow -f workflow.yaml status [--vis]
```

| Option | Description |
|--------|-------------|
| `--vis` | Overlay job statuses on the dependency graph after printing the table |

---

## 🧪 Examples

See `examples/minimal/` for a minimal runnable setup:

- `examples/minimal/workflow.yaml` – declarative DAG
- `examples/minimal/preprocess.sh`, `examples/minimal/train.sh`, `examples/minimal/postprocess.sh` – sample jobs

Run locally (requires Slurm):

```bash
export SFILE=examples/minimal/workflow.yaml
sworkflow vis
sworkflow submit
```

Note: make scripts executable first:

```bash
chmod +x examples/minimal/*.sh
```

---

## ⚠️ Error Handling

- Dependencies are resolved using `graphlib.TopologicalSorter`, preventing cycles
- Jobs will only run if their dependency conditions (`afterok`, `afterany`, `afternotok`) are satisfied
- Use `sworkflow status` to monitor running workflows

## 🛠️ Troubleshooting

- `command not found: sbatch` – ensure Slurm is installed/loaded and on your PATH (e.g., `module load slurm`)
- Graphviz visualization fails – install `graphviz` and ensure `dot` is on PATH
- Jobs stuck in PENDING – check partition/account/QA constraints and your
  `sbatch` resource flags (`--time`, `--mem`, `--account`, etc.)
- `status` shows nothing – confirm `sacct` is enabled at your site and you have permission to query accounting data

## 🧭 Scope & limitations

- Designed for Slurm; requires `sbatch`/`squeue`/`sacct`
- No built-in retries/backoff beyond what you script in your job commands
- Not a full workflow engine (no caching, scheduling, or cross-cluster orchestration)
- `status` relies on Slurm accounting and may be subject to site-specific retention/latency

---

## 📚 Resources

- [Slurm job dependencies documentation](https://slurm.schedmd.com/sbatch.html#OPT_dependency)
- Presentation: [GoeHPCoffee — Workflow management with sworkflow](https://pad.gwdg.de/s/UYOiCAkUN)

---

## 🤝 Contributing

Issues and pull requests are welcome!

- Fork the repo and create a feature branch
- Add tests or examples if applicable
- Submit a pull request with a clear description

---

## 📜 License

MIT License. See [LICENSE](LICENSE) for details.
