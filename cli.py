import typer
from pathlib import Path
from bestvideo.config import load_config
from bestvideo.pipeline import Pipeline

app = typer.Typer()

@app.command()
def run(config: Path = typer.Option("example.yaml", help="Path to the configuration file.")):
    """Run BestVideo pipeline."""
    cfg = load_config(config)
    Pipeline(cfg).run()

if __name__ == "__main__":
    app() 