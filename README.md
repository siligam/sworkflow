# sworkflow

A flexible work-flow for scripting job dependencies in slurm.

A typical approach for defining dependencies between tasks is to capture the
JOB\_ID of the previously submitted job and use it in the next job submission in
order to make the later as a dependent of the previous job. The same process is
repeated for further dependent jobs down the lane. The 2 actions that are
intertwined in this approach are ordering of jobs and managing of JOB\_ID's. For
fewer jobs this is managable but as the larger job, soon it might become a bit
complicated to follow the dependencies.

A different approach is to have seperation of concernes by expressing
dependencies between tasks as a seperate python dictionary mapping and tasks to
run as seperate python dictionary mapping.

# Usage

consider the follow example:

```bash
jobid_1=$(sbatch --parsable preprocess.sh)
jobid_2=$(sbatch --parsable --depend=afterok:${jobid_1} modelrun.sh)
jobid_3=$(sbatch --parsable --depend=afterok:${jobid_2} postprocessing.sh) 
```

This can be written as:
```python
import sworkflow

dep = {
    "modelrun": "afterok:preprocess",
    "postprocess": "afterok:modelrun",
}

tasks = {
    "preprocess": "preprocess.sh",
    "modelrun": "sbatch modelrun.sh",
    "postprocess": "sbatch postprocessing.sh"
}

s = sdepend.sDepend(dep, tasks)
s.submit()
s.visualize(as_ascii=True)
┌────────────┐     ┌──────────┐     ┌─────────────┐
│ preprocess │ ──▶ │ modelrun │ ──▶ │ postprocess │
└────────────┘     └──────────┘     └─────────────┘
```
