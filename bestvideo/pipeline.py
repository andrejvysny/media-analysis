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
            # Ensure the module path starts with 'bestvideo' if it's a local module
            if not mod_path.startswith("bestvideo") and "." not in mod_path:
                mod_path = f"bestvideo.modules.{mod_path}"
            elif not mod_path.startswith("bestvideo") and "modules" not in mod_path:
                mod_path = f"bestvideo.modules.{mod_path}"

            try:
                mod = import_module(mod_path)
            except ModuleNotFoundError:
                 # Try absolute import if relative fails or not specific enough
                mod = import_module(f"bestvideo.modules.{m.name.rsplit('.',1)[0]}") 

            cls = getattr(mod, cls_name)
            stages.append(cls(m.params))
        return stages

    def run(self) -> None:
        console.rule("[bold blue]BestVideo Pipeline")
        for stage in self.stages:
            console.print(f"[cyan]▶ Running {stage.__class__.__name__}")
            stage.run(self.ctx)
        console.rule("[green]✔ Pipeline Finished") 