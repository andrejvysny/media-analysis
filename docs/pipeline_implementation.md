## Implementation Plan – **Modular Pipeline Skeleton** (Python)

The steps below create the **project scaffold**, **pipeline core**, and a pair of **demo modules**.
Each module is **self-contained** and communicates through a **typed context object**, so future modules can be added or replaced without touching existing code.

---

### 0. Prerequisites

| Tool   | Version |
| ------ | ------- |
| Python | ≥ 3.10  |
| Poetry | ≥ 1.8   |
| Git    | latest  |

---

### 1. Project Layout

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
│   └── test_pipeline.py
└── README.md
```

---

### 2. Set-Up with **Poetry**

```bash
poetry new bestvideo
cd bestvideo
poetry add typer[all] pydantic rich tqdm
poetry add --group dev pytest black ruff
```

`pyproject.toml` already contains package metadata; Poetry manages virtual-envs and locking.

---

### 3. **Config** Handling (`config.py`)

```python
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field
import yaml

class ModuleCfg(BaseModel):
    name: str                  # dotted path to module class
    params: dict = Field(default_factory=dict)

class AppCfg(BaseModel):
    root: Path
    db: Path
    modules: List[ModuleCfg]

def load_config(path: Path) -> AppCfg:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return AppCfg.model_validate(data)
```

*Any* future YAML keys validate against these models.

---

### 4. **Context Object** (`context.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

@dataclass
class Context:
    """Shared state passed between modules."""
    cfg: "AppCfg"                  # full validated config
    store: Dict[str, Any] = field(default_factory=dict)

    def push(self, key: str, value: Any) -> None:
        self.store[key] = value

    def pull(self, key: str, default: Any = None) -> Any:
        return self.store.get(key, default)
```

* **Immutable inputs** (cfg) + **mutable store**.
* Store keys are **namespaced** (`"scan.files"`, `"meta.info"`, …).

---

### 5. **Base Module** (`base_module.py`)

```python
from abc import ABC, abstractmethod
from typing import Dict, Any
from .context import Context

class BaseModule(ABC):
    def __init__(self, params: Dict[str, Any] | None = None) -> None:
        self.params = params or {}

    @abstractmethod
    def run(self, ctx: Context) -> None:
        """Process context in-place."""
```

Every real module inherits and implements `run()`.

---

### 6. **Pipeline Orchestrator** (`pipeline.py`)

```python
from importlib import import_module
from typing import List
from rich.console import Console
from .context import Context
from .base_module import BaseModule
from .config import AppCfg

console = Console()

class Pipeline:
    def __init__(self, cfg: AppCfg) -> None:
        self.cfg = cfg
        self.ctx = Context(cfg=cfg)
        self.stages: List[BaseModule] = self._load_stages()

    def _load_stages(self) -> List[BaseModule]:
        stages: List[BaseModule] = []
        for m in self.cfg.modules:
            mod_path, cls_name = m.name.rsplit(".", 1)
            mod = import_module(mod_path)
            cls = getattr(mod, cls_name)
            stages.append(cls(m.params))
        return stages

    def run(self) -> None:
        console.rule("[bold blue]BestVideo Pipeline")
        for stage in self.stages:
            console.print(f"[cyan]▶ Running {stage.__class__.__name__}")
            stage.run(self.ctx)
        console.rule("[green]✔ Pipeline Finished")
```

* Uses **dynamic import** for pluggability.
* **Rich** console rules for readability.

---

### 7. **Demo Modules**

#### 7.1 `scan_demo.py`

```python
from pathlib import Path
from tqdm import tqdm
from ..base_module import BaseModule
from ..context import Context

class ScanDemo(BaseModule):
    """Dummy scan – collects *.mp4 files."""

    def run(self, ctx: Context) -> None:
        root = Path(ctx.cfg.root)
        files = [p for p in root.rglob("*.mp4")]
        for _ in tqdm(files, desc="Scanning"):
            pass  # demo: no work
        ctx.push("scan.files", files)
```

#### 7.2 `meta_demo.py`

```python
from ..base_module import BaseModule
from ..context import Context

class MetaDemo(BaseModule):
    """Pretend to extract metadata."""

    def run(self, ctx: Context) -> None:
        files = ctx.pull("scan.files", [])
        fake_meta = {str(f): {"duration": 0, "codec": "demo"} for f in files}
        ctx.push("meta.info", fake_meta)
```

Both modules **read** / **write** through `Context`.

---

### 8. **CLI Entry-Point** (`cli.py`)

```python
import typer
from pathlib import Path
from bestvideo.config import load_config
from bestvideo.pipeline import Pipeline

app = typer.Typer()

@app.command()
def run(config: Path):
    """Run BestVideo pipeline."""
    cfg = load_config(config)
    Pipeline(cfg).run()

if __name__ == "__main__":
    app()
```

Install as console-script via `pyproject.toml`:

```toml
[tool.poetry.scripts]
bestvideo = "cli:app"
```

---

### 9. **Sample Config** (`example.yaml`)

```yaml
root: /tmp/videos
db: /tmp/bestvideo.db
modules:
  - name: bestvideo.modules.scan_demo.ScanDemo
    params: {}
  - name: bestvideo.modules.meta_demo.MetaDemo
    params: {}
```

---

### 10. **Unit-Test Skeleton** (`tests/test_pipeline.py`)

```python
from bestvideo.config import AppCfg, ModuleCfg
from bestvideo.pipeline import Pipeline

def test_pipeline_runs(tmp_path):
    cfg = AppCfg(
        root=tmp_path,
        db=tmp_path / "db.sqlite",
        modules=[
            ModuleCfg(name="bestvideo.modules.scan_demo.ScanDemo"),
            ModuleCfg(name="bestvideo.modules.meta_demo.MetaDemo"),
        ],
    )
    Pipeline(cfg).run()
    assert (tmp_path / "db.sqlite")  # placeholder assertion
```

---

### 11. **Formatting, Linting, CI**

```bash
poetry run black .
poetry run ruff check .
pytest
```

Add **pre-commit** hooks and a basic **GitHub Actions** workflow later.

---

### 12. How to **Extend**

1. **Create** new file in `bestvideo/modules`, e.g. `hashing.py`.
2. **Subclass** `BaseModule`, declare `run()`.
3. **Add** to YAML:

```yaml
- name: bestvideo.modules.hashing.HashModule
  params:
    p_hash_size: 16
```

4. **Run** `bestvideo --config my.yaml`.

*No pipeline code changes required.*

---

### Result

You now have a **clean, pluggable skeleton**:

* **Swap / add** modules by editing YAML.
* **Context** decouples stages.
* **Pipeline** manages ordering, logging, and progress.
* Ready for incremental implementation of real functionality (metadata, hashing, quality analysis, etc.).
