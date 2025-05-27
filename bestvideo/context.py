from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

# Forward declaration for AppCfg type hint
if False:  # This block is not executed at runtime
    from .config import AppCfg

@dataclass
class Context:
    """Shared state passed between modules."""
    cfg: "AppCfg"                  # full validated config
    store: Dict[str, Any] = field(default_factory=dict)

    def push(self, key: str, value: Any) -> None:
        self.store[key] = value

    def pull(self, key: str, default: Any = None) -> Any:
        return self.store.get(key, default) 