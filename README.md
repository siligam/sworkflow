# sworkflow

A flexible work-flow for scripting job dependencies in slurm.

A typical approach for defining dependencies between tasks is to capture the
JOB\_ID of the previously submitted job and use it in the next job submission in
order to make the latter as a dependent of the previous job. The same process is
repeated for further dependent jobs down the lane. The 2 actions that are
intertwined in this approach are ordering of jobs and managing of JOB\_ID's. For
fewer jobs this is manageable but as the larger job, soon it might become a bit
complicated to follow the dependencies.

A different approach is to have separation of concerns by expressing
dependencies between tasks as a separate python dictionary mapping and tasks to
run as separate python dictionary mapping.

# Installation

clone the repository

``` shell
git clone https://github.com/siligam/sworkflow.git
cd sworkflow
```

Install the package using conda

``` shell
conda env create -f environment.yaml -n sworkflow
pip install .
```

# Usage

consider the follow example:
(typical slurm job dependency work-flow commands executed in a shell or via bash script)

```bash
jobid_1=$(sbatch --parsable preprocess.sh)
jobid_2=$(sbatch --parsable --depend=afterok:${jobid_1} modelrun.sh)
jobid_3=$(sbatch --parsable --depend=afterok:${jobid_2} postprocessing.sh) 
```

This can be written as:
(python session)

```python
import sworkflow

dep = {
    "modelrun": "afterok:preprocess",
    "postprocess": "afterok:modelrun",
}

tasks = {
    "preprocess": "preprocess.sh",
    "modelrun": "sbatch modelrun.sh",
    "postprocess": "sbatch postprocessing.sh",
}

s = sworkflow.Suite(dep, tasks)
s.submit()
s.visualize(as_ascii=True)

┌────────────┐     ┌──────────┐     ┌─────────────┐
│ preprocess │ ──▶ │ modelrun │ ──▶ │ postprocess │
└────────────┘     └──────────┘     └─────────────┘
```

**cli**

create a yaml file with task dependencies

``` shell
cat > model.yaml <<EOF
dependency:
  modelrun: afterok:preprocess
  postprocess: afterok:modelrun
jobs:
  preprocess: preprocess.sh
  modelrun: modelrun.sh
  postprocess: postprocessing.sh
EOF
```

visualize the suite

``` shell
sworkflow -f model.yaml vis
┌────────────┐     ┌──────────┐     ┌─────────────┐
│ preprocess │ ──▶ │ modelrun │ ──▶ │ postprocess │
└────────────┘     └──────────┘     └─────────────┘
```

submit suite to slurm. Upon submission, each of the tasks gets assigned slurm job-ids

``` shell
sworkflow -f model.yaml submit
{'modelrun': '9078434', 'postprocess': '9078435', 'preprocess': '9078433'}
```

If desired, this can be verified using the `squeue` command as follows

``` shell
squeue --me
             JOBID PARTITION     NAME     USER ST       TIME  NODES NODELIST(REASON)
           9078433    shared     wrap  a270243 CG       0:04      1 l40000
           9078434    shared     wrap  a270243 PD       0:00      1 (Dependency)
           9078435    shared     wrap  a270243 PD       0:00      1 (Dependency)
```

job status can be tracked with `sworkflow` as follows

``` shell
sworkflow -f model.yaml vis
┌──────────────────────────────┐     ┌──────────────────────────┐     ┌─────────────────────────────┐
│ preprocess 9078433 COMPLETED │ ──▶ │ modelrun 9078434 RUNNING │ ──▶ │ postprocess 9078435 PENDING │
└──────────────────────────────┘     └──────────────────────────┘     └─────────────────────────────┘
```

The `vis` command can be repeated any number of times to get the current activate status of the job

``` shell
sworkflow -f model.yaml vis
┌──────────────────────────────┐     ┌────────────────────────────┐     ┌───────────────────────────────┐
│ preprocess 9078433 COMPLETED │ ──▶ │ modelrun 9078434 COMPLETED │ ──▶ │ postprocess 9078435 COMPLETED │
└──────────────────────────────┘     └────────────────────────────┘     └───────────────────────────────┘
```

