# @package    sim2l library
# @copyright  Copyright (c) 2005-2026 Purdue University.
# @license    http://opensource.org/licenses/MIT MIT

"""Top-level sim2l command line interface."""

import click

from .mcp import mcp
from .services import services


@click.group()
def cli():
    """sim2l command line tools."""
    pass


cli.add_command(services)
cli.add_command(mcp)


if __name__ == "__main__":
    cli()
