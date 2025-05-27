# BestVideo

Video processing and selection tool.

## Setup

1. Install Poetry: `curl -sSL https://install.python-poetry.org | python3 -`
2. Clone the repository: `git clone <your-repo-url>`
3. Navigate to the project directory: `cd bestvideo`
4. Install dependencies: `poetry install`

## Running the pipeline

To run the pipeline with the example configuration:

```bash
poetry run bestvideo --config example.yaml
```

Or simply:
```bash
poetry run bestvideo
```
(This will use `example.yaml` by default)

## Project Structure

```text
bestvideo/
├── bestvideo/              # package root
│   ├── __init__.py
│   ├── config.py           # config dataclasses & loader
│   ├── context.py          # typed Context object
│   ├── pipeline.py         # Pipeline orchestrator
│   ├── base_module.py      # abstract BaseModule
│   └── modules/            # pluggable steps
│       ├── __init__.py
│       ├── scan_demo.py    # Demo: directory scan
│       └── meta_demo.py    # Demo: fake metadata extraction
├── cli.py                  # Typer CLI entry-point
├── pyproject.toml
├── tests/
│   ├── __init__.py
│   └── test_pipeline.py
├── example.yaml            # Example configuration file
└── README.md
```

## Adding New Modules

1.  **Create** new file in `bestvideo/modules/`, e.g. `my_new_module.py`.
2.  **Subclass** `BaseModule` and implement the `run(self, ctx: Context)` method.
    *   Read data from the context: `data = ctx.pull("some_module.output_key")`
    *   Push data to the context: `ctx.push("my_new_module.output_key", result)`
3.  **Add** your module to the `modules` list in your YAML configuration file:

    ```yaml
    - name: bestvideo.modules.my_new_module.MyNewModule # assuming class is MyNewModule
      params:
        some_param_for_module: value
    ```
4.  **Run** the pipeline: `poetry run bestvideo --config your_config.yaml`. 