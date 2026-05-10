# sworkflow

A lightweight Python toolkit for composing, visualizing, and submitting **Slurm job workflows** with complex dependencies.

Instead of writing fragile Bash scripts with nested `sbatch --dependency` calls, `sworkflow` lets you **declare dependencies** cleanly in Python or YAML, visualize them as a graph, and submit jobs in the correct order.

---

## Why sworkflow?

Traditional Bash or "Python-flavored Bash" workflows for Slurm often suffer from:

- **Fragile chaining** – manual `sbatch --dependency` wiring, brittle string parsing
- **Hard fan-in/out** – merging branches and complex DAGs is error-prone
- **Little validation** – cycles and typos appear late at submit/run time
- **Poor reuse** – copy-pasted scripts with ad-hoc parameters

`sworkflow` addresses this by:

- **Declarative DAGs** – dependencies as data (YAML/Python), not shell glue
- **Built-in validation** – uses `graphlib.TopologicalSorter` to prevent cycles and order jobs
- **Visualization first** – render the DAG before submitting
- **Consistent submission** – captures job IDs and applies dependency rules uniformly
- **Python API + CLI** – use as a library or via simple commands

---

## Quick contrast

=== "Bash (fragile)"

    ```bash
    jid_pre=$(sbatch --parsable preprocess.sh)
    jid_train=$(sbatch --parsable --dependency=afterok:$jid_pre train.sh)
    jid_post=$(sbatch --parsable --dependency=afterok:$jid_train postprocess.sh)

    echo "preprocess=$jid_pre train=$jid_train postprocess=$jid_post"
    ```

=== "sworkflow (declarative)"

    ```yaml
    dependency:
      train: afterok:preprocess
      postprocess: afterok:train
    jobs:
      preprocess: preprocess.sh
      train: train.sh
      postprocess: postprocess.sh
    ```

---

## Features

- **Declarative workflow definition** – express dependencies in a dictionary or YAML file
- **Visualization** – generate ASCII or graph-based DAGs before submission
- **Python API & CLI** – use as a library or standalone tool
- **Safer workflows** – prevents dependency cycles, ensures correct ordering
- **Config-driven** – define jobs in YAML for reuse and easy editing

---

[Get started →](quickstart.md){ .md-button .md-button--primary }
[Installation →](installation.md){ .md-button }
