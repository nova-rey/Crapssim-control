"""Adapter contract & action grammar.
See docs/engine_contract.md#effect-schema-10 for the uniform effect_summary schema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from importlib import import_module
import warnings
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Type, TypedDict

__all__ = [
    "EngineAdapter",
    "NullAdapter",
    "VanillaAdapter",
    "VerbRegistry",
    "PolicyRegistry",
    "Effect",
    "validate_effect_summary",
]



class Effect(TypedDict, total=False):
    schema: str
    verb: str
    target: Dict[str, Any]
    bets: Dict[str, str]
    bankroll_delta: float
    policy: Optional[str]
    level_update: Dict[str, int]


def _is_delta(s: str) -> bool:
    if not isinstance(s, str) or len(s) < 2:
        return False
    if s[0] not in "+-":
        return False
    try:
        float(s[1:])
        return True
    except Exception:
        return False


def validate_effect_summary(effect: Mapping[str, Any], schema: str = "1.0") -> None:
    # Fail-closed validator used before journaling
    if effect.get("schema") != schema:
        raise ValueError(f"effect_schema_mismatch:{effect.get('schema')}")
    if "verb" not in effect:
        raise ValueError("effect_missing:verb")
    if "bankroll_delta" not in effect or not isinstance(effect["bankroll_delta"], (int, float)):
        raise ValueError("effect_missing:bankroll_delta")
    bets = effect.get("bets", {})
    if bets is None:
        bets = {}
    if not isinstance(bets, dict):
        raise ValueError("effect_invalid:bets_type")
    for k, v in bets.items():
        if not _is_delta(v):
            raise ValueError(f"effect_invalid:bet_delta:{k}={v}")


VerbHandler = Callable[[Dict[str, Any], Dict[str, Any]], Effect]
PolicyHandler = Callable[[Dict[str, Any], Dict[str, Any]], Effect]


def _try_import_crapssim() -> Tuple[Optional[EngineAdapter], Optional[str]]:
    """Instantiate the CrapsSim adapter when available."""

    try:
        adapter_cls, reason = resolve_engine_adapter()
    except Exception as exc:  # pragma: no cover - defensive guard
        return None, f"resolve_failed:{exc}"

    if adapter_cls is None:
        return None, reason

    try:
        return adapter_cls(), None
    except Exception as exc:  # pragma: no cover - adapter construction errors
        return None, f"instantiate_failed:{exc}"


def _normalize_snapshot(raw_snapshot: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Normalize arbitrary engine snapshots into CSC's canonical shape."""

    raw_snapshot = raw_snapshot or {}
    bankroll = raw_snapshot.get("bankroll")
    try:
        bankroll_val = float(bankroll) if bankroll is not None else 0.0
    except (TypeError, ValueError):
        bankroll_val = 0.0

    point_value = raw_snapshot.get("point_value")
    try:
        point_val_norm = int(point_value) if point_value is not None else None
    except (TypeError, ValueError):
        point_val_norm = None

    hand_id = raw_snapshot.get("hand_id")
    try:
        hand_id_norm = int(hand_id) if hand_id is not None else 0
    except (TypeError, ValueError):
        hand_id_norm = 0

    roll_in_hand = raw_snapshot.get("roll_in_hand")
    try:
        roll_norm = int(roll_in_hand) if roll_in_hand is not None else 0
    except (TypeError, ValueError):
        roll_norm = 0

    rng_seed = raw_snapshot.get("rng_seed")
    try:
        rng_seed_norm = int(rng_seed) if rng_seed is not None else 0
    except (TypeError, ValueError):
        rng_seed_norm = 0

    bets_norm: Dict[str, float] = {}
    bets_obj = raw_snapshot.get("bets")
    if isinstance(bets_obj, Mapping):
        for key, value in bets_obj.items():
            amount = value
            name = key
            if isinstance(value, Mapping):
                amount = value.get("amount")
                name = value.get("name") or key
            try:
                bets_norm[str(name)] = float(amount) if amount is not None else 0.0
            except (TypeError, ValueError):
                continue

    normalized = {
        "bankroll": bankroll_val,
        "point_on": bool(raw_snapshot.get("point_on", False)) or bool(point_val_norm),
        "point_value": point_val_norm,
        "bets": bets_norm,
        "hand_id": hand_id_norm,
        "roll_in_hand": roll_norm,
        "rng_seed": rng_seed_norm,
    }

    if "levels" in raw_snapshot:
        levels = raw_snapshot.get("levels")
        if isinstance(levels, Mapping):
            normalized["levels"] = {str(k): int(v) for k, v in levels.items() if isinstance(v, (int, float))}
    if "last_effect" in raw_snapshot:
        normalized["last_effect"] = raw_snapshot.get("last_effect")

    return normalized


_DEPRECATION_EMITTED = False


class VerbRegistry:
    _handlers: Dict[str, VerbHandler] = {}

    @classmethod
    def register(cls, name: str, fn: VerbHandler) -> None:
        cls._handlers[name] = fn

    @classmethod
    def get(cls, name: str) -> VerbHandler:
        if name not in cls._handlers:
            raise KeyError(f"unknown_verb:{name}")
        return cls._handlers[name]


