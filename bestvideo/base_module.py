from abc import ABC, abstractmethod
from typing import Dict, Any
from .context import Context

class BaseModule(ABC):
    def __init__(self, params: Dict[str, Any] | None = None) -> None:
        self.params = params or {}

    @abstractmethod
    def run(self, ctx: Context) -> None:
        """Process context in-place.""" 