The `status` command also provides the same information without visualization

``` shell
sworkflow -f model.yaml status
modelrun  9078434  COMPLETED
postprocess  9078435  COMPLETED
preprocess  9078433  COMPLETED
```

**NOTE**

In `model.yaml` job description for each task is written in super minimal
way. Job submission may fail if some of the slurm directives like `account` and
`partition` are missing.

Here is a more concrete example of yaml file including those details

``` shell
cat > model.yaml <<EOF
dependency:
  modelrun: afterok:preprocess
  postprocess: afterok:modelrun
jobs:
  preprocess: sbatch -A ab0246 -p shared preprocess.sh
  modelrun: sbatch -A ab0246 -p compute modelrun.sh
  postprocess: sbatch -A ab0246 -p shared postprocessing.sh
EOF
```

If relevant slurm directives are declared in the script files, the above example
can go back to the super minimal representation and it still works.


``` shell
cat > model.yaml <<EOF
dependency:
  modelrun: afterok:preprocess
  postprocess: afterok:modelrun
jobs:
  preprocess: preprocess.sh
  modelrun: modelrun.sh
  postprocess: postprocessing.sh
EOF
```


**TIP**

instead of providing `-f model.yaml` argument to `sworkflow` everytime, an
environment varible can be set as follows


``` shell
export SFILE=model.yaml
```

Having done that, `sworkflow` commands become less cluttering as follows

``` shell
sworkflow status
suite definition: model.yaml

modelrun  9078468  COMPLETED
postprocess  9078469  COMPLETED
preprocess  9078467  COMPLETED
```

# Big Picture

The work-flow to build a simple or a complex task dependency is to just
concentrate on gradual iterative building of task graph. Associating the task
names with respective job scripts can be differed as a final step. Just start
off building partial graph and get a intuitive feeling of the task graph by
visualizing it (`sworkflow vis`). Once the task dependencies are defined as
desired, it is also possible to submit the suite even before associating task
names with the actual job scripts. In this case, a dummy task of `sleeping for 2
seconds` is triggered for each task. This way, corrections to suite can be made
if task flow through the graph deviates from users expectation. As a final step,
define association of task name to job script.

For instance, consider building a task graph which branches and
merges. Conceptually this is formulated as a particular task runs only after 2
previous tasks completes. Those 2 previous tasks run only if a task before those
2 tasks completes. To illustrate this, look at the following yaml file

``` shell
cat > branch_merge.yaml <<EOF
dependency:
  E: afterok:D
  D: after:B,afterany:C
  B: afterok:A
  C: afterok:A
EOF
```

Here, task `E` depends on `D` to complete but `D` depends on both `B` and `C` to
complete. Tasks `B` and `C` run only when task `A` completes. It is possible to
visualize this suite in its current state as follows

``` shell
sworkflow -f branch_merge.yaml vis
┌───┐     ┌───┐     ┌───┐     ┌───┐
│ A │ ──▶ │ B │ ──▶ │ D │ ──▶ │ E │
└───┘     └───┘     └───┘     └───┘
  │                   ▲
  │                   │
  ▼                   │
┌───┐                 │
│ C │ ────────────────┘
└───┘
```

change the orientation of the graph if it improves understanding of task flow as
follows

``` shell
sworkflow -f branch_merge.yaml vis --rankdir left
                              ┌───┐
            ┌──────────────── │ C │
            │                 └───┘
            │                   ▲
            │                   │
            ▼                   │
┌───┐     ┌───┐     ┌───┐     ┌───┐
│ E │ ◀── │ D │ ◀── │ B │ ◀── │ A │
└───┘     └───┘     └───┘     └───┘
```

# Presentation

I talked about this tool in one of GoeHPCoffee sessions at GWDG. The
presentation not only covers a brief overview of slurm's `--dependency` feature
but also showcases usage of this package with few examples.

Presentation link: https://pad.gwdg.de/ZVBwU_rPSOih4PWK0B3wMA?view
