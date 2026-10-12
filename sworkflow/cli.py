import os
import subprocess
from graphlib import CycleError

import click
import yaml

from . import Suite, utils

"""

sworkflow --filename name.yaml vis
export SFILE=name.yaml
sworkflow vis --rankdir 'TB'
sworkflow submit --dry-run
sworkflow submit
SFILE=other.yaml sworkflow vis

"""


class Config:
    def __init__(self):
        self.filename = None

    def load(self):
        """Load and validate the workflow file, turning failures into CLI errors."""
        if not self.filename:
            raise click.UsageError(
                "no workflow file: use -f/--filename or set the SFILE environment variable"
            )
        try:
            suite = Suite.load_yaml(self.filename)
            utils.task_ordering(suite.dependency, suite.jobs)
        except (OSError, yaml.YAMLError) as e:
            raise click.ClickException(str(e))
        except CycleError as e:
            raise click.ClickException("dependency cycle: " + " -> ".join(e.args[1]))
        return suite


pass_config = click.make_pass_decorator(Config, ensure=True)


@click.group()
@click.option(
    "-f",
    "--filename",
    envvar="SFILE",
    type=click.Path(),
    help="yaml file containing job dependency",
)
@pass_config
def cli(ctx, filename):
    """slurm job dependency management

    Define task dependencies in a yaml file. Visualize the dependency graph to
    ensure expected workflow and then submit the job to slurm. Check the status
    of the submitted job.

    NOTE: All commands require `-f/--filename` flag. Either provide
    `-f/--filename` option or set the environment variable `SFILE`.
    """
    sfile = os.environ.get("SFILE", None)
    ctx.filename = filename
    if sfile:
        click.echo("suite definition: {}\n".format(sfile))


@cli.command("vis")
@click.option(
    "--rankdir",
    default="LR",
    show_default=True,
    help="direction of graph layout, LR|RL|TB|BT",
)
@pass_config
def visualize(ctx, rankdir):
    """Visualize the task dependency as described in the yaml file.

    Change graph layout with `--rankdir` option. It also accepts
    `right|left|top|down` as parameters.
    """
    mapper = {
        "LR": ("lr", "r", "right", "forward", "forwards"),
        "RL": ("rl", "l", "left", "backward", "backwards"),
        "TB": ("tb", "d", "down", "downward", "downwards"),
        "BT": ("bt", "u", "up", "upward", "upwards"),
    }
    rank = rankdir.lower()
    for name, options in mapper.items():
        if rank in options:
            target = name
            break
    else:
        target = None
    if target is None:
        click.echo(f"{rankdir} is not valid, using default LeftRight layout.")
        target = "LR"
    ctx.load().visualize(rankdir=target)


@cli.command()
@click.option(
    "--dry-run", is_flag=True, help="simulates job submission with Fake job-ids"
)
@click.option(
    "--force", is_flag=True, help="submit again even if the file already has job-ids"
)
@pass_config
def submit(ctx, dry_run, force):
    """Submits jobs to slurm and updates the yaml file with job-ids

    `--dry-run` prints the sbatch commands with fake job-ids and does not touch
    the yaml file. A file that already has job-ids is refused unless `--force`.
    """
    suite = ctx.load()
    try:
        job_ids = suite.submit(dry_run=dry_run, force=force)
    except ValueError as e:
        raise click.ClickException(str(e))
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"sbatch failed: {e}")
    click.echo(job_ids)


@cli.command()
@click.option("--vis", is_flag=True, help="shows status in graph visualization")
@pass_config
def status(ctx, vis):
    """Gets the current status of the submitted job suite by querying slurm
    controller.

    Status of currently running and completed jobs in the suite are displayed.
    """
    suite = ctx.load()
    res = suite.update_status()
    for line in res:
        click.echo("  ".join(x or "UNKNOWN" for x in line))
    if vis:
        suite.visualize()
