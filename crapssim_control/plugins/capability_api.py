from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict


class Verb(ABC):
    @abstractmethod
    def apply(self, state: Dict[str, Any], params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Execute verb effect and return a summary dict."""
        raise NotImplementedError


class Policy(ABC):
    @abstractmethod
    def decide(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Return a decision object."""
        raise NotImplementedError
