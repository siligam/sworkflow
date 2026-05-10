# Installation

## Prerequisites

- Python **3.9+** (uses `graphlib.TopologicalSorter` from the standard library)
- A working Slurm environment (`sbatch`, `squeue`, `sacct` available on PATH)
- Optional: [Graphviz](https://graphviz.org) for PDF graph rendering

## Install from source

Clone the repository and install with pip:

```bash
git clone https://github.com/siligam/sworkflow.git
cd sworkflow
```

=== "Conda (recommended for HPC)"

    ```bash
    conda env create -f environment.yaml -n sworkflow
    conda activate sworkflow
    pip install .
    ```

=== "Virtualenv"

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install .
    ```

## Verify the installation

```bash
sworkflow --help
```

You should see the top-level help text listing the `vis`, `submit`, and `status` subcommands.

## Optional: Graphviz

ASCII visualization works without Graphviz. For PDF rendering, install the system package:

```bash
# Debian / Ubuntu
sudo apt install graphviz

# macOS
brew install graphviz

# Conda
conda install graphviz
```
