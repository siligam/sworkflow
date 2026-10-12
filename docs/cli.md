# CLI Reference

All commands require `-f/--filename` or the `SFILE` environment variable to specify the workflow file.
Problems such as a missing file, an unknown job name or a dependency cycle are reported as a one-line error (exit code 1) instead of a traceback.

```bash
export SFILE=workflow.yaml   # set once, all commands use it
```

---

## `sworkflow vis`

Print the dependency graph as plain text. The text is rendered locally; each job is indented by its depth and lists its predecessors.

```bash
sworkflow -f workflow.yaml vis [--pdf] [--rankdir LR|RL|TB|BT]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--pdf` | off | Write a Graphviz PDF (`<workflow-name>-graph.pdf`, needs `dot`) instead of printing text |
| `--rankdir` | `LR` | Graph layout direction for the PDF (the text view ignores it). Aliases accepted: `right`/`left`/`down`/`up` |

**Example:**

```bash
sworkflow -f workflow.yaml vis
```

```
preprocess
    train  <- preprocess
        postprocess  <- train
```

For a Graphviz PDF, which also honors `--rankdir`:

```bash
sworkflow -f workflow.yaml vis --pdf --rankdir TB   # writes workflow-graph.pdf
```

This needs the Graphviz `dot` executable; from Python use `Suite.visualize(as_ascii=False)`.

---

## `sworkflow submit`

Submit all jobs to Slurm in dependency order. Job IDs are written back to the YAML file on completion so `status` can find them.

```bash
sworkflow -f workflow.yaml submit [--dry-run] [--force]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Print the sbatch commands without executing them; uses fake job IDs and never writes the file |
| `--force` | Submit even if the file already has `job_ids` (refused by default to avoid duplicate jobs) |

If a later `sbatch` call fails, the IDs of the jobs already submitted are still saved to the file before the error is reported.

**Recommended workflow:**

```bash
sworkflow -f workflow.yaml vis            # 1. visualize
sworkflow -f workflow.yaml submit --dry-run  # 2. check commands
sworkflow -f workflow.yaml submit         # 3. submit for real
```

---

## `sworkflow status`

Query Slurm for the current state of all submitted jobs. A job that `sacct` does not know (for example because its accounting record has expired) is shown as `UNKNOWN`.

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

Every name used under `dependency` must also be defined under `jobs`; an unknown name is an error. Avoid names that end in `_<number>` (read as a job-array task) and names made only of digits.

### Existing Slurm jobs

An all-digit token refers to a job that is already in Slurm and is passed through unchanged:

```yaml
dependency:
  D: afterok:123456:C   # wait for existing job 123456 and for workflow job C
```

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
  D: afterok:A,afternotok:B   # D runs only if A succeeds AND B fails
```

Use `?` instead of `,` when any one condition is enough:

```yaml
dependency:
  D: afterok:A?afterok:B      # D runs if A OR B succeeds
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `command not found: sbatch` | Ensure Slurm is loaded: `module load slurm` |
| `vis --pdf` fails with "needs the Graphviz `dot` executable" | Install Graphviz and ensure `dot` is on PATH (e.g. `module load graphviz`) |
| Jobs stuck in PENDING | Check partition/account constraints; verify `--time`, `--mem`, `--account` flags |
| `Error: jobs not defined in 'jobs': ...` | A name in `dependency` has no entry under `jobs`; check for a typo |
| `Error: workflow already has job_ids` | The file was submitted before; use `submit --force` to submit it again (earlier jobs keep running) |
| `status` shows nothing | Confirm `sacct` is enabled and you have permission to query accounting data |
| Branch stuck with `DependencyNeverSatisfied` | Cancel the unneeded branch: `scancel <job_id>` |