class PolicyRegistry:
    _handlers: Dict[str, PolicyHandler] = {}

    @classmethod
    def register(cls, name: str, fn: PolicyHandler) -> None:
        cls._handlers[name] = fn

    @classmethod
    def get(cls, name: str) -> PolicyHandler:
        if name not in cls._handlers:
            raise KeyError(f"unknown_policy:{name}")
        return cls._handlers[name]


# --------------------------------------------------------------------------------------
# CrapsSim discovery (best-effort; tolerate missing engine at import time)
# --------------------------------------------------------------------------------------
_HAS_LEGACY_PLAYERS = False
try:  # pragma: no cover - exercised in engine-present workflows
    import crapssim.strategy as cs_strategy  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - engine not installed
    cs_strategy = None  # type: ignore

try:  # pragma: no cover - exercised in engine-present workflows
    import crapssim.players as cs_players  # type: ignore
    _HAS_LEGACY_PLAYERS = True
except ModuleNotFoundError:  # pragma: no cover - engine not installed
    cs_players = None  # type: ignore

try:  # pragma: no cover - exercised in engine-present workflows
    from crapssim.table import Table as _CsTable  # type: ignore
except Exception:  # pragma: no cover - tolerate missing engine shapes
    _CsTable = None  # type: ignore


@dataclass
class EngineAttachResult:
    table: Any
    controller_player: Any
    meta: Dict[str, Any]


