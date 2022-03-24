import os
import click
from . import Suite

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
        self.suite = None


pass_config = click.make_pass_decorator(Config, ensure=True)


@click.group()
@click.option(
    '-f',
    '--filename',
    envvar="SFILE",
    type=click.Path(),
    help='yaml file containing job dependency',
)
@pass_config
def cli(ctx, filename):
    "slurm job dependency management"
    sfile = os.environ.get('SFILE', None)
    if filename:
        s = Suite.load_yaml(filename)
    else:
        s = Suite(dependency={})
    ctx.suite = s
    ctx.filename = filename
    if sfile:
        click.echo('suite definition: {}\n'.format(sfile))


@cli.command('vis')
@click.option(
    '--rankdir',
    default='LR',
    help='direction of graph layout, LR|RL|TB|BT',
)
@pass_config
def visualize(ctx, rankdir):
    ctx.suite.visualize(rankdir=rankdir)


@cli.command()
@click.option('--dry-run', is_flag=True)
@pass_config
def submit(ctx, dry_run):
    job_ids = ctx.suite.submit(dry_run=dry_run)
    click.echo(job_ids)


@cli.command()
@click.option('--vis', is_flag=True)
@pass_config
def status(ctx, vis):
    res = ctx.suite.update_status()
    for line in res:
        click.echo("  ".join(line))
    if vis:
        ctx.suite.visualize()
