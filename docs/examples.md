# Examples

All examples are in the `examples/` directory and can be run with `sworkflow submit` on any system with Slurm.

---

## Minimal — linear pipeline

**Location:** `examples/minimal/`

A three-job sequential pipeline: `preprocess → train → postprocess`. Each job must
complete successfully before the next starts.

```yaml title="examples/minimal/workflow.yaml"
dependency:
  train: afterok:preprocess
  postprocess: afterok:train

jobs:
  preprocess: sbatch examples/minimal/preprocess.sh
  train: sbatch examples/minimal/train.sh
  postprocess: sbatch examples/minimal/postprocess.sh
```

```bash
# Visualize
sworkflow -f examples/minimal/workflow.yaml vis

# Submit (dry-run first)
sworkflow -f examples/minimal/workflow.yaml submit --dry-run
sworkflow -f examples/minimal/workflow.yaml submit
```

**Graph:**

```
preprocess → train → postprocess
```

---

## Branch and merge — diamond DAG

**Location:** `examples/branch-merge/`

A five-job diamond: `A` fans out to `B` and `C` in parallel, both merge into `D`, then `E` runs last.

```yaml title="examples/branch-merge/workflow.yaml"
dependency:
  B: afterok:A
  C: afterok:A
  D: afterok:B:C
  E: afterok:D

jobs:
  A: --wrap='sleep 2'
  B: --wrap='sleep 2'
  C: --wrap='sleep 2'
  D: examples/branch-merge/D.sh
  E: --mem=40G examples/branch-merge/E.sh
```

**What this demonstrates:**

- **Fan-out**: `A` triggers `B` and `C` simultaneously
- **Fan-in**: `D` waits for *both* `B` and `C` before starting (`afterok:B:C`)
- **Mixed command styles**: inline `--wrap`, plain script, script with extra sbatch flags (`--mem=40G`)

**Graph:**

```
    A
   / \
  B   C
   \ /
    D
    |
    E
```

---

## Job array with `after`/`afterok` and minute-offset

**Location:** `examples/job-array/`

An array job (`array`) with 5 tasks, plus three dependent jobs that showcase
different timing conditions.

```yaml title="examples/job-array/workflow.yaml"
dependency:
  B: after:array
  C: afterok:array
  D: after:B+1

jobs:
  array: --array=5,10,15,20,25 --wrap='sleep $SLURM_ARRAY_TASK_ID'
```

**What this demonstrates:**

| Job | Condition | Meaning |
|-----|-----------|---------|
| `B` | `after:array` | Starts as soon as `array` starts (no success check) |
| `C` | `afterok:array` | Waits until all 5 array tasks complete successfully |
| `D` | `after:B+1` | Starts 1 minute after `B` starts (`+n` = minute offset) |

`B`, `C`, and `D` have no entry under `jobs`, so they use the default command:
`sbatch --wrap="sleep 2"`.

**Graph:**

```
array ──► B ──► D
  │
  └──► C
```

---

## Exclusive branching — `afterok` vs `afternotok`

**Location:** `examples/afterok-afternotok/`

`C` and `D` are mutually exclusive: only one fires depending on whether `B` succeeds or fails.

```yaml title="examples/afterok-afternotok/workflow.yaml"
dependency:
  B: afterok:A
  C: afterok:B
  D: afternotok:B

jobs:
  A: --wrap='sleep 2'
  B: --wrap='sleep 2'
  C: --wrap='sleep 2'
  D: --wrap='sleep 2'
```

**What this demonstrates:**

- `afterok:B` — `C` runs only if `B` exits successfully
- `afternotok:B` — `D` runs only if `B` exits with a non-zero status
- These two conditions are **mutually exclusive**: exactly one branch fires

!!! warning "DependencyNeverSatisfied"
    Whichever branch is not triggered will remain in the Slurm queue indefinitely
    with status `DependencyNeverSatisfied`. Cancel it manually:

    ```bash
    scancel <job_id>
    ```

**Graph:**

```
A → B → C   (if B succeeds)
      ↘ D   (if B fails)
```