# --------------------------------------------------------------------------------------
# Engine contract
# --------------------------------------------------------------------------------------
class EngineAdapter(ABC):
    """Abstract base adapter defining the CrapsSim engine interface.
    See docs/engine_contract.md for method definitions and determinism expectations.
    """

    @abstractmethod
    def start_session(self, spec: Dict[str, Any]) -> None:
        """Initialize the engine with a simulation spec."""
        raise NotImplementedError

    @abstractmethod
    def step_roll(
        self, dice: Optional[Tuple[int, int]] = None, seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """Advance one roll using fixed dice or RNG seed."""
        raise NotImplementedError

    @abstractmethod
    def apply_action(self, verb: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a CSC action to the engine and return the effect."""
        raise NotImplementedError

    @abstractmethod
    def snapshot_state(self) -> Dict[str, Any]:
        """Return a snapshot of current engine state."""
        raise NotImplementedError


# --------------------------------------------------------------------------------------
# Null (no-engine) implementation used for controller smoke paths
# --------------------------------------------------------------------------------------
class NullAdapter(EngineAdapter):
    """No-op adapter used when no engine is available."""

    def __init__(self) -> None:
        self._attach_result: Optional[EngineAttachResult] = None

    def start_session(self, spec: Dict[str, Any]) -> None:  # pragma: no cover - trivial
        self._attach_result = EngineAttachResult(
            table=None,
            controller_player=None,
            meta={"mode": "noop"},
        )

    def step_roll(
        self, dice: Optional[Tuple[int, int]] = None, seed: Optional[int] = None
    ) -> Dict[str, Any]:
        return {"result": "noop", "dice": dice, "seed": seed}

    def apply_action(self, verb: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"applied": verb, "args": args, "result": "noop"}

    def snapshot_state(self) -> Dict[str, Any]:
        return {
            "bankroll": 0.0,
            "point_on": False,
            "point_value": None,
            "bets": {},
            "hand_id": 0,
            "roll_in_hand": 0,
            "rng_seed": 0,
        }

    # --- Back-compat shims (TEMP: remove by P7·C3) ---
    def attach(self, spec: Dict[str, Any]):  # pragma: no cover - compatibility shim
        warnings.warn(
            "NullAdapter.attach() is deprecated; use start_session(). Will be removed in P7·C3.",
            DeprecationWarning,
        )
        self.start_session(spec)
        return {"attached": True, "mode": "noop"}

    @classmethod
    def attach_cls(cls, spec: Dict[str, Any]):  # pragma: no cover - compatibility shim
        warnings.warn(
            "NullAdapter.attach_cls() is deprecated; use start_session() on an instance. Will be removed in P7·C3.",
            DeprecationWarning,
        )
        inst = cls()
        return inst.attach(spec)

    def play(self, shooters: int = 1, rolls: int = 3) -> Dict[str, Any]:  # pragma: no cover - shim
        warnings.warn(
            "NullAdapter.play() is deprecated; use controller-run paths. Will be removed in P7·C3.",
            DeprecationWarning,
        )
        return {"shooters": int(shooters), "rolls": int(rolls), "status": "noop"}


class VanillaAdapter(EngineAdapter):
    """
    Adapter that defaults to deterministic stubs but can bridge to CrapsSim live engines.
    """

    def __init__(self):
        self.spec: Dict[str, Any] = {}
        self.seed: Optional[int] = None
        self.live_engine: bool = False
        self._engine_adapter: Optional[EngineAdapter] = None
        self._engine_reason: Optional[str] = None
        self._snapshot_cache: Dict[str, Any] = {}

        self._reset_stub_state()

    @staticmethod
    def _coerce_seed(seed_raw: Any) -> Optional[int]:
        if seed_raw is None or isinstance(seed_raw, bool):
            return None
        try:
            return int(seed_raw)
        except (TypeError, ValueError):
            try:
                return int(str(seed_raw).strip())
            except Exception:
                return None

    def _reset_stub_state(self) -> None:
        self.bankroll: float = 1000.0
        self.bets: Dict[str, float] = {"6": 0.0, "8": 0.0, "pass": 0.0, "dc": 0.0}
        self.last_effect: Optional[Effect] = None
        self.martingale_levels: Dict[str, int] = {}
        base_snapshot = {
            "bankroll": self.bankroll,
            "point_on": False,
            "point_value": None,
            "bets": dict(self.bets),
            "hand_id": 0,
            "roll_in_hand": 0,
            "rng_seed": self.seed or 0,
            "levels": dict(self.martingale_levels),
            "last_effect": self.last_effect,
        }
        self._snapshot_cache = _normalize_snapshot(base_snapshot)

    def set_seed(self, seed: Optional[int]) -> None:
        coerced = self._coerce_seed(seed)
        self.seed = coerced
        engine = self._engine_adapter if self.live_engine else None
        if engine is None or coerced is None:
            return
        set_seed_fn = getattr(engine, "set_seed", None)
        if callable(set_seed_fn):
            try:
                set_seed_fn(int(coerced))
            except Exception:  # pragma: no cover - engine reseed best-effort
                return

    def start_session(self, spec: Dict[str, Any]) -> None:
        self.spec = spec or {}
        run_cfg = self.spec.get("run") if isinstance(self.spec, dict) else {}
        if isinstance(run_cfg, dict):
            run_seed = self._coerce_seed(run_cfg.get("seed"))
            if run_seed is not None:
                self.seed = run_seed
        adapter_cfg = run_cfg.get("adapter") if isinstance(run_cfg, dict) else {}
        live_requested = bool(adapter_cfg.get("live_engine")) if isinstance(adapter_cfg, dict) else False

        self.live_engine = False
        self._engine_adapter = None
        self._engine_reason = None

        if live_requested:
            engine, reason = _try_import_crapssim()
            if engine is not None:
                self._engine_adapter = engine
                self.live_engine = True
                engine.start_session(self.spec)
                self.set_seed(self.seed)
                snapshot = _normalize_snapshot(engine.snapshot_state())
                self._apply_normalized_snapshot(snapshot)
                return
            self._engine_reason = reason

        self._reset_stub_state()

    def step_roll(
        self, dice: Optional[Tuple[int, int]] = None, seed: Optional[int] = None
    ) -> Dict[str, Any]:
        if seed is not None:
            self.set_seed(seed)
        if self.live_engine and self._engine_adapter is not None:
            raw = self._engine_adapter.step_roll(dice=dice, seed=seed)
            snapshot = _normalize_snapshot(raw)
            self._apply_normalized_snapshot(snapshot)
            return snapshot
        return {"result": "stub", "dice": dice, "seed": self.seed}

    def apply_action(self, verb: str, args: Dict[str, Any]) -> Dict[str, Any]:
        global _DEPRECATION_EMITTED
        if verb == "martingale":
            if not _DEPRECATION_EMITTED:
                warnings.warn(
                    "verb 'martingale' is deprecated; use apply_policy(policy='martingale_v1')",
                    DeprecationWarning,
                )
                _DEPRECATION_EMITTED = True
            raw_args = dict(args or {})
            policy = raw_args.get("policy")
            if not isinstance(policy, dict):
                policy = {"name": "martingale_v1"}
            policy.setdefault("name", "martingale_v1")
            alias_args = {
                key: raw_args.get(key)
                for key in ("step_key", "delta", "max_level")
                if raw_args.get(key) is not None
            }
            existing_policy_args = dict(policy.get("args") or {})
            for key, value in alias_args.items():
                existing_policy_args.setdefault(key, value)
            if alias_args or existing_policy_args:
                policy["args"] = existing_policy_args
            raw_args["policy"] = policy
            args = {"policy": policy}
            verb = "apply_policy"

        if self.live_engine and self._engine_adapter is not None and verb in {"press", "regress"}:
            try:
                action_args = args or {}
                before = _normalize_snapshot(self._engine_adapter.snapshot_state())
                result = self._engine_adapter.apply_action(verb, action_args)
                after = _normalize_snapshot(self._engine_adapter.snapshot_state())
                if isinstance(result, Mapping) and result.get("schema") == "1.0":
                    effect = result  # type: ignore[assignment]
                else:
                    effect = self._effect_from_snapshot_delta(verb, action_args, before, after)
                self._apply_normalized_snapshot(after)
                self.last_effect = effect
                return effect
            except Exception:  # pragma: no cover - fail open to stub
                warnings.warn(
                    "live_engine_press_regress_failed:fallback_to_stub", RuntimeWarning
                )

        handler = VerbRegistry.get(verb)
        effect = handler(self._effect_context(), args or {})
        self._apply_effect(effect)
        self.last_effect = effect
        return effect

    def _effect_context(self) -> Dict[str, Any]:
        return {
            "bankroll": self.bankroll,
            "bets": dict(self.bets),
            "seed": self.seed or 0,
            "levels": dict(self.martingale_levels),
        }

    def _apply_effect(self, effect: Effect) -> None:
        for bet, delta_str in (effect.get("bets") or {}).items():
            try:
                delta = float(delta_str)
            except (TypeError, ValueError):
                continue
            self.bets[bet] = max(0.0, self.bets.get(bet, 0.0) + delta)

        bankroll_delta = effect.get("bankroll_delta")
        if bankroll_delta is not None:
            try:
                self.bankroll = float(self.bankroll + float(bankroll_delta))
            except (TypeError, ValueError):
                pass

        if "level_update" in effect:
            updates = effect.get("level_update") or {}
            for key, level in updates.items():
                try:
                    self.martingale_levels[key] = int(level)
                except (TypeError, ValueError):
                    continue

        self._snapshot_cache = _normalize_snapshot(
            {
                "bankroll": self.bankroll,
                "bets": dict(self.bets),
                "point_on": False,
                "point_value": None,
                "hand_id": 0,
                "roll_in_hand": 0,
                "rng_seed": self.seed or 0,
                "levels": dict(self.martingale_levels),
                "last_effect": self.last_effect,
            }
        )

    def _apply_normalized_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self.bankroll = float(snapshot.get("bankroll", self.bankroll))
        bets = snapshot.get("bets") or {}
        if isinstance(bets, Mapping):
            self.bets = {str(k): float(v) for k, v in bets.items()}
        rng_seed = snapshot.get("rng_seed")
        if isinstance(rng_seed, (int, float)):
            self.seed = int(rng_seed)
        levels = snapshot.get("levels")
        if isinstance(levels, Mapping):
            self.martingale_levels = {
                str(k): int(v) for k, v in levels.items() if isinstance(v, (int, float))
            }
        elif self.live_engine:
            self.martingale_levels = {}
        last_effect = snapshot.get("last_effect")
        if isinstance(last_effect, Mapping):
            self.last_effect = last_effect  # type: ignore[assignment]
        self._snapshot_cache = dict(snapshot)

    def _effect_from_snapshot_delta(
        self,
        verb: str,
        args: Dict[str, Any],
        before: Dict[str, Any],
        after: Dict[str, Any],
    ) -> Effect:
        bets_before = before.get("bets") or {}
        bets_after = after.get("bets") or {}
        deltas: Dict[str, str] = {}
        if isinstance(bets_before, Mapping) and isinstance(bets_after, Mapping):
            keys = set(str(k) for k in bets_before.keys()) | set(str(k) for k in bets_after.keys())
            for bet in keys:
                try:
                    before_amt = float(bets_before.get(bet, 0.0) or 0.0)
                except (TypeError, ValueError):
                    before_amt = 0.0
                try:
                    after_amt = float(bets_after.get(bet, 0.0) or 0.0)
                except (TypeError, ValueError):
                    after_amt = before_amt
                delta = after_amt - before_amt
                if abs(delta) < 1e-6:
                    continue
                sign = "+" if delta >= 0 else ""
                deltas[bet] = f"{sign}{delta:.0f}"

        bankroll_before = before.get("bankroll") or 0.0
        bankroll_after = after.get("bankroll") or 0.0
        try:
            bankroll_delta = float(bankroll_after) - float(bankroll_before)
        except (TypeError, ValueError):
            bankroll_delta = 0.0

        target = args.get("target") if isinstance(args, Mapping) else {}

        effect: Effect = {
            "schema": "1.0",
            "verb": verb,
            "target": dict(target) if isinstance(target, Mapping) else {},
            "bets": deltas,
            "bankroll_delta": bankroll_delta,
            "policy": None,
        }
        return effect

    def snapshot_state(self) -> Dict[str, Any]:
        if self.live_engine and self._engine_adapter is not None:
            raw = self._engine_adapter.snapshot_state()
            snapshot = _normalize_snapshot(raw)
            if self.last_effect is not None:
                snapshot["last_effect"] = self.last_effect
            if self.martingale_levels:
                snapshot["levels"] = dict(self.martingale_levels)
            self._apply_normalized_snapshot(snapshot)
            return snapshot

        base_snapshot = {
            "bankroll": self.bankroll,
            "point_on": False,
            "point_value": None,
            "bets": dict(self.bets),
            "hand_id": 0,
            "roll_in_hand": 0,
            "rng_seed": self.seed or 0,
        }
        snapshot = _normalize_snapshot(base_snapshot)
        if self.martingale_levels:
            snapshot["levels"] = dict(self.martingale_levels)
        if self.last_effect is not None:
            snapshot["last_effect"] = self.last_effect
        self._snapshot_cache = dict(snapshot)
        return snapshot


# ----------------- Built-in Verb Handlers -----------------


def verb_press(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Effect:
    target = (args.get("target") or {}).get("bet")
    amt = float((args.get("amount") or {}).get("value", 0))
    if not target or amt <= 0:
        raise ValueError("press_invalid_args")
    return {
        "schema": "1.0",
        "verb": "press",
        "target": {"bet": target},
        "bets": {target: f"+{amt:.0f}"},
        "bankroll_delta": -amt,
        "policy": None,
    }


def verb_regress(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Effect:
    selector: list[str] = []
    target = args.get("target") or {}
    if "selector" in target:
        selector = list(target.get("selector") or [])
    elif "bet" in target:
        selector = [target.get("bet")]  # type: ignore[list-item]
    if not selector:
        raise ValueError("regress_invalid_args")

    bets: Dict[str, str] = {}
    bankroll_delta = 0.0
    for bet in selector:
        current = float(snapshot.get("bets", {}).get(bet, 0.0))
        take = current / 2.0
        if take <= 0:
            continue
        bets[bet] = f"-{take:.0f}"
        bankroll_delta += take

    return {
        "schema": "1.0",
        "verb": "regress",
        "target": {"selector": selector},
        "bets": bets,
        "bankroll_delta": bankroll_delta,
        "policy": None,
    }


def verb_same_bet(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Effect:
    target = (args.get("target") or {}).get("bet")
    return {
        "schema": "1.0",
        "verb": "same_bet",
        "target": {"bet": target},
        "bets": {},
        "bankroll_delta": 0.0,
        "policy": None,
    }


def verb_switch_profile(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Effect:
    name = (args.get("details") or {}).get("profile") or args.get("profile") or "default"
    return {
        "schema": "1.0",
        "verb": "switch_profile",
        "target": {"profile": name},
        "bets": {},
        "bankroll_delta": 0.0,
        "policy": None,
    }


def verb_apply_policy(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Effect:
    policy = args.get("policy") or {}
    name = policy.get("name")
    handler = PolicyRegistry.get(name)
    effect = handler(snapshot, policy.get("args") or {})
    effect.update({"schema": "1.0", "verb": "apply_policy", "policy": name})
    return effect


VerbRegistry.register("press", verb_press)
VerbRegistry.register("regress", verb_regress)
VerbRegistry.register("same_bet", verb_same_bet)
VerbRegistry.register("switch_profile", verb_switch_profile)
VerbRegistry.register("apply_policy", verb_apply_policy)


# ----------------- Built-in Policy Handlers -----------------


def pol_martingale_v1(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Effect:
    key = str(args.get("step_key", ""))
    delta = float(args.get("delta", 0.0))
    max_level = int(args.get("max_level", 1))
    if not key or delta <= 0 or max_level < 1:
        raise ValueError("martingale_invalid_args")

    levels = dict(snapshot.get("levels") or {})
    level = int(levels.get(key, 0)) + 1
    if level > max_level:
        level = 0

    increment = delta * (level if level > 0 else 0)
    bets: Dict[str, str] = {}
    bankroll_delta = 0.0
    if increment > 0:
        bets[key] = f"+{increment:.0f}"
        bankroll_delta = -increment

    return {
        "target": {"bet": key},
        "bets": bets,
        "bankroll_delta": bankroll_delta,
        "level_update": {key: level},
    }


PolicyRegistry.register("martingale_v1", pol_martingale_v1)

# --------------------------------------------------------------------------------------
# CrapsSim bridge (ported from legacy adapter, refit for EngineAdapter ABC)
# --------------------------------------------------------------------------------------

def check_engine_ready() -> Tuple[bool, Optional[str]]:
    """Return (ok, reason) indicating whether the CrapsSim engine is usable."""

    if _CsTable is None and cs_strategy is None and not _HAS_LEGACY_PLAYERS:
        return False, "Could not import crapsim.table.Table or strategy/players modules"

    tbl_mod = None
    if _CsTable is not None:
        try:
            tbl_mod = import_module(_CsTable.__module__)
        except Exception:
            tbl_mod = None
    if tbl_mod is None:
        try:
            tbl_mod = import_module("crapssim.table")
        except Exception as exc:
            return False, f"crapssim.table.Table unavailable: {exc}"

    if not hasattr(tbl_mod, "Table"):
        return False, "crapssim.table.Table unavailable"

    has_player = hasattr(tbl_mod, "Player")
    if not has_player:
        try:
            player_mod = import_module("crapssim.player")
            has_player = hasattr(player_mod, "Player")
        except Exception:
            has_player = False
    if not has_player:
        return False, "crapssim Player class unavailable"

    has_dice = hasattr(tbl_mod, "Dice")
    if not has_dice:
        try:
            dice_mod = import_module("crapssim.dice")
            has_dice = hasattr(dice_mod, "Dice")
        except Exception:
            has_dice = False
    if not has_dice:
        return False, "crapssim Dice class unavailable"

    return True, None


def _resolve_modern_strategy_base() -> Tuple[Optional[type], Optional[type]]:
    if cs_strategy is None:
        return None, None
    StrategyBase = getattr(cs_strategy, "Strategy", None) or getattr(cs_strategy, "BaseStrategy", None)
    SimplePass = getattr(cs_strategy, "PassLineStrategy", None)
    return StrategyBase, SimplePass


def _build_controller_strategy(spec: Dict[str, Any], strategy_base: type) -> Any:
    import crapssim.bet as B  # type: ignore

    PassLine = getattr(B, "PassLine", None)
    Place = getattr(B, "Place", None)
    Field = getattr(B, "Field", None)

    def _point_value(table):
        pt = getattr(table, "point", None)
        if pt is not None and not isinstance(pt, (int, type(None))):
            pt = getattr(pt, "value", getattr(pt, "number", None))
        return pt

    def _mk_pass(amount: int):
        if not PassLine:
            return None
        try:
            return PassLine(amount=amount)
        except TypeError:
            try:
                return PassLine(amount)
            except Exception:
                return None

    def _mk_field(amount: int):
        if not Field:
            return None
        try:
            return Field(amount=amount)
        except TypeError:
            try:
                return Field(amount)
            except Exception:
                return None

    def _mk_place(number: int, amount: int):
        if not Place:
            return None
        for kw in ({"number": number, "amount": amount}, {"amount": amount, "number": number}):
            try:
                return Place(**kw)
            except TypeError:
                continue
        for args in ((number, amount),):
            try:
                return Place(*args)
            except Exception:
                continue
        return None

    class ControlStrategy(strategy_base):  # type: ignore[misc]
        def __init__(self, spec_dict: Dict[str, Any]):
            try:
                super().__init__()
            except TypeError:
                try:
                    super().__init__(name="CSC-Control")
                except TypeError:
                    pass
            self.name = "CSC-Control"
            self._spec = spec_dict
            self._armed = False
            self._last_point = None

        def _player_add_many(self, player, bets):
            bets = [b for b in bets if b is not None]
            if not bets:
                return False
            fn = getattr(player, "add_strategy_bets", None)
            if callable(fn):
                try:
                    fn(bets)
                    return True
                except Exception:
                    pass
            ok = False
            add1 = getattr(player, "add_bet", None)
            if callable(add1):
                for b in bets:
                    try:
                        add1(b)
                        ok = True
                    except Exception:
                        pass
                if ok:
                    return True
            try:
                lst = getattr(player, "bets", None)
                if isinstance(lst, list):
                    lst.extend(b for b in bets if b is not None)
                    return True
            except Exception:
                pass
            return False

        def _player_clear_bets(self, player) -> bool:
            for name in ("clear_bets", "clear", "reset_bets"):
                fn = getattr(player, name, None)
                if callable(fn):
                    try:
                        fn()
                        return True
                    except Exception:
                        continue
            try:
                bets = getattr(player, "bets", None)
                if isinstance(bets, list):
                    bets[:] = []
                    return True
            except Exception:
                pass
            return False

        def update_bets(self, player) -> None:
            table = getattr(player, "table", None)
            point = _point_value(table) if table is not None else None
            comeout = point in (None, 0)

            if comeout or point != self._last_point:
                self._armed = False
                self._last_point = point
                self._player_clear_bets(player)

            if comeout:
                self._player_add_many(player, [_mk_pass(10)])
                return

            if not self._armed:
                self._player_add_many(
                    player,
                    [
                        _mk_place(6, 12),
                        _mk_place(8, 12),
                        _mk_field(5),
                    ],
                )
                self._armed = True

        def completed(self, player) -> bool:  # pragma: no cover - interface shim
            return False

        def reset(self, *a, **k):  # pragma: no cover - compatibility
            self._armed, self._last_point = False, None

        def on_shooter_change(self, *a, **k):  # pragma: no cover - compatibility
            self.reset()

        def on_seven_out(self, *a, **k):  # pragma: no cover - compatibility
            self.reset()

        def on_comeout(self, *a, **k):  # pragma: no cover - compatibility
            return

        def on_point_established(self, *a, **k):  # pragma: no cover - compatibility
            return

        def on_point(self, *a, **k):  # pragma: no cover - compatibility
            return

        def on_roll(self, *a, **k):  # pragma: no cover - compatibility
            return

        def apply_template(self, *a, **k):  # pragma: no cover - compatibility
            return

        def clear_bets(self, *a, **k):  # pragma: no cover - compatibility
            return

    abstract = getattr(strategy_base, "__abstractmethods__", set()) or set()
    for name in abstract:
        if not hasattr(ControlStrategy, name):
            setattr(
                ControlStrategy,
                name,
                (lambda *a, **k: False) if name == "completed" else (lambda *a, **k: None),
            )

    return ControlStrategy(spec)


def _attach_modern(table: Any, spec: Dict[str, Any]) -> EngineAttachResult:
    StrategyBase, _ = _resolve_modern_strategy_base()
    if StrategyBase is None:
        raise RuntimeError(
            "CrapsSim ≥0.3.x detected but no Strategy base found. Expected crapssim.strategy.Strategy or .BaseStrategy."
        )

    controller_strategy = _build_controller_strategy(spec, StrategyBase)

    bankroll = int(
        spec.get("bankroll")
        or spec.get("run", {}).get("bankroll")
        or spec.get("table", {}).get("bankroll", 1000)
    )

    add_player = getattr(table, "add_player", None)
    add_strategy = getattr(table, "add_strategy", None)

    if callable(add_player):
        attached = False
        for kw_name in ("strategy", "bet_strategy"):
            try:
                add_player(bankroll=bankroll, **{kw_name: controller_strategy}, name="CSC-Control")
                attached = True
                break
            except TypeError:
                continue
            except Exception:
                pass
        if not attached:
            try:
                add_player(bankroll=bankroll, strategy=controller_strategy)
                attached = True
            except Exception:
                try:
                    add_player(bankroll=bankroll, bet_strategy=controller_strategy)
                    attached = True
                except Exception:
                    add_player(bankroll, controller_strategy, "CSC-Control")
                    attached = True
    elif callable(add_strategy):
        try:
            add_strategy(strategy=controller_strategy, name="CSC-Control")
        except TypeError:
            add_strategy(strategy=controller_strategy)
    else:
        raise RuntimeError("Table has neither add_player nor add_strategy.")

    try:
        players = getattr(table, "players", None)
        p0 = players[0] if players else None
        if p0 is None:
            raise RuntimeError("No player attached after add_* call.")
        set_br = getattr(p0, "set_bankroll", None)
        if callable(set_br):
            set_br(float(bankroll))
        else:
            for attr in ("bankroll", "total_player_cash", "chips", "_bankroll"):
                if hasattr(p0, attr):
                    try:
                        setattr(p0, attr, float(bankroll))
                    except Exception:
                        pass
    except Exception:
        pass

    return EngineAttachResult(
        table=table,
        controller_player=controller_strategy,
        meta={"mode": "modern", "bankroll": bankroll},
    )


def _attach_legacy(table: Any, spec: Dict[str, Any]) -> EngineAttachResult:
    if cs_players is None:
        raise RuntimeError("Legacy players API requested but 'crapssim.players' is unavailable.")

    BasePlayer = getattr(cs_players, "BasePlayer", None) or getattr(cs_players, "Player", None)
    if BasePlayer is None:
        raise RuntimeError("Could not find BasePlayer/Player in crapssim.players.")

    class ControlPlayer(BasePlayer):  # type: ignore[misc]
        def __init__(self, spec_dict: Dict[str, Any]):
            super().__init__()
            self._spec = spec_dict
            self._state: Dict[str, Any] = {"mode": spec_dict.get("start_mode", "default")}

        def on_comeout(self, table):
            return

        def on_point(self, table, point):
            return

        def on_roll(self, table, roll):
            return

        def on_seven_out(self, table):
            return

        def apply_template(self, table, template: Dict[str, Any]):
            return

        def clear_bets(self, table):
            return

    p = ControlPlayer(spec)
    add_player = getattr(table, "add_player", None)
    if callable(add_player):
        try:
            add_player(p)
        except TypeError:
            add_player(player=p)
    else:
        raise RuntimeError("Legacy attach failed: table has no add_player()")
    return EngineAttachResult(table=table, controller_player=p, meta={"mode": "legacy"})


def attach_engine(spec: Dict[str, Any]) -> EngineAttachResult:
    ok, reason = check_engine_ready()
    if not ok:
        raise RuntimeError(reason or "Could not attach to CrapsSim: engine not installed.")

    if _CsTable is not None:
        try:
            table = _CsTable()
        except TypeError:
            table = _CsTable()  # type: ignore[call-arg]
    else:  # pragma: no cover - defensive fallback
        class _ShimTable:
            def __init__(self):
                self.players = []

            def add_player(self, *a, **k):
                self.players.append(object())

            def add_strategy(self, *a, **k):
                return None

        table = _ShimTable()

    if cs_strategy is not None:
        return _attach_modern(table, spec)
    if _HAS_LEGACY_PLAYERS:
        return _attach_legacy(table, spec)
    raise RuntimeError(
        "Could not attach to CrapsSim. Neither 'crapssim.strategy' (modern) nor 'crapssim.players' (legacy) is available."
    )


class CrapsSimAdapter(EngineAdapter):
    """Concrete adapter that bridges CSC to a CrapsSim installation."""

    def __init__(self) -> None:
        self.table = None
        self.controller_player = None
        self.meta: Dict[str, Any] = {}
        self._attach_result: Optional[EngineAttachResult] = None

    # ----- EngineAdapter interface --------------------------------------------------
    def start_session(self, spec: Dict[str, Any]) -> None:
        result = attach_engine(spec)
        self.table = result.table
        self.controller_player = result.controller_player
        self.meta = dict(result.meta or {})
        self._attach_result = result

    def step_roll(
        self, dice: Optional[Tuple[int, int]] = None, seed: Optional[int] = None
    ) -> Dict[str, Any]:
        if self.table is None:
            raise RuntimeError("start_session() must be called before step_roll().")
        if seed is not None:
            self.set_seed(seed)
        self._drive_one_roll(self.table, dice)
        return self.snapshot_state()

    def apply_action(self, verb: str, args: Dict[str, Any]) -> Dict[str, Any]:
        table = self.table
        if table is None:
            raise RuntimeError("start_session() must be called before apply_action().")

        controller = getattr(table, "controller", None)
        if controller is None:
            players = getattr(table, "players", None)
            controller = players[0] if players else None

        fn = getattr(controller, "apply_action", None)
        if callable(fn):
            try:
                return fn(verb, args)
            except TypeError:
                return fn(verb, **(args or {}))  # type: ignore[misc]
            except Exception as exc:  # pragma: no cover - defensive
                return {"result": "error", "error": str(exc)}

        return {"result": "noop", "applied": verb, "args": dict(args)}

    def snapshot_state(self) -> Dict[str, Any]:
        table = self.table
        if table is None:
            return {
                "bankroll": 0.0,
                "point_on": False,
                "point_value": None,
                "bets": {},
                "hand_id": 0,
                "roll_in_hand": 0,
                "rng_seed": None,
            }

        bankroll = None
        players = getattr(table, "players", None)
        primary = players[0] if players else None
        if primary is not None:
            for attr in ("bankroll", "total_player_cash", "chips", "_bankroll"):
                if hasattr(primary, attr):
                    bankroll = getattr(primary, attr)
                    break

        point = getattr(table, "point", None)
        point_value = None
        if point is not None:
            point_value = point if isinstance(point, int) else getattr(point, "value", getattr(point, "number", None))
        point_on = bool(point_value)

        bets: Dict[str, Any] = {}
        bet_list = getattr(primary, "bets", None)
        if isinstance(bet_list, list):
            for idx, bet in enumerate(bet_list):
                amount = getattr(bet, "amount", None)
                name = getattr(bet, "name", None) or getattr(bet, "__class__", type(bet)).__name__
                bets[str(idx)] = {"name": str(name), "amount": float(amount) if amount is not None else None}

        hand_id = getattr(table, "hand_id", 0)
        roll_in_hand = getattr(table, "roll_in_hand", 0)

        rng_seed = None
        for attr in ("seed", "rng_seed", "_seed"):
            if hasattr(table, attr):
                rng_seed = getattr(table, attr)
                break
        if rng_seed is None:
            dice = getattr(table, "dice", None) or getattr(table, "_dice", None)
            rng_seed = getattr(dice, "seed", None) if dice is not None else None

        return {
            "bankroll": float(bankroll) if bankroll is not None else None,
            "point_on": bool(point_on),
            "point_value": int(point_value) if point_value is not None else None,
            "bets": bets,
            "hand_id": int(hand_id) if hand_id is not None else 0,
            "roll_in_hand": int(roll_in_hand) if roll_in_hand is not None else 0,
            "rng_seed": rng_seed,
        }

    # ----- Back-compat helpers ------------------------------------------------------
    def attach(self, spec: Dict[str, Any]) -> EngineAttachResult:
        self.start_session(spec)
        assert self._attach_result is not None
        return self._attach_result

    @classmethod
    def attach_cls(cls, spec: Dict[str, Any]) -> EngineAttachResult:
        inst = cls()
        return inst.attach(spec)

    def set_seed(self, seed: int | None) -> None:
        if seed is None:
            return
        table = self.table
        if table is None:
            return
        try:
            for meth in ("set_seed", "seed"):
                fn = getattr(table, meth, None)
                if callable(fn):
                    fn(int(seed))
                    return
            for attr_name in ("rng", "random", "prng", "dice", "shooter"):
                obj = getattr(table, attr_name, None)
                if obj is None:
                    continue
                seed_fn = getattr(obj, "seed", None)
                if callable(seed_fn):
                    seed_fn(int(seed))
                    return
            meta = getattr(self, "meta", {}) or {}
            reseed = meta.get("set_seed") if isinstance(meta, dict) else None
            if callable(reseed):
                reseed(int(seed))
        except Exception:  # pragma: no cover - fail open
            return

    def play(self, shooters: int = 1, rolls: int = 3) -> Dict[str, Any]:
        table = self.table
        if table is None:
            return {"shooters": shooters, "rolls": rolls, "status": "noop"}
        for _ in range(max(1, int(rolls))):
            self._drive_one_roll(table, None)
        return {"shooters": int(shooters), "rolls": int(rolls), "status": "ok"}

    # ----- Internal helpers --------------------------------------------------------
    @staticmethod
    def _drive_one_roll(table: Any, dice: Optional[Tuple[int, int]]) -> None:
        if dice is not None:
            process = getattr(table, "process_roll", None) or getattr(table, "on_roll", None)
            if callable(process):
                process(tuple(int(x) for x in dice))
                return

        roll_fn = getattr(table, "roll", None)
        if callable(roll_fn):
            roll_fn()
            return

        play_fn = getattr(table, "play", None)
        if callable(play_fn):
            play_fn(rolls=1)
            return

        run_fn = getattr(table, "run", None)
        if callable(run_fn):
            try:
                run_fn(1)
            except TypeError:
                run_fn(rolls=1)
            return

        try:  # pragma: no cover - last-resort path
            from crapssim.dice import Dice  # type: ignore

            dice_obj = Dice()
            process = getattr(table, "process_roll", None) or getattr(table, "on_roll", None)
            if callable(process):
                outcome = dice if dice is not None else dice_obj.roll()
                process(outcome)
                return
        except Exception:
            pass

        raise RuntimeError("Could not advance roll: no compatible engine hooks found.")


def resolve_engine_adapter() -> Tuple[Optional[Type[EngineAdapter]], Optional[str]]:
    """Return (adapter_cls, reason) for the current environment."""

    ok, reason = check_engine_ready()
    if ok:
        return CrapsSimAdapter, None
    return None, reason

