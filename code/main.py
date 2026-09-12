from pathlib import Path
from typing import Annotated

import typer

from config import load_config
from solve import solve
from sources import load_world
from writer import write_output

app = typer.Typer(
    help=(
        "Recommend whether to pay, wait, or skip each Buy or Wait? evaluation Request."
    ),
    add_completion=False,
)


@app.command()
def main(
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            help=(
                "Write the submission table here. Defaults to output.csv "
                "at the repository root."
            ),
            show_default=False,
        ),
    ] = None,
) -> None:
    """Write one Decision row per evaluation Request."""
    config = load_config()
    destination = output if output is not None else config.output_path
    world = load_world(config.dataset_dir)
    rows = [solve(world, request) for request in world.requests]
    write_output(rows, destination)
    typer.echo(f"Wrote {len(rows)} Decision rows to {destination}")


if __name__ == "__main__":
    app()
