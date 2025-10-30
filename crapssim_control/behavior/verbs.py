from __future__ import annotations
from typing import Dict, Any, Callable

class VerbRegistry:
    def __init__(self):
        self._verbs: Dict[str, Callable[[Dict[str,Any]], Dict[str,Any]]] = {}

    def register(self, name: str, fn: Callable[[Dict[str,Any]], Dict[str,Any]]) -> None:
        self._verbs[name] = fn

    def apply(self, name: str, args: Dict[str,Any]) -> Dict[str,Any]:
        if name not in self._verbs:
            raise KeyError(f"Verb not registered: {name}")
        return self._verbs[name](args)

# Default verbs: return a normalized "intent" to be validated/applied by controller legality gate.
def default_registry() -> VerbRegistry:
    vr = VerbRegistry()
    vr.register("switch_profile", lambda a: {"verb":"switch_profile", "name": a["name"]})
    vr.register("press", lambda a: {"verb":"press", "bet": a["bet"], "units": int(a.get("units",1))})
    vr.register("regress", lambda a: {"verb":"regress", "bet": a["bet"], "units": int(a.get("units",1))})
    vr.register("apply_policy", lambda a: {"verb":"apply_policy", "name": a["name"]})
    return vr
