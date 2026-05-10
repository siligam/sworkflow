# CLI Reference

All commands accept `-f/--filename` or the `SFILE` environment variable to specify the workflow file.

```bash
export SFILE=workflow.yaml   # set once, all commands use it
```

---

## `sworkflow vis`

Render the dependency graph as ASCII art.

```bash
sworkflow -f workflow.yaml vis [--rankdir LR|RL|TB|BT]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--rankdir` | `LR` | Graph layout direction. Aliases accepted: `right`/`left`/`down`/`up` and `top`/`bottom` |

**Example:**

```bash
sworkflow -f workflow.yaml vis --rankdir TB
```

---

## `sworkflow submit`

Submit all jobs to Slurm in dependency order. Job IDs are written back to the YAML file on completion so `status` can find them.

```bash
sworkflow -f workflow.yaml submit [--dry-run]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Print the sbatch commands without executing them; uses fake job IDs |

**Recommended workflow:**

```bash
sworkflow -f workflow.yaml vis            # 1. visualize
sworkflow -f workflow.yaml submit --dry-run  # 2. check commands
sworkflow -f workflow.yaml submit         # 3. submit for real
```

---

## `sworkflow status`

Query Slurm for the current state of all submitted jobs.

```bash
sworkflow -f workflow.yaml status [--vis]
```

| Option | Description |
|--------|-------------|
| `--vis` | Overlay job statuses on the dependency graph after printing the table |

---

## Dependency syntax

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

Multiple predecessors are colon-separated: `afterok:B:C` means run after **both** B and C succeed.

### Minute-offset syntax

Append `+n` to delay a dependency by `n` minutes after the predecessor starts:

```yaml
dependency:
  D: after:B+1   # D starts 1 minute after B starts
```

### Comma-separated conditions

Combine multiple conditions with a comma:

```yaml
dependency:
  D: afterok:A,afternotok:B   # D runs if A succeeds OR B fails
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `command not found: sbatch` | Ensure Slurm is loaded: `module load slurm` |
| Graphviz visualization fails | Install `graphviz` and ensure `dot` is on PATH |
| Jobs stuck in PENDING | Check partition/account constraints; verify `--time`, `--mem`, `--account` flags |
| `status` shows nothing | Confirm `sacct` is enabled and you have permission to query accounting data |
| Branch stuck with `DependencyNeverSatisfied` | Cancel the unneeded branch: `scancel <job_id>` |
