"""CLI entrypoint for chatshare."""

import click
from chatstyle import (
    CommandField,
    CommandSchema,
    add_interactive_option,
    render_success,
    resolve_command_inputs,
)


HELLO_SCHEMA = CommandSchema(
    name="hello",
    fields=(CommandField("name", prompt="name", required=True),),
)


@click.group()
def main() -> None:
    """chatshare command line interface."""


@main.command()
@click.argument("name", required=False)
@add_interactive_option
def hello(name: str | None, interactive: bool | None) -> None:
    """Print a greeting with ChatStyle-backed input resolution."""

    values = resolve_command_inputs(
        schema=HELLO_SCHEMA,
        provided={"name": name},
        interactive=interactive,
        usage="Usage: chatshare hello [NAME]",
    )
    render_success(f"Hello, {values['name']}!")


if __name__ == "__main__":
    main()
