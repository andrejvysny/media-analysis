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