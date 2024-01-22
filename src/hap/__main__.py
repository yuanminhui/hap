import click

from . import commands


@click.group("hap")
@click.version_option()
def cli():
    """Hierarchical Pangenome toolkit."""


for itemname in dir(commands):
    item = getattr(commands, itemname)
    if isinstance(item, click.Command):
        cli.add_command(item, name=itemname)


# if __name__ == "__main__":
#     cli(prog_name="hap")  # pragma: no cover
