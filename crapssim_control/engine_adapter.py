"""Adapter contract & action grammar.
See docs/engine_contract.md#effect-schema-10 for the uniform effect_summary schema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
import random
import re
import warnings
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Type, TypedDict

from crapssim_control.config import get_journal_options
from crapssim_control.journal import append_effect_summary_line, reset_group_state
from crapssim_control.transport import EngineTransport, LocalTransport
from crapssim_control.rule_engine import RuleEngine
from crapssim_control.dsl_parser import parse_file, compile_rules

__all__ = [
    "EngineAdapter",
    "NullAdapter",
    "VanillaAdapter",
    "VerbRegistry",
    "PolicyRegistry",
    "Effect",
    "validate_effect_summary",
]


_BOX_NUMBERS = (4, 5, 6, 8, 9, 10)

try:
    import crapssim.bet as cs_bet
except Exception:
    cs_bet = None  # type: ignore


def _mk(cs_cls, *a, **k):
    if not cs_cls:
        return None
    try:
        return cs_cls(*a, **k)
    except TypeError:
        try:
            return cs_cls(*a)
        except Exception:
            return None


def _is_die(n):
    return isinstance(n, int) and 1 <= n <= 6


def _is_box_number(x) -> bool:
    try:
        return int(x) in _BOX_NUMBERS
    except Exception:
        return False


def _reject(code: str, reason: str) -> Dict[str, Any]:
    return {"rejected": True, "code": code, "reason": reason}


_VALUE_ERROR_CODE_SUFFIXES = {
    "invalid_amount": "illegal_amount",
    "invalid_args": "invalid_args",
    "invalid_dice": "illegal_dice",
    "invalid_number": "illegal_number",
    "invalid_increment": "illegal_increment",
}


def _reject_from_value_error(exc: ValueError) -> Dict[str, Any]:
    message = str(exc) or "invalid"
    for suffix, code in _VALUE_ERROR_CODE_SUFFIXES.items():
        if suffix in message:
            return _reject(code, message)
    return _reject("illegal_increment", message)


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


def _normalize_snapshot(table_or_snapshot: Optional[Any], player: Optional[Any] = None) -> Dict[str, Any]:
    """Normalize arbitrary engine snapshots into CSC's canonical shape."""

    def _get_prop_intents(source_player: Optional[Any]) -> List[Mapping[str, Any]]:
        if source_player is None:
            return []
        candidates: List[Any] = []
        try:
            strategy = getattr(source_player, "_strategy", None)
        except Exception:
            strategy = None
        if strategy is not None:
            candidates.append(strategy)
        candidates.append(source_player)
        for candidate in candidates:
            if candidate is None:
                continue
            try:
                intents = getattr(candidate, "_props_intent", None)
            except Exception:
                intents = None
            if intents:
                try:
                    return list(intents)
                except Exception:
                    continue
        try:
            pending = getattr(source_player, "_csc_props_pending", None)
        except Exception:
            pending = None
        if pending:
            try:
                return list(pending)
            except Exception:
                pass
        adapter_ref = getattr(source_player, "_csc_adapter_ref", None)
        if adapter_ref is not None:
            try:
                pending = getattr(adapter_ref, "_props_pending", None)
                if pending:
                    return list(pending)
            except Exception:
                return []
        return []

    if isinstance(table_or_snapshot, Mapping) or table_or_snapshot is None:
        raw_snapshot: Mapping[str, Any] = table_or_snapshot or {}
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
        bet_types: Dict[str, str] = {}
        existing_meta = raw_snapshot.get("bet_types")
        if isinstance(existing_meta, Mapping):
            for key, value in existing_meta.items():
                if isinstance(value, str):
                    bet_types[str(key)] = value

        bets_obj = raw_snapshot.get("bets")
        if isinstance(bets_obj, Mapping):
            for key, value in bets_obj.items():
                amount = value
                name = key
                number = None
                if isinstance(value, Mapping):
                    amount = value.get("amount")
                    name = value.get("name") or key
                    number = value.get("number") or value.get("point")
                try:
                    amount_val = float(amount) if amount is not None else 0.0
                except (TypeError, ValueError):
                    continue

                name_str = str(name)
                key_str = str(key)
                bet_key: Optional[str] = None
                if number is not None and _is_box_number(number):
                    bet_key = str(int(number))
                elif _is_box_number(key_str):
                    bet_key = str(int(key_str))
                else:
                    lower = name_str.lower()
                    digits = re.findall(r"\d+", lower)
                    for token in digits:
                        if _is_box_number(token):
                            bet_key = str(int(token))
                            break
                    if bet_key is None:
                        if "pass" in lower:
                            bet_key = "pass"
                        elif "dont" in lower and "come" in lower and "line" not in lower:
                            bet_key = "dc"

                if bet_key is None:
                    lower_name = name_str.lower()
                    if lower_name == "field":
                        bet_key = "field"
                    elif lower_name == "hardway" and number is not None and _is_box_number(number):
                        bet_key = f"hardway_{int(number)}"
                    else:
                        bet_key = lower_name if name_str else key_str

                bets_norm[bet_key] = bets_norm.get(bet_key, 0.0) + amount_val

                if bet_key in {str(n) for n in _BOX_NUMBERS}:
                    if bet_key not in bet_types:
                        lower_name = name_str.lower()
                        if "buy" in lower_name:
                            bet_types[bet_key] = "buy"
                        elif "lay" in lower_name:
                            bet_types[bet_key] = "lay"
                        elif "place" in lower_name:
                            bet_types[bet_key] = "place"

        for num in _BOX_NUMBERS:
            bets_norm.setdefault(str(num), bets_norm.get(str(num), 0.0))
        bets_norm.setdefault("field", bets_norm.get("field", 0.0))
        for n in (4, 6, 8, 10):
            bets_norm.setdefault(f"hardway_{n}", bets_norm.get(f"hardway_{n}", 0.0))
        for family in ("come", "dc"):
            for n in _BOX_NUMBERS:
                bets_norm.setdefault(f"odds_{family}_{n}", bets_norm.get(f"odds_{family}_{n}", 0.0))

        def _zero_point_map() -> Dict[str, float]:
            return {str(n): 0.0 for n in _BOX_NUMBERS}

        odds_norm = {
            "pass": 0.0,
            "dont_pass": 0.0,
            "come": _zero_point_map(),
            "dc": _zero_point_map(),
        }

        raw_odds = raw_snapshot.get("odds")
        if isinstance(raw_odds, Mapping):
            for key in ("pass", "dont_pass"):
                try:
                    odds_norm[key] = float(raw_odds.get(key, 0.0) or 0.0)  # type: ignore[index]
                except (TypeError, ValueError):
                    odds_norm[key] = 0.0
            for family_key in ("come", "dc"):
                branch = raw_odds.get(family_key)
                if isinstance(branch, Mapping):
                    for num, value in branch.items():
                        if _is_box_number(num):
                            try:
                                odds_norm[family_key][str(int(num))] = float(value or 0.0)
                            except (TypeError, ValueError):
                                continue

        for bet_key, amount in bets_norm.items():
            if not isinstance(bet_key, str):
                continue
            key_lower = bet_key.lower()
            try:
                amt_val = float(amount or 0.0)
            except (TypeError, ValueError):
                continue
            if key_lower == "odds_pass":
                odds_norm["pass"] = amt_val
            elif key_lower == "odds_dont_pass":
                odds_norm["dont_pass"] = amt_val
            elif key_lower.startswith("odds_come_"):
                suffix = bet_key.split("_", 2)[-1]
                if _is_box_number(suffix):
                    odds_norm["come"][str(int(suffix))] = amt_val
            elif key_lower.startswith("odds_dc_"):
                suffix = bet_key.split("_", 2)[-1]
                if _is_box_number(suffix):
                    odds_norm["dc"][str(int(suffix))] = amt_val

        come_flat_raw = raw_snapshot.get("come_flat")
        dc_flat_raw = raw_snapshot.get("dc_flat")

        def _coerce_point_map(obj: Any) -> Dict[str, float]:
            data = _zero_point_map()
            if isinstance(obj, Mapping):
                for key, value in obj.items():
                    if _is_box_number(key):
                        try:
                            data[str(int(key))] = float(value or 0.0)
                        except (TypeError, ValueError):
                            continue
            return data

        come_flat = _coerce_point_map(come_flat_raw)
        dc_flat = _coerce_point_map(dc_flat_raw)

        normalized = {
            "bankroll": bankroll_val,
            "point_on": bool(raw_snapshot.get("point_on", False)) or bool(point_val_norm),
            "point_value": point_val_norm,
            "bets": bets_norm,
            "hand_id": hand_id_norm,
            "roll_in_hand": roll_norm,
            "rng_seed": rng_seed_norm,
            "on_comeout": bool(raw_snapshot.get("on_comeout"))
            if "on_comeout" in raw_snapshot
            else point_val_norm in (None, 0),
            "come_flat": come_flat,
            "dc_flat": dc_flat,
            "odds": odds_norm,
        }

        dice_raw = raw_snapshot.get("dice")
        dice_norm: Optional[Tuple[int, int]] = None
        if isinstance(dice_raw, (list, tuple)) and len(dice_raw) == 2:
            try:
                dice_norm = (int(dice_raw[0]), int(dice_raw[1]))
            except Exception:
                dice_norm = None
        normalized["dice"] = dice_norm

        total_raw = raw_snapshot.get("total")
        try:
            normalized["total"] = int(total_raw) if total_raw is not None else None
        except Exception:
            normalized["total"] = None

        bankroll_after = raw_snapshot.get("bankroll_after")
        try:
            normalized["bankroll_after"] = (
                float(bankroll_after)
                if bankroll_after is not None
                else bankroll_val
            )
        except (TypeError, ValueError):
            normalized["bankroll_after"] = bankroll_val

        travel_events = raw_snapshot.get("travel_events")
        normalized["travel_events"] = (
            {str(k): v for k, v in travel_events.items()}
            if isinstance(travel_events, Mapping)
            else {}
        )

        pso_flag = raw_snapshot.get("pso_flag")
        normalized["pso_flag"] = bool(pso_flag) if pso_flag is not None else False

        if bet_types:
            normalized["bet_types"] = bet_types

        if "levels" in raw_snapshot:
            levels = raw_snapshot.get("levels")
            if isinstance(levels, Mapping):
                normalized["levels"] = {
                    str(k): int(v) for k, v in levels.items() if isinstance(v, (int, float))
                }
        if "last_effect" in raw_snapshot:
            normalized["last_effect"] = raw_snapshot.get("last_effect")

        props_bucket: Dict[str, float] = {}
        for intent in _get_prop_intents(player)[-8:]:
            if not isinstance(intent, Mapping):
                continue
            fam = str(intent.get("prop_family", intent.get("family", "prop")))
            key = fam
            if fam == "hop":
                combo = intent.get("combo", "")
                key = f"hop_{combo}" if combo else "hop"
            try:
                amt = float(intent.get("amount", 0.0) or 0.0)
            except (TypeError, ValueError):
                amt = 0.0
            props_bucket[key] = amt
        normalized["props"] = props_bucket

        dice_pair = normalized.get("dice")
        total_val = normalized.get("total")
        last_roll: Dict[str, Any] = {}
        if isinstance(dice_pair, (list, tuple)) and len(dice_pair) == 2:
            try:
                last_roll["dice"] = (int(dice_pair[0]), int(dice_pair[1]))
            except Exception:
                pass
        if isinstance(total_val, (int, float)):
            try:
                last_roll["total"] = int(total_val)
            except Exception:
                pass
        normalized["last_roll"] = last_roll if last_roll else {}

        return normalized

    table = table_or_snapshot
    if table is None or player is None:
        return {}

    br = None
    for attr in ("bankroll", "chips", "total_player_cash", "_bankroll"):
        if hasattr(player, attr):
            try:
                br = float(getattr(player, attr))
                break
            except Exception:
                continue

    pt = getattr(table, "point", None)
    if pt is not None and not isinstance(pt, (int, type(None))):
        pt = getattr(pt, "value", getattr(pt, "number", None))
    try:
        point_val = int(pt) if pt is not None else None
    except Exception:
        point_val = None
    point_on = bool(point_val and _is_box_number(point_val))

    bets_map: Dict[str, float] = {}
    meta_types: Dict[str, str] = {}
    odds_map = {
        "pass": 0.0,
        "dont_pass": 0.0,
        "come": {str(n): 0.0 for n in _BOX_NUMBERS},
        "dc": {str(n): 0.0 for n in _BOX_NUMBERS},
    }
    come_flat = {str(n): 0.0 for n in _BOX_NUMBERS}
    dc_flat = {str(n): 0.0 for n in _BOX_NUMBERS}
    try:
        bets = getattr(player, "bets", []) or []
        for bet in bets:
            name_raw = getattr(bet, "name", getattr(bet, "type", "") or "")
            name = str(name_raw).lower()
            cls_name = bet.__class__.__name__.lower()
            if not name:
                name = cls_name
            number = getattr(bet, "number", getattr(bet, "point", None))
            try:
                amt = float(getattr(bet, "amount", 0.0) or 0.0)
            except Exception:
                amt = 0.0
            key = None
            bet_kind = None
            if _is_box_number(number):
                n = str(int(number))
                key = n
                if "buy" in name:
                    bet_kind = "buy"
                elif "lay" in name:
                    bet_kind = "lay"
                elif "place" in name:
                    bet_kind = "place"
            elif "dont pass" in name or "dontpass" in cls_name:
                key, bet_kind = "dont_pass", "line"
            elif "pass" in name or "passline" in cls_name:
                key, bet_kind = "pass", "line"
            elif "dont" in name and "come" in name and "line" not in name:
                key, bet_kind = "dc", "dont_come"
            elif "field" in name or cls_name == "field":
                key = "field"
            elif cls_name == "hardway" and _is_box_number(number):
                key = f"hardway_{int(number)}"
            if key:
                bets_map[key] = bets_map.get(key, 0.0) + amt
                if bet_kind and key not in meta_types and key in {str(n) for n in _BOX_NUMBERS}:
                    meta_types[key] = bet_kind
                if key in {str(n) for n in _BOX_NUMBERS} and key not in meta_types:
                    cls_name = bet.__class__.__name__.lower()
                    if "buy" in cls_name:
                        meta_types[key] = "buy"
                    elif "lay" in cls_name:
                        meta_types[key] = "lay"
                    elif "place" in cls_name:
                        meta_types[key] = "place"
            if "come" in name and "dont" not in name and "odds" not in name and _is_box_number(number):
                come_flat[str(int(number))] += amt
            elif "dont come" in name and "odds" not in name and _is_box_number(number):
                dc_flat[str(int(number))] += amt
            elif "odds" in name and "pass" in name and "dont" not in name:
                odds_map["pass"] += amt
            elif "odds" in name and "dont pass" in name:
                odds_map["dont_pass"] += amt
            elif "odds" in name and "come" in name and "dont" not in name and _is_box_number(number):
                odds_map["come"][str(int(number))] += amt
            elif "odds" in name and "dont" in name and _is_box_number(number):
                odds_map["dc"][str(int(number))] += amt
    except Exception:
        pass

    for num in _BOX_NUMBERS:
        bets_map.setdefault(str(num), bets_map.get(str(num), 0.0))
    bets_map.setdefault("pass", bets_map.get("pass", 0.0))
    bets_map.setdefault("dont_pass", bets_map.get("dont_pass", 0.0))

    hand_id = getattr(table, "hand_id", 0)
    try:
        hand_id_norm = int(hand_id)
    except Exception:
        hand_id_norm = 0

    roll_ct = getattr(table, "roll_count", getattr(table, "roll_in_hand", 0))
    try:
        roll_norm = int(roll_ct)
    except Exception:
        roll_norm = 0

    rng_seed = None
    for attr in ("seed", "rng_seed", "_seed"):
        if hasattr(table, attr):
            rng_seed = getattr(table, attr)
            break
    if rng_seed is None:
        dice = getattr(table, "dice", None) or getattr(table, "_dice", None)
        if dice is not None:
            rng_seed = getattr(dice, "seed", None)
    try:
        rng_seed_norm = int(rng_seed) if rng_seed is not None else 0
    except Exception:
        rng_seed_norm = 0

    normalized = {
        "bankroll": float(br) if br is not None else 0.0,
        "point_on": point_on,
        "point_value": point_val if point_val is not None else None,
        "bets": bets_map,
        "bet_types": meta_types,
        "hand_id": hand_id_norm,
        "roll_in_hand": roll_norm,
        "rng_seed": rng_seed_norm,
        "on_comeout": not point_on,
        "come_flat": come_flat,
        "dc_flat": dc_flat,
        "odds": odds_map,
    }

    normalized["bankroll_after"] = normalized.get("bankroll", 0.0)
    normalized["dice"] = None
    normalized["total"] = None
    normalized["travel_events"] = {}
    normalized["pso_flag"] = False

    props_bucket: Dict[str, float] = {}
    for intent in _get_prop_intents(player)[-8:]:
        if not isinstance(intent, Mapping):
            continue
        fam = str(intent.get("prop_family", intent.get("family", "prop")))
        key = fam
        if fam == "hop":
            combo = intent.get("combo", "")
            key = f"hop_{combo}" if combo else "hop"
        try:
            amt = float(intent.get("amount", 0.0) or 0.0)
        except (TypeError, ValueError):
            amt = 0.0
        props_bucket[key] = amt
    normalized["props"] = props_bucket

    ats_keys = ("small", "tall", "all")
    ats_progress: Dict[str, float] = {k: 0.0 for k in ats_keys}
    raw_progress = None
    if player is not None:
        raw_progress = getattr(player, "_ats_progress", None)
        if raw_progress is None:
            adapter_ref = getattr(player, "_csc_adapter_ref", None)
            if adapter_ref is not None:
                raw_progress = getattr(adapter_ref, "_ats_progress", None)
    if raw_progress is None:
        raw_progress = getattr(table, "_ats_progress", None)
    if isinstance(raw_progress, Mapping):
        for key in ats_keys:
            value = raw_progress.get(key, 0)
            try:
                ats_progress[key] = float(value)
            except (TypeError, ValueError):
                ats_progress[key] = 0.0
    for key in ats_keys:
        bets_map[f"ats_{key}"] = ats_progress.get(key, bets_map.get(f"ats_{key}", 0.0))
    normalized["ats_progress"] = {k: ats_progress.get(k, 0.0) for k in ats_keys}

    last_roll: Dict[str, Any] = {}
    normalized["last_roll"] = last_roll

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

    def __init__(self, transport: EngineTransport | None = None):
        self.transport = transport or LocalTransport()
        self._session_started = False
        self.spec: Dict[str, Any] = {}
        self.seed: Optional[int] = None
        self.live_engine: bool = False
        self._engine_adapter: Optional[EngineAdapter] = None
        self._engine_reason: Optional[str] = None
        self._snapshot_cache: Dict[str, Any] = {}
        self._table: Optional[Any] = None
        self._player: Optional[Any] = None
        self._controller: Optional[Any] = None
        self._cs_bet_module: Optional[Any] = None
        self._rng = random.Random()
        self._last_snapshot: Dict[str, Any] = {}
        self._props_intent: List[Dict[str, Any]] = []
        self._props_pending: List[Dict[str, Any]] = []
        self.dsl_trace_enabled: bool = False
        self.journal: Optional[Any] = None

        self._reset_stub_state()
        self._journal_opts: Dict[str, Any] = get_journal_options({})
        self.rule_engine: Optional[RuleEngine] = None

    def load_ruleset(self, text_or_path: str) -> None:
        """Load and compile DSL rules from a file path or raw text."""

        from pathlib import Path

        source = Path(text_or_path)
        if source.exists():
            text = source.read_text(encoding="utf-8")
        else:
            text = text_or_path
        rules = parse_file(text)
        compiled = compile_rules(rules)
        self.rule_engine = RuleEngine(compiled)

    def maybe_eval_rules(
        self, snapshot: Dict[str, Any], trace_enabled: bool = False
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if not self.rule_engine:
            return [], []
        return self.rule_engine.evaluate(snapshot, trace_enabled=trace_enabled)

    def enable_dsl_trace(self, enabled: bool = True) -> None:
        """Enable or disable DSL trace logging."""
        self.dsl_trace_enabled = bool(enabled)

    def perform_handshake(self) -> None:
        """Query engine for version and capabilities, store for manifest export."""

        try:
            ver_info = self.transport.version()
            caps_info = self.transport.capabilities()
            self._engine_info = {
                "engine": ver_info.get("engine", "unknown") if isinstance(ver_info, dict) else "unknown",
                "version": ver_info.get("version", "unknown") if isinstance(ver_info, dict) else "unknown",
                "capabilities": caps_info if isinstance(caps_info, dict) else {},
            }
        except Exception as exc:  # pragma: no cover - defensive handshake guard
            self._engine_info = {"engine": "unknown", "error": str(exc)}

    def get_engine_info(self) -> Dict[str, Any]:
        """Return cached engine handshake info."""

        if not hasattr(self, "_engine_info"):
            self.perform_handshake()
        return getattr(self, "_engine_info", {})

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
        self.bets: Dict[str, float] = {str(n): 0.0 for n in _BOX_NUMBERS}
        self.bets.update({"pass": 0.0, "dont_pass": 0.0, "come": 0.0, "dc": 0.0})
        self.bets.update({"field": 0.0})
        for n in (4, 6, 8, 10):
            self.bets[f"hardway_{n}"] = 0.0
        for side in ("come", "dc"):
            for n in _BOX_NUMBERS:
                self.bets[f"odds_{side}_{n}"] = 0.0
        def _zero_point_map() -> Dict[str, float]:
            return {str(n): 0.0 for n in _BOX_NUMBERS}

        self.come_flat: Dict[str, float] = _zero_point_map()
        self.dc_flat: Dict[str, float] = _zero_point_map()
        self.odds_state: Dict[str, Any] = {
            "pass": 0.0,
            "dont_pass": 0.0,
            "come": _zero_point_map(),
            "dc": _zero_point_map(),
        }
        self.on_comeout: bool = True
        self.box_bet_types: Dict[str, str] = {}
        self.last_effect: Optional[Effect] = None
        self.martingale_levels: Dict[str, int] = {}
        self._props_intent = []
        self._props_pending = []
        base_snapshot = {
            "bankroll": self.bankroll,
            "point_on": False,
            "point_value": None,
            "bets": dict(self.bets),
            "bet_types": dict(self.box_bet_types),
            "hand_id": 0,
            "roll_in_hand": 0,
            "rng_seed": self.seed or 0,
            "levels": dict(self.martingale_levels),
            "last_effect": self.last_effect,
            "on_comeout": self.on_comeout,
            "come_flat": dict(self.come_flat),
            "dc_flat": dict(self.dc_flat),
            "odds": {
                "pass": self.odds_state["pass"],
                "dont_pass": self.odds_state["dont_pass"],
                "come": dict(self.odds_state["come"]),
                "dc": dict(self.odds_state["dc"]),
            },
        }
        self._snapshot_cache = _normalize_snapshot(base_snapshot)
        self._last_snapshot = dict(self._snapshot_cache)
        if self.seed is not None:
            try:
                self._rng.seed(int(self.seed))
            except Exception:
                pass

    def set_seed(self, seed: Optional[int]) -> None:
        coerced = self._coerce_seed(seed)
        self.seed = coerced
        if coerced is not None:
            self._rng.seed(int(coerced))
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
        try:
            self.transport.start_session(spec or {})
        except Exception:
            # Transport failures shouldn't block stub fallback.
            pass
        self._session_started = True
        self.spec = spec or {}
        self._journal_opts = get_journal_options(self.spec)
        reset_group_state()
        run_cfg = self.spec.get("run") if isinstance(self.spec, dict) else {}
        run_seed: Optional[int] = None
        if isinstance(run_cfg, dict):
            run_seed = self._coerce_seed(run_cfg.get("seed"))
        if run_seed is None and isinstance(self.spec, dict):
            run_seed = self._coerce_seed(self.spec.get("seed"))
        if run_seed is not None:
            self.seed = run_seed
        journal_cfg = run_cfg.get("journal") if isinstance(run_cfg, dict) else {}
        if isinstance(journal_cfg, dict):
            self.dsl_trace_enabled = bool(journal_cfg.get("dsl_trace", False))
        else:
            self.dsl_trace_enabled = False
        self._reset_stub_state()
        adapter_cfg = run_cfg.get("adapter") if isinstance(run_cfg, dict) else {}
        live_requested = bool(adapter_cfg.get("live_engine")) if isinstance(adapter_cfg, dict) else False

        self.live_engine = False
        self._engine_adapter = None
        self._engine_reason = None
        self._table = None
        self._player = None
        self._cs_bet_module = None

        if live_requested:
            engine, reason = _try_import_crapssim()
            if engine is not None:
                self._engine_adapter = engine
                self.live_engine = True
                engine.start_session(self.spec)
                self._table = getattr(engine, "table", None)
                self._controller = getattr(engine, "controller_player", None)
                self._player = None
                if self._table is not None:
                    try:
                        players = getattr(self._table, "players", None)
                        if players:
                            self._player = players[0]
                    except Exception:
                        self._player = None
                if self._player is None and self._controller is not None:
                    try:
                        candidate = getattr(self._controller, "player", None)
                        if candidate is not None:
                            self._player = candidate
                    except Exception:
                        pass
                self._clear_prop_intents()
                if self._cs_bet_module is None:
                    try:
                        import crapssim.bet as _cs_bet  # type: ignore

                        self._cs_bet_module = _cs_bet
                    except Exception:
                        self._cs_bet_module = None
                self.set_seed(self.seed)
                snapshot = _normalize_snapshot(engine.snapshot_state())
                self._apply_normalized_snapshot(snapshot)
                return
            self._engine_reason = reason

    def _render_auto_why(
        self, verb: str, args: Dict[str, Any], pre: Dict[str, Any]
    ) -> str:
        try:
            def _amt(value: Any) -> Any:
                raw = value
                if isinstance(raw, dict):
                    raw = raw.get("value", raw.get("amount"))
                try:
                    return int(float(raw))
                except Exception:
                    return raw

            point_on = bool(pre.get("point_on"))
            point = pre.get("point_value")
            if verb == "place_bet":
                number = args.get("number")
                if number is None:
                    target = args.get("target")
                    if isinstance(target, Mapping):
                        number = target.get("bet")
                amount = _amt(args.get("amount"))
                base = f"Placed ${amount} on {number}"
                bets = pre.get("bets") if isinstance(pre.get("bets"), dict) else {}
                existing = bets.get(str(number)) if isinstance(bets, dict) else None
                if point_on and not existing:
                    return f"{base} because point is {point} and no existing place bet."
                return f"{base} per strategy."
            if verb == "set_odds":
                side = args.get("on")
                point_val = args.get("point")
                amount = _amt(args.get("amount"))
                return (
                    f"Set ${amount} {side} odds on {point_val} because flat is established."
                )
            if verb == "cancel_bet":
                family = args.get("family")
                target = args.get("target")
                return f"Removed {family} {target} between rolls per rule."
            if verb == "set_working":
                scope = args.get("scope")
                family = args.get("family")
                mode = "on" if args.get("on", True) else "off"
                return f"Turned {family} {mode} on {scope} by policy."
        except Exception:
            pass
        return f"Requested {verb} with args={args}."

    def _cs_get_player(self):
        try:
            if self._player is not None:
                return self._player
            tbl_players = getattr(self._table, "players", None)
            if tbl_players:
                return tbl_players[0]
        except Exception:
            pass
        return None

    def _cs_add_bet(self, bet_obj) -> bool:
        p = self._cs_get_player()
        fn = getattr(p, "add_bet", None) if p else None
        if callable(fn) and bet_obj is not None:
            try:
                fn(bet_obj)
                return True
            except Exception:
                return False
        return False

    def _add_prop_bet(self, bet_obj) -> bool:
        return self._cs_add_bet(bet_obj)

    def _set_props_intent(self, intents: List[Dict[str, Any]]) -> None:
        normalized: List[Dict[str, Any]] = []
        for item in intents:
            if isinstance(item, Mapping):
                normalized.append({str(k): item[k] for k in item.keys()})
            else:
                try:
                    normalized.append(dict(item))  # type: ignore[arg-type]
                except Exception:
                    continue
        self._props_intent = normalized
        self._props_pending = list(normalized)
        player = self._cs_get_player()
        targets: List[Any] = []
        if player is not None:
            strategy = getattr(player, "_strategy", None)
            if strategy is not None:
                targets.append(strategy)
            targets.append(player)
            try:
                setattr(player, "_csc_adapter_ref", self)
            except Exception:
                pass
        targets.append(self)
        for target in targets:
            if target is None:
                continue
            try:
                setattr(target, "_props_intent", list(normalized))
                setattr(target, "_csc_props_pending", list(normalized))
            except Exception:
                continue

    def _clear_prop_intents(self) -> None:
        self._set_props_intent([])

    def _finalize_prop_cleanup(self, roll_result: Mapping[str, Any]) -> Mapping[str, Any]:
        self._props_intent = []
        self._props_pending = []
        player = self._cs_get_player()
        if player is not None:
            for attr in ("_props_intent", "_csc_props_pending"):
                try:
                    setattr(player, attr, [])
                except Exception:
                    continue
            try:
                setattr(player, "_csc_adapter_ref", self)
            except Exception:
                pass
        snapshot_payload = None
        if isinstance(roll_result, Mapping):
            snapshot_payload = roll_result.get("snapshot")
        if isinstance(snapshot_payload, Mapping):
            if not isinstance(snapshot_payload, dict):
                snapshot_payload = dict(snapshot_payload)
                if isinstance(roll_result, dict):
                    roll_result["snapshot"] = snapshot_payload
            snapshot_payload["props"] = {}
        return roll_result

    def _snap_bankroll(self) -> float:
        snap = _normalize_snapshot(self._table, self._cs_get_player())
        return float(snap.get("bankroll", 0.0))

    def step_roll(
        self, dice: Optional[Tuple[int, int]] = None, seed: Optional[int] = None
    ) -> Dict[str, Any]:
        coerced_seed = self._coerce_seed(seed) if seed is not None else None
        if seed is not None:
            self.set_seed(seed)

        pre_snapshot = self.snapshot_state()
        trace_enabled = bool(getattr(self, "dsl_trace_enabled", False))
        actions, traces = self.maybe_eval_rules(pre_snapshot, trace_enabled)

        for act in actions:
            verb = act.get("verb", "")
            reason = (
                f"{verb} was triggered because WHEN ({act.get('_when', '')}) "
                "evaluated True."
            )
            args = dict(act.get("args", {}))
            args.setdefault("_why", reason)
            self.apply_action(verb, args)

        try:
            self.transport.step(dice, seed)
        except Exception:
            pass

        def _emit_traces() -> None:
            if not (trace_enabled and traces):
                return
            journal_obj = getattr(self, "journal", None)
            if journal_obj is None or not hasattr(journal_obj, "append"):
                return
            for entry in traces:
                journal_obj.append(entry)

        rng = self._rng if coerced_seed is None else random.Random(int(coerced_seed))
        if dice is None:
            d1 = rng.randint(1, 6)
            d2 = rng.randint(1, 6)
            if coerced_seed is None:
                self._rng = rng
        else:
            d1, d2 = dice
        total = int(d1) + int(d2)

        if self.live_engine:
            live_result = self._step_roll_live((int(d1), int(d2)), total)
            if live_result is not None:
                _emit_traces()
                return self._finalize_prop_cleanup(live_result)

        stub_result = self._step_roll_stub((int(d1), int(d2)), total)
        _emit_traces()
        return self._finalize_prop_cleanup(stub_result)

    def _step_roll_live(
        self, dice: Tuple[int, int], total: int
    ) -> Optional[Dict[str, Any]]:
        table = self._table or getattr(self._engine_adapter, "table", None)
        if table is None:
            return None

        player = self._player
        if player is None:
            try:
                players = getattr(table, "players", None)
                if players:
                    player = players[0]
            except Exception:
                player = None
        if player is None:
            controller = self._controller or getattr(self._engine_adapter, "controller_player", None)
            candidate = getattr(controller, "player", None) if controller is not None else None
            if candidate is not None:
                player = candidate
        if player is None:
            return None
        self._player = player

        prev_snapshot = dict(self._last_snapshot or {})
        if not prev_snapshot:
            prev_snapshot = _normalize_snapshot(table, player)

        try:
            if hasattr(table, "roll"):
                table.roll(dice[0], dice[1])
            elif hasattr(table, "step_roll"):
                table.step_roll(dice)
            else:
                return None
        except Exception as exc:  # pragma: no cover - defensive guard
            return {"status": "error", "code": "roll_failed", "reason": str(exc)}

        self._clear_prop_intents()

        post_snapshot = _normalize_snapshot(table, player)
        if not post_snapshot:
            post_snapshot = {}

        post_snapshot["dice"] = dice
        post_snapshot["total"] = total

        travel_events: Dict[str, Any] = {}
        prev_come = prev_snapshot.get("come_flat") or {}
        prev_dc = prev_snapshot.get("dc_flat") or {}
        now_come = post_snapshot.get("come_flat") or {}
        now_dc = post_snapshot.get("dc_flat") or {}
        for num in ("4", "5", "6", "8", "9", "10"):
            try:
                prev_c = float(prev_come.get(num, 0.0) or 0.0)
                now_c = float(now_come.get(num, 0.0) or 0.0)
            except (TypeError, ValueError):
                prev_c, now_c = 0.0, 0.0
            if prev_c <= 0 and now_c > 0:
                travel_events[f"come_{num}"] = "moved"
            try:
                prev_d = float(prev_dc.get(num, 0.0) or 0.0)
                now_d = float(now_dc.get(num, 0.0) or 0.0)
            except (TypeError, ValueError):
                prev_d, now_d = 0.0, 0.0
            if prev_d <= 0 and now_d > 0:
                travel_events[f"dc_{num}"] = "moved"
        post_snapshot["travel_events"] = travel_events

        pre_point = prev_snapshot.get("point_value")
        pso = bool(pre_point and int(pre_point) in _BOX_NUMBERS and total == 7)
        post_snapshot["pso_flag"] = pso

        prev_hand = int(prev_snapshot.get("hand_id", 0) or 0)
        prev_roll = int(prev_snapshot.get("roll_in_hand", 0) or 0)
        post_hand = int(post_snapshot.get("hand_id", prev_hand) or prev_hand)
        if post_hand == prev_hand and pso:
            post_hand = prev_hand + 1
        if post_hand != prev_hand:
            roll_in_hand = 1
        else:
            roll_in_hand = prev_roll + 1
        post_snapshot["hand_id"] = post_hand
        post_snapshot["roll_in_hand"] = roll_in_hand

        bankroll_val = None
        for attr in ("bankroll", "chips", "total_player_cash", "_bankroll"):
            if hasattr(player, attr):
                try:
                    bankroll_val = float(getattr(player, attr))
                    break
                except Exception:
                    continue
        post_snapshot["bankroll_after"] = bankroll_val if bankroll_val is not None else post_snapshot.get("bankroll", 0.0)

        if pso:
            post_snapshot["point_value"] = None
            post_snapshot["point_on"] = False
            post_snapshot["on_comeout"] = True

        self._apply_normalized_snapshot(post_snapshot)
        self._last_snapshot = dict(post_snapshot)

        return {
            "status": "ok",
            "dice": dice,
            "total": total,
            "snapshot": post_snapshot,
            "travel": travel_events,
            "pso": pso,
        }

    def _step_roll_stub(
        self, dice: Tuple[int, int], total: int
    ) -> Dict[str, Any]:
        prev_snapshot = dict(self._snapshot_cache or self._last_snapshot or {})
        if not prev_snapshot:
            prev_snapshot = dict(self._last_snapshot or {})
        if not prev_snapshot:
            prev_snapshot = {
                "bankroll": self.bankroll,
                "point_on": False,
                "point_value": None,
                "hand_id": 0,
                "roll_in_hand": 0,
                "come_flat": {str(n): 0.0 for n in _BOX_NUMBERS},
                "dc_flat": {str(n): 0.0 for n in _BOX_NUMBERS},
                "travel_events": {},
            }

        post_snapshot = dict(prev_snapshot)
        post_snapshot["dice"] = dice
        post_snapshot["total"] = total

        pre_point = prev_snapshot.get("point_value")
        point_val = int(pre_point) if pre_point not in (None, "", 0) else None
        pso = bool(point_val and total == 7)
        if point_val is None and total in _BOX_NUMBERS:
            post_snapshot["point_value"] = total
            post_snapshot["point_on"] = True
            post_snapshot["on_comeout"] = False
        elif point_val is not None:
            if total == point_val:
                post_snapshot["point_value"] = None
                post_snapshot["point_on"] = False
                post_snapshot["on_comeout"] = True
            elif total == 7:
                post_snapshot["point_value"] = None
                post_snapshot["point_on"] = False
                post_snapshot["on_comeout"] = True

        prev_hand = int(prev_snapshot.get("hand_id", 0) or 0)
        prev_roll = int(prev_snapshot.get("roll_in_hand", 0) or 0)
        if pso or (point_val is not None and total in (point_val, 7)):
            hand_id = prev_hand + 1
            roll_in_hand = 1
        else:
            hand_id = prev_hand
            roll_in_hand = prev_roll + 1 if prev_roll >= 0 else 1
        post_snapshot["hand_id"] = hand_id
        post_snapshot["roll_in_hand"] = roll_in_hand

        post_snapshot["pso_flag"] = pso
        post_snapshot["travel_events"] = {}
        post_snapshot["bankroll_after"] = float(self.bankroll)
        post_snapshot["bankroll"] = float(self.bankroll)

        self._apply_normalized_snapshot(post_snapshot)

        return {
            "status": "ok",
            "dice": dice,
            "total": total,
            "snapshot": post_snapshot,
            "travel": {},
            "pso": pso,
        }

    def apply_action(self, verb: str, args: Dict[str, Any]) -> Dict[str, Any]:
        global _DEPRECATION_EMITTED
        args = dict(args or {})
        group_id = args.pop("_why_group", None)
        why = args.pop("_why", None)
        journal_opts = self._journal_opts or {}
        pre_snapshot: Dict[str, Any] = {}
        if journal_opts.get("explain"):
            try:
                pre_snapshot = self.snapshot_state()
            except Exception:
                pre_snapshot = {}
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

        try:
            self.transport.apply(verb, args or {})
        except Exception:
            pass

        engine_verbs = {
            "press",
            "regress",
            "place_bet",
            "buy_bet",
            "lay_bet",
            "take_down",
            "move_bet",
            "line_bet",
            "come_bet",
            "dont_come_bet",
            "set_odds",
            "take_odds",
            "remove_line",
            "remove_come",
            "remove_dont_come",
            "field_bet",
            "hardway_bet",
            "any7_bet",
            "anycraps_bet",
            "yo_bet",
            "craps2_bet",
            "craps3_bet",
            "craps12_bet",
            "ce_bet",
            "hop_bet",
            "ats_all_bet",
            "ats_small_bet",
            "ats_tall_bet",
        }
        if self.live_engine and self._engine_adapter is not None and verb in engine_verbs:
            try:
                effect = self._apply_engine_action(verb, args or {})
                self.last_effect = effect
                return effect
            except Exception:  # pragma: no cover - fail open to stub
                warnings.warn(
                    f"live_engine_{verb}_failed:fallback_to_stub", RuntimeWarning
                )

        try:
            handler = VerbRegistry.get(verb)
        except KeyError as exc:
            return _reject("unsupported", str(exc))

        try:
            effect = handler(self._effect_context(), args or {})
        except ValueError as exc:
            return _reject_from_value_error(exc)
        except AttributeError as exc:
            return _reject("unsupported", str(exc))
        except Exception as exc:
            return _reject("engine_error", str(exc))

        if isinstance(effect, Mapping) and effect.get("rejected"):
            effect_out = dict(effect)
            if journal_opts.get("explain"):
                why_text = why or self._render_auto_why(verb, args, pre_snapshot)
                effect_out["_why"] = why_text
                if group_id:
                    effect_out["_why_group"] = group_id
            self.last_effect = effect_out  # type: ignore[assignment]
            return effect_out

        try:
            self._apply_effect(effect)
        except ValueError as exc:
            return _reject_from_value_error(exc)
        except AttributeError as exc:
            return _reject("unsupported", str(exc))
        except Exception as exc:
            return _reject("engine_error", str(exc))

        effect_out = dict(effect)
        if journal_opts.get("explain"):
            why_text = why or self._render_auto_why(verb, args, pre_snapshot)
            effect_out["_why"] = why_text
            if group_id:
                effect_out["_why_group"] = group_id
        self.last_effect = effect_out
        return effect_out

    def apply_actions(
        self,
        actions: List[Dict[str, Any]],
        *,
        why: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        grouping = str(self._journal_opts.get("explain_grouping", "first_only"))
        aggregate = grouping == "aggregate_line"
        explain_enabled = bool(self._journal_opts.get("explain"))
        resolved_group = group_id or f"grp-{int(datetime.utcnow().timestamp())}"
        results: List[Dict[str, Any]] = []
        auto = why is None
        pre_snapshot: Dict[str, Any] = {}
        if explain_enabled:
            try:
                pre_snapshot = self.snapshot_state()
            except Exception:
                pre_snapshot = {}
        for idx, action in enumerate(actions):
            verb = action.get("verb")
            args = dict(action.get("args", {}))
            if verb in {"place_bet", "buy_bet", "lay_bet"}:
                number = args.pop("number", None)
                if number is not None:
                    target = dict(args.get("target") or {})
                    target.setdefault("bet", number)
                    args["target"] = target
                amount_val = args.get("amount")
                if not isinstance(amount_val, Mapping):
                    if amount_val is None:
                        args["amount"] = {}
                    else:
                        args["amount"] = {"value": amount_val}
            if explain_enabled:
                args["_why_group"] = resolved_group
                if not aggregate:
                    if auto and why is None and verb is not None:
                        why = self._render_auto_why(verb, args, pre_snapshot)
                    if idx == 0 and why is not None:
                        args["_why"] = why
            result = self.apply_action(verb or "", args)
            results.append(result)
            if explain_enabled:
                append_effect_summary_line(
                    result,
                    path=None,
                    explain_opts=self._journal_opts,
                )
        if explain_enabled and aggregate:
            verbs = [action.get("verb") for action in actions]
            why_text = why or f"Executed {', '.join(v for v in verbs if v)} by strategy policy."
            synthetic = {
                "event": "group_explain",
                "verbs": verbs,
                "_why": why_text,
                "_why_group": resolved_group,
            }
            append_effect_summary_line(
                synthetic,
                path=None,
                explain_opts=self._journal_opts,
            )
        return results

    def _apply_engine_action(self, verb: str, args: Dict[str, Any]) -> Effect:
        if not self.live_engine or self._engine_adapter is None:
            raise RuntimeError("engine_action_unavailable")

        engine = self._engine_adapter

        if verb in {"press", "regress"}:
            action_args = args or {}
            before = _normalize_snapshot(engine.snapshot_state())
            result = engine.apply_action(verb, action_args)
            after = _normalize_snapshot(engine.snapshot_state())
            if isinstance(result, Mapping) and result.get("schema") == "1.0":
                effect = result  # type: ignore[assignment]
            else:
                effect = self._effect_from_snapshot_delta(verb, action_args, before, after)
            self._apply_normalized_snapshot(after)
            return effect

        table = self._table or getattr(engine, "table", None)
        player = self._player
        controller = self._controller or getattr(engine, "controller_player", None)
        if player is None and table is not None:
            try:
                players = getattr(table, "players", None)
                if players:
                    player = players[0]
            except Exception:
                player = None
        if player is None and controller is not None:
            try:
                candidate = getattr(controller, "player", None)
                if candidate is not None:
                    player = candidate
            except Exception:
                player = None
        self._table = table
        self._player = player
        self._controller = controller

        player = self._cs_get_player()
        self._player = player

        cs_bet = self._cs_bet_module
        if cs_bet is None:
            try:
                import crapssim.bet as _cs_bet  # type: ignore

                cs_bet = _cs_bet
            except Exception:
                cs_bet = None
            self._cs_bet_module = cs_bet

        if player is None or table is None or cs_bet is None:
            raise RuntimeError("engine_handles_unavailable")

        target = (args.get("target") or {}) if isinstance(args, Mapping) else {}
        amount = (args.get("amount") or {}) if isinstance(args, Mapping) else {}
        selector = list(target.get("selector") or []) if isinstance(target, Mapping) else []
        bet_key = target.get("bet") if isinstance(target, Mapping) else None
        if bet_key:
            selector.append(bet_key)
        keys = [str(int(k)) for k in selector if _is_box_number(k)]

        bankroll_delta = 0.0
        bets_delta: Dict[str, str] = {}
        extra_effect: Dict[str, Any] = {}

        Place = getattr(cs_bet, "Place", None)
        Buy = getattr(cs_bet, "Buy", None)
        Lay = getattr(cs_bet, "Lay", None)

        def _iter_player_bets():
            bets = getattr(player, "bets", []) or []
            for b in bets:
                number = getattr(b, "number", getattr(b, "point", None))
                try:
                    num_val = int(number) if number is not None else None
                except Exception:
                    num_val = None
                try:
                    amt_val = float(getattr(b, "amount", 0.0) or 0.0)
                except Exception:
                    amt_val = 0.0
                name = str(getattr(b, "name", getattr(b, "type", "") or "")).lower()
                yield b, num_val, amt_val, name

        def _add_bet(bet_obj) -> bool:
            add_fn = getattr(player, "add_bet", None)
            if callable(add_fn) and bet_obj is not None:
                try:
                    add_fn(bet_obj)
                    try:
                        amt = float(getattr(bet_obj, "amount", 0.0) or 0.0)
                    except Exception:
                        amt = 0.0
                    nonlocal bankroll_delta
                    bankroll_delta -= amt
                    return True
                except Exception:
                    return False
            return False

        def _remove_bet_object(bet_obj, number: Optional[int] = None) -> bool:
            remove_methods = ("remove_bet", "take_bet", "take_down", "clear_bet")
            for name in remove_methods:
                fn = getattr(player, name, None)
                if callable(fn):
                    try:
                        if name == "remove_bet":
                            fn(bet_obj)
                        else:
                            if number is None:
                                fn()
                            else:
                                fn(number)
                        return True
                    except Exception:
                        continue
            bet_methods = ("take_down", "remove", "clear")
            for name in bet_methods:
                fn = getattr(bet_obj, name, None)
                if callable(fn):
                    try:
                        fn()
                        return True
                    except Exception:
                        continue
            bets_list = getattr(player, "bets", None)
            if isinstance(bets_list, list) and bet_obj in bets_list:
                try:
                    bets_list.remove(bet_obj)
                    return True
                except Exception:
                    return False
            return False

        def _pop_bet(number: int):
            for bet_obj, num_val, amt_val, name in _iter_player_bets():
                if num_val == number:
                    if _remove_bet_object(bet_obj, number):
                        return bet_obj, amt_val, name
                    break
            return None, 0.0, ""

        def _make_bet(kind: str, number: int, amt: float):
            bet_obj = None
            if kind == "buy" and callable(Buy):
                for kwargs in ({"number": number, "amount": amt}, {"amount": amt, "number": number}):
                    try:
                        return Buy(**kwargs)
                    except Exception:
                        continue
                for args in ((number, amt),):
                    try:
                        return Buy(*args)
                    except Exception:
                        continue
            elif kind == "lay" and callable(Lay):
                for kwargs in ({"number": number, "amount": amt}, {"amount": amt, "number": number}):
                    try:
                        return Lay(**kwargs)
                    except Exception:
                        continue
                for args in ((number, amt),):
                    try:
                        return Lay(*args)
                    except Exception:
                        continue
            elif callable(Place):
                for kwargs in ({"number": number, "amount": amt}, {"amount": amt, "number": number}):
                    try:
                        return Place(**kwargs)
                    except Exception:
                        continue
                for args in ((number, amt),):
                    try:
                        return Place(*args)
                    except Exception:
                        continue
            return bet_obj

        if verb in ("place_bet", "buy_bet", "lay_bet"):
            incr = float(amount.get("value", 0.0)) if isinstance(amount, Mapping) else 0.0
            if incr <= 0:
                raise ValueError(f"{verb}_invalid_amount")
            kind = {"place_bet": "place", "buy_bet": "buy", "lay_bet": "lay"}[verb]
            for k in keys:
                n = int(k)
                bet_obj = _make_bet(kind, n, incr)
                if bet_obj and _add_bet(bet_obj):
                    bets_delta[k] = f"+{int(incr)}"

        elif verb == "take_down":
            for k in keys:
                n = int(k)
                bet_obj, amt, _ = _pop_bet(n)
                if bet_obj is not None or amt > 0:
                    bankroll_delta += amt
                    bets_delta[k] = f"-{int(amt)}"

        elif verb == "move_bet":
            src = str(target.get("from", "")) if isinstance(target, Mapping) else ""
            dst = str(target.get("to", "")) if isinstance(target, Mapping) else ""
            if not (_is_box_number(src) and _is_box_number(dst)):
                raise ValueError("move_bet_invalid_args")
            n_src = int(src)
            bet_obj, amt, name = _pop_bet(n_src)
            if amt > 0:
                bankroll_delta += amt
                bets_delta[src] = f"-{int(amt)}"
                kind = "place"
                if "buy" in name:
                    kind = "buy"
                elif "lay" in name:
                    kind = "lay"
                n_dst = int(dst)
                new_bet = _make_bet(kind, n_dst, amt)
                if new_bet and _add_bet(new_bet):
                    bets_delta[dst] = f"+{int(amt)}"

        elif verb == "line_bet":
            side = (args.get("side") or target.get("side") or "pass")
            amt = float((args.get("amount") or {}).get("value", 0.0))
            bankroll_before = self._snap_bankroll()
            PL = getattr(cs_bet, "PassLine", None)
            DPL = getattr(cs_bet, "DontPass", None)
            bet_obj = None
            if side == "pass" and callable(PL):
                try:
                    bet_obj = PL(amount=amt)
                except Exception:
                    try:
                        bet_obj = PL(amt)
                    except Exception:
                        bet_obj = None
            elif side in ("dont_pass", "dp") and callable(DPL):
                try:
                    bet_obj = DPL(amount=amt)
                except Exception:
                    try:
                        bet_obj = DPL(amt)
                    except Exception:
                        bet_obj = None
            if bet_obj and self._cs_add_bet(bet_obj):
                key = "pass" if side == "pass" else "dont_pass"
                bets_delta[key] = f"+{int(amt)}"
            bankroll_after = self._snap_bankroll()
            bankroll_delta += (bankroll_after - bankroll_before)

        elif verb in ("come_bet", "dont_come_bet"):
            amt = float((args.get("amount") or {}).get("value", 0.0))
            bankroll_before = self._snap_bankroll()
            Come = getattr(cs_bet, "Come", None)
            DontCome = getattr(cs_bet, "DontCome", None)
            bet_obj = None
            if verb == "come_bet" and callable(Come):
                try:
                    bet_obj = Come(amount=amt)
                except Exception:
                    try:
                        bet_obj = Come(amt)
                    except Exception:
                        bet_obj = None
            elif verb == "dont_come_bet" and callable(DontCome):
                try:
                    bet_obj = DontCome(amount=amt)
                except Exception:
                    try:
                        bet_obj = DontCome(amt)
                    except Exception:
                        bet_obj = None
            if bet_obj and self._cs_add_bet(bet_obj):
                bets_delta["come" if verb == "come_bet" else "dc"] = f"+{int(amt)}"
            bankroll_after = self._snap_bankroll()
            bankroll_delta += (bankroll_after - bankroll_before)

        elif verb in ("set_odds", "take_odds"):
            on_raw = (
                args.get("on")
                or target.get("on")
                or args.get("side")
                or target.get("side")
                or "pass"
            )
            on = str(on_raw).lower() if isinstance(on_raw, str) else "pass"
            pt = (
                target.get("point")
                or args.get("point")
                or target.get("number")
                or args.get("number")
            )
            amount_arg = args.get("amount")
            if isinstance(amount_arg, Mapping):
                amt_val = amount_arg.get("value", amount_arg.get("amount", 0.0))
            else:
                amt_val = amount_arg
            try:
                amt = float(amt_val or 0.0)
            except (TypeError, ValueError):
                amt = 0.0
            amt_value = float(amt)
            direction = +1 if verb == "set_odds" else -1
            bankroll_before = self._snap_bankroll()

            pass_cls = getattr(cs_bet, "PassLine", None)
            dont_pass_cls = getattr(cs_bet, "DontPass", None)
            come_cls = getattr(cs_bet, "Come", None)
            dont_come_cls = getattr(cs_bet, "DontCome", None)
            OddsPass = getattr(cs_bet, "OddsPass", None)
            OddsDontPass = getattr(cs_bet, "OddsDontPass", None)
            OddsCome = getattr(cs_bet, "OddsCome", None)
            OddsDontCome = getattr(cs_bet, "OddsDontCome", None)
            OddsGeneric = getattr(cs_bet, "Odds", None)

            if not any(
                callable(cls)
                for cls in (OddsPass, OddsDontPass, OddsCome, OddsDontCome, OddsGeneric)
            ):
                raise RuntimeError("engine_odds_unavailable")

            table_point = getattr(table, "point", None)
            if table_point is not None and not isinstance(table_point, (int, type(None))):
                table_point = getattr(table_point, "value", getattr(table_point, "number", None))

            point_spec = int(pt) if _is_box_number(pt) else None

            placed = False
            removed_total = 0.0

            def _make_odds_bet(base_type, number, amount):
                bet_obj = None
                if base_type is pass_cls and callable(OddsPass):
                    try:
                        bet_obj = OddsPass(amount=amount)
                    except Exception:
                        try:
                            bet_obj = OddsPass(amount)
                        except Exception:
                            bet_obj = None
                elif base_type is dont_pass_cls and callable(OddsDontPass):
                    try:
                        bet_obj = OddsDontPass(amount=amount)
                    except Exception:
                        try:
                            bet_obj = OddsDontPass(amount)
                        except Exception:
                            bet_obj = None
                elif base_type is come_cls and callable(OddsCome):
                    try:
                        bet_obj = OddsCome(number=number, amount=amount)
                    except Exception:
                        try:
                            bet_obj = OddsCome(number, amount)
                        except Exception:
                            bet_obj = None
                elif base_type is dont_come_cls and callable(OddsDontCome):
                    try:
                        bet_obj = OddsDontCome(number=number, amount=amount)
                    except Exception:
                        try:
                            bet_obj = OddsDontCome(number, amount)
                        except Exception:
                            bet_obj = None
                if bet_obj is None and callable(OddsGeneric) and base_type and number is not None:
                    for args_variant in ((base_type, number, amount),):
                        try:
                            bet_obj = OddsGeneric(*args_variant)
                            break
                        except Exception:
                            bet_obj = None
                    if bet_obj is None:
                        for kwargs in ({"base_type": base_type, "number": number, "amount": amount}, {"base_type": base_type, "point": number, "amount": amount}):
                            try:
                                bet_obj = OddsGeneric(**kwargs)
                                break
                            except Exception:
                                bet_obj = None
                return bet_obj

            def _readd_leftover(base_type, number, amount):
                if amount <= 0 or number is None:
                    return
                bet_obj = _make_odds_bet(base_type, number, amount)
                if bet_obj is not None:
                    self._cs_add_bet(bet_obj)

            try:
                p = self._cs_get_player()
                if on in ("pass", "dp", "dont_pass"):
                    base_type = pass_cls if on == "pass" else dont_pass_cls
                    point_val = point_spec
                    if point_val is None and _is_box_number(table_point):
                        point_val = int(table_point)
                    removed_total = 0.0
                    if direction > 0:
                        bet_obj = _make_odds_bet(base_type, point_val, amt) if point_val is not None else None
                        placed = self._cs_add_bet(bet_obj) if bet_obj is not None else False
                    else:
                        odds_type = OddsGeneric
                        remaining = amt
                        for bet_obj, num_val, amt_val, _ in list(_iter_player_bets()):
                            if odds_type is not None and isinstance(bet_obj, odds_type):
                                base = getattr(bet_obj, "base_type", None)
                                target_num = getattr(bet_obj, "number", getattr(bet_obj, "point", None))
                                if base is base_type and (point_val is None or target_num == point_val):
                                    take = min(remaining, amt_val)
                                    if take <= 0:
                                        continue
                                    leftover = max(0.0, amt_val - take)
                                    if _remove_bet_object(bet_obj, num_val):
                                        removed_total += take
                                        if leftover > 0:
                                            _readd_leftover(base_type, target_num, leftover)
                                        remaining -= take
                                    if remaining <= 0:
                                        break
                    if direction > 0 and placed:
                        key = "dont_pass" if on in ("dp", "dont_pass") else "pass"
                        bets_delta[f"odds_{key}"] = f"+{int(amt_value)}"
                    elif direction < 0 and removed_total > 0:
                        key = "dont_pass" if on in ("dp", "dont_pass") else "pass"
                        bets_delta[f"odds_{key}"] = f"-{int(removed_total)}"
                elif on in ("come", "dc"):
                    base_type = come_cls if on == "come" else dont_come_cls
                    point_val = point_spec
                    if base_type and point_val is not None:
                        removed_total = 0.0
                        if direction > 0:
                            bet_obj = _make_odds_bet(base_type, point_val, amt)
                            placed = self._cs_add_bet(bet_obj) if bet_obj is not None else False
                            if placed:
                                fam = "dc" if on == "dc" else "come"
                                bets_delta[f"odds_{fam}_{point_val}"] = f"+{int(amt_value)}"
                        else:
                            odds_type = OddsGeneric
                            remaining = amt
                            for bet_obj, num_val, amt_val, _ in list(_iter_player_bets()):
                                if odds_type is not None and isinstance(bet_obj, odds_type):
                                    base = getattr(bet_obj, "base_type", None)
                                    target_num = getattr(bet_obj, "number", getattr(bet_obj, "point", None))
                                    if base is base_type and target_num == point_val:
                                        take = min(remaining, amt_val)
                                        if take <= 0:
                                            continue
                                        leftover = max(0.0, amt_val - take)
                                        if _remove_bet_object(bet_obj, num_val):
                                            removed_total += take
                                            if leftover > 0:
                                                _readd_leftover(base_type, target_num, leftover)
                                            remaining -= take
                                        if remaining <= 0:
                                            break
                            if removed_total > 0:
                                fam = "dc" if on == "dc" else "come"
                                bets_delta[f"odds_{fam}_{point_val}"] = f"-{int(removed_total)}"
            except Exception:
                placed = False

            bankroll_after = self._snap_bankroll()
            bankroll_delta += (bankroll_after - bankroll_before)

            if amt_value > 0 and not bets_delta:
                raise RuntimeError("engine_odds_unavailable")

        elif verb == "field_bet":
            amount_arg = args.get("amount")
            try:
                amount_val = float(amount_arg if not isinstance(amount_arg, Mapping) else amount_arg.get("value", amount_arg.get("amount", 0.0)))
            except (TypeError, ValueError):
                amount_val = 0.0
            Field = getattr(cs_bet, "Field", None)
            placed = False
            bankroll_before = self._snap_bankroll()
            bet_obj = None
            if callable(Field) and amount_val > 0:
                for ctor_args in (
                    {"amount": amount_val},
                    (amount_val,),
                ):
                    try:
                        if isinstance(ctor_args, dict):
                            bet_obj = Field(**ctor_args)
                        else:
                            bet_obj = Field(*ctor_args)
                        break
                    except Exception:
                        bet_obj = None
            if bet_obj and self._cs_add_bet(bet_obj):
                bets_delta["field"] = f"+{int(amount_val)}"
                placed = True
            bankroll_after = self._snap_bankroll()
            bankroll_delta += (bankroll_after - bankroll_before)
            if amount_val > 0 and not placed:
                raise RuntimeError("engine_field_unavailable")

        elif verb == "hardway_bet":
            number_raw = args.get("number")
            try:
                number_val = int(number_raw)
            except (TypeError, ValueError):
                number_val = 0
            amount_arg = args.get("amount")
            try:
                amount_val = float(amount_arg if not isinstance(amount_arg, Mapping) else amount_arg.get("value", amount_arg.get("amount", 0.0)))
            except (TypeError, ValueError):
                amount_val = 0.0
            HardWay = getattr(cs_bet, "HardWay", None)
            placed = False
            bankroll_before = self._snap_bankroll()
            bet_obj = None
            if callable(HardWay) and number_val in (4, 6, 8, 10) and amount_val > 0:
                for ctor in (
                    {"number": number_val, "amount": amount_val},
                    (number_val, amount_val),
                ):
                    try:
                        if isinstance(ctor, dict):
                            bet_obj = HardWay(**ctor)
                        else:
                            bet_obj = HardWay(*ctor)
                        break
                    except Exception:
                        bet_obj = None
            if bet_obj and self._cs_add_bet(bet_obj):
                bets_delta[f"hardway_{number_val}"] = f"+{int(amount_val)}"
                placed = True
            bankroll_after = self._snap_bankroll()
            bankroll_delta += (bankroll_after - bankroll_before)
            if amount_val > 0 and number_val in (4, 6, 8, 10) and not placed:
                raise RuntimeError("engine_hardway_unavailable")

        elif verb in (
            "any7_bet",
            "anycraps_bet",
            "yo_bet",
            "craps2_bet",
            "craps3_bet",
            "craps12_bet",
            "ce_bet",
            "hop_bet",
        ):
            amt_arg = args.get("amount") if isinstance(args, Mapping) else {}
            if isinstance(amt_arg, Mapping):
                amt_val = amt_arg.get("value", amt_arg.get("amount", 0.0))
            else:
                amt_val = amt_arg
            try:
                amount = float(amt_val or 0.0)
            except (TypeError, ValueError):
                amount = 0.0
            if amount <= 0:
                raise ValueError("prop_bet_invalid_amount")

            bankroll_before = self._snap_bankroll()
            placed = False
            meta_note: Dict[str, Any] = {}
            bet_obj = None

            if verb == "any7_bet":
                bet_obj = _mk(getattr(cs_bet, "Any7", None), amount=amount) or _mk(getattr(cs_bet, "Any7", None), amount)
                meta_note = {"prop_family": "any7"}
            elif verb == "anycraps_bet":
                bet_obj = _mk(getattr(cs_bet, "AnyCraps", None), amount=amount) or _mk(getattr(cs_bet, "AnyCraps", None), amount)
                meta_note = {"prop_family": "any_craps"}
            elif verb == "yo_bet":
                bet_obj = _mk(getattr(cs_bet, "Yo", None), amount=amount) or _mk(getattr(cs_bet, "Yo", None), amount)
                meta_note = {"prop_family": "yo"}
            elif verb == "craps2_bet":
                bet_obj = _mk(getattr(cs_bet, "Two", None), amount=amount) or _mk(getattr(cs_bet, "Two", None), amount)
                meta_note = {"prop_family": "two"}
            elif verb == "craps3_bet":
                bet_obj = _mk(getattr(cs_bet, "Three", None), amount=amount) or _mk(getattr(cs_bet, "Three", None), amount)
                meta_note = {"prop_family": "three"}
            elif verb == "craps12_bet":
                bet_obj = _mk(getattr(cs_bet, "Boxcars", None), amount=amount) or _mk(getattr(cs_bet, "Boxcars", None), amount)
                meta_note = {"prop_family": "twelve"}
            elif verb == "ce_bet":
                bet_obj = _mk(getattr(cs_bet, "CAndE", None), amount=amount) or _mk(getattr(cs_bet, "CAndE", None), amount)
                meta_note = {"prop_family": "c_and_e"}
            elif verb == "hop_bet":
                d1_raw = args.get("d1", args.get("die1", 0))
                d2_raw = args.get("d2", args.get("die2", 0))
                try:
                    d1 = int(d1_raw)
                    d2 = int(d2_raw)
                except (TypeError, ValueError):
                    d1, d2 = 0, 0
                if not (_is_die(d1) and _is_die(d2)):
                    raise ValueError("prop_bet_invalid_dice")
                hop_cls = getattr(cs_bet, "Hop", None)
                bet_obj = _mk(hop_cls, result=(d1, d2), amount=amount) or _mk(hop_cls, (d1, d2), amount)
                meta_note = {"prop_family": "hop", "combo": f"{d1}-{d2}"}

            if bet_obj and self._add_prop_bet(bet_obj):
                placed = True

            bankroll_after = self._snap_bankroll()
            bankroll_delta += float(bankroll_after - bankroll_before)

            if not placed:
                raise RuntimeError(f"engine_prop_unavailable:{verb}")

            intent_entry: Dict[str, Any] = {"verb": verb, "amount": float(amount), **meta_note}
            intents_list = list(getattr(self, "_props_intent", []))
            intents_list.append(intent_entry)
            self._set_props_intent(intents_list)

            prop_key = meta_note.get("prop_family", "prop")
            if prop_key == "hop":
                combo = meta_note.get("combo", "")
                prop_key = f"hop_{combo}" if combo else "hop"
            bets_delta[prop_key] = f"+{int(amount)}"

            extra_effect = {"one_roll": True, "meta": meta_note, "bets_delta": dict(bets_delta)}

        elif verb in ("ats_all_bet", "ats_small_bet", "ats_tall_bet"):
            amt_arg = args.get("amount") if isinstance(args, Mapping) else args
            if isinstance(amt_arg, Mapping):
                amt_val = amt_arg.get("value", amt_arg.get("amount", 0.0))
            else:
                amt_val = amt_arg
            try:
                amount = float(amt_val or 0.0)
            except (TypeError, ValueError):
                amount = 0.0

            if amount <= 0:
                raise ValueError("ats_bet_invalid_amount")

            bankroll_before = self._snap_bankroll()

            AllCls = getattr(cs_bet, "ATSAll", None) or getattr(cs_bet, "All", None)
            SmallCls = getattr(cs_bet, "ATSSmall", None) or getattr(cs_bet, "Small", None)
            TallCls = getattr(cs_bet, "ATSTall", None) or getattr(cs_bet, "Tall", None)

            ats_mapping = {
                "ats_all_bet": AllCls,
                "ats_small_bet": SmallCls,
                "ats_tall_bet": TallCls,
            }
            bet_ctor = ats_mapping.get(verb)
            bet_obj = None
            placed = False
            if callable(bet_ctor):
                try:
                    bet_obj = bet_ctor(amount=amount)
                except TypeError:
                    try:
                        bet_obj = bet_ctor(amount)
                    except Exception:
                        bet_obj = None
                except Exception:
                    bet_obj = None
            if bet_obj is not None:
                placed = self._add_prop_bet(bet_obj)

            if placed:
                bankroll_after = self._snap_bankroll()
                bankroll_delta += float(bankroll_after - bankroll_before)
            else:
                bankroll_delta -= float(amount)

            key = verb.replace("ats_", "").replace("_bet", "")
            bets_delta[f"ats_{key}"] = f"+{amount:g}"

            progress_defaults = {"small": 0, "tall": 0, "all": 0}
            player_progress = getattr(player, "_ats_progress", None)
            progress: Dict[str, Any] = {}
            if isinstance(player_progress, Mapping):
                for prog_key in progress_defaults:
                    raw_value = player_progress.get(prog_key, 0)
                    try:
                        progress[prog_key] = int(raw_value)
                    except (TypeError, ValueError):
                        try:
                            progress[prog_key] = float(raw_value or 0.0)
                        except Exception:
                            progress[prog_key] = 0
            else:
                progress.update(progress_defaults)

            progress.setdefault("small", 0)
            progress.setdefault("tall", 0)
            progress.setdefault("all", 0)
            progress[key] = 0

            try:
                setattr(player, "_ats_progress", dict(progress))
            except Exception:
                pass

            try:
                self._ats_progress = dict(progress)
            except Exception:
                pass

            extra_effect = {"bonus_family": "ATS", "ats_progress": dict(progress)}

        elif verb in ("remove_line", "remove_come", "remove_dont_come"):
            snap_now = self.snapshot_state()
            odds_type = getattr(cs_bet, "Odds", None)
            pass_cls = getattr(cs_bet, "PassLine", None)
            dont_pass_cls = getattr(cs_bet, "DontPass", None)
            come_cls = getattr(cs_bet, "Come", None)
            dont_come_cls = getattr(cs_bet, "DontCome", None)
            if verb == "remove_line":
                bankroll_before = self._snap_bankroll()
                for bet_obj, num_val, _, _ in list(_iter_player_bets()):
                    if pass_cls and isinstance(bet_obj, pass_cls):
                        _remove_bet_object(bet_obj, num_val)
                    elif dont_pass_cls and isinstance(bet_obj, dont_pass_cls):
                        _remove_bet_object(bet_obj, num_val)
                    elif odds_type and isinstance(bet_obj, odds_type):
                        base = getattr(bet_obj, "base_type", None)
                        if base is pass_cls and _remove_bet_object(bet_obj, num_val):
                            continue
                        if base is dont_pass_cls and _remove_bet_object(bet_obj, num_val):
                            continue
                for key in ("pass", "dont_pass"):
                    cur = float(snap_now.get("bets", {}).get(key, 0.0))
                    if cur > 0:
                        bets_delta[key] = f"-{int(cur)}"
                for k in ("pass", "dont_pass"):
                    oamt = float(snap_now.get("odds", {}).get(k, 0.0))
                    if oamt > 0:
                        bets_delta[f"odds_{k}"] = f"-{int(oamt)}"
                bankroll_after = self._snap_bankroll()
                bankroll_delta += (bankroll_after - bankroll_before)
            else:
                families = {
                    "remove_come": (come_cls, "come", "come_flat"),
                    "remove_dont_come": (dont_come_cls, "dc", "dc_flat"),
                }
                bet_cls, branch_key, flat_key = families[verb]
                for bet_obj, num_val, amt_val, _ in list(_iter_player_bets()):
                    if bet_cls and isinstance(bet_obj, bet_cls) and _is_box_number(num_val):
                        if _remove_bet_object(bet_obj, num_val):
                            bankroll_delta += amt_val
                    elif odds_type and isinstance(bet_obj, odds_type):
                        base = getattr(bet_obj, "base_type", None)
                        if base is bet_cls and _is_box_number(getattr(bet_obj, "number", None)):
                            num = int(getattr(bet_obj, "number"))
                            amt_val = float(amt_val)
                            if _remove_bet_object(bet_obj, num):
                                bankroll_delta += amt_val
                for p in ("4", "5", "6", "8", "9", "10"):
                    cur = float(snap_now.get(flat_key, {}).get(p, 0.0))
                    if cur > 0:
                        bets_delta[p] = f"-{int(cur)}"
                    oamt = float(snap_now.get("odds", {}).get(branch_key, {}).get(p, 0.0))
                    if oamt > 0:
                        bets_delta[f"odds_{branch_key}_{p}"] = f"-{int(oamt)}"

        snap = _normalize_snapshot(table, player)
        if snap:
            self._apply_normalized_snapshot(snap)

        effect: Effect = {
            "schema": "1.0",
            "verb": verb,
            "target": target if isinstance(target, Mapping) else {},
            "bets": bets_delta,
            "bankroll_delta": bankroll_delta,
            "policy": None,
        }
        if extra_effect:
            effect.update(extra_effect)
        return effect

    def _effect_context(self) -> Dict[str, Any]:
        return {
            "bankroll": self.bankroll,
            "bets": dict(self.bets),
            "seed": self.seed or 0,
            "levels": dict(self.martingale_levels),
            "come_flat": dict(getattr(self, "come_flat", {})),
            "dc_flat": dict(getattr(self, "dc_flat", {})),
            "odds": {
                "pass": getattr(self, "odds_state", {}).get("pass", 0.0),
                "dont_pass": getattr(self, "odds_state", {}).get("dont_pass", 0.0),
                "come": dict(getattr(self, "odds_state", {}).get("come", {})),
                "dc": dict(getattr(self, "odds_state", {}).get("dc", {})),
            },
            "on_comeout": getattr(self, "on_comeout", True),
        }

    def _apply_effect(self, effect: Effect) -> None:
        bet_deltas = effect.get("bets") or {}
        delta_map: Dict[str, float] = {}
        for bet, delta_str in bet_deltas.items():
            try:
                delta = float(delta_str)
            except (TypeError, ValueError):
                continue
            self.bets[bet] = max(0.0, self.bets.get(bet, 0.0) + delta)
            delta_map[bet] = delta

        bankroll_delta = effect.get("bankroll_delta")
        if bankroll_delta is not None:
            try:
                self.bankroll = float(self.bankroll + float(bankroll_delta))
            except (TypeError, ValueError):
                pass

        if not hasattr(self, "odds_state"):
            self.odds_state = {
                "pass": 0.0,
                "dont_pass": 0.0,
                "come": {str(n): 0.0 for n in _BOX_NUMBERS},
                "dc": {str(n): 0.0 for n in _BOX_NUMBERS},
            }
        if not hasattr(self, "come_flat"):
            self.come_flat = {str(n): 0.0 for n in _BOX_NUMBERS}
        if not hasattr(self, "dc_flat"):
            self.dc_flat = {str(n): 0.0 for n in _BOX_NUMBERS}
        if not hasattr(self, "on_comeout"):
            self.on_comeout = True

        verb_name = effect.get("verb") if isinstance(effect.get("verb"), str) else None
        if verb_name in {"place_bet", "buy_bet", "lay_bet"}:
            kind = {"place_bet": "place", "buy_bet": "buy", "lay_bet": "lay"}[verb_name]
            for bet, delta in delta_map.items():
                if delta > 0 and _is_box_number(bet):
                    self.box_bet_types[str(int(bet))] = kind
        elif verb_name == "move_bet":
            target = effect.get("target") or {}
            src = str(target.get("from", "")) if isinstance(target, Mapping) else ""
            dst = str(target.get("to", "")) if isinstance(target, Mapping) else ""
            if _is_box_number(src):
                existing = self.box_bet_types.get(str(int(src)))
                if existing and _is_box_number(dst):
                    self.box_bet_types[str(int(dst))] = existing
                self.box_bet_types.pop(str(int(src)), None)
        elif verb_name == "take_down":
            for bet, delta in delta_map.items():
                if delta < 0 and _is_box_number(bet):
                    self.box_bet_types.pop(str(int(bet)), None)

        if verb_name in {"remove_line", "remove_come", "remove_dont_come"}:
            if verb_name == "remove_line":
                self.bets["pass"] = max(0.0, self.bets.get("pass", 0.0))
                self.bets["dont_pass"] = max(0.0, self.bets.get("dont_pass", 0.0))
                self.odds_state["pass"] = 0.0
                self.odds_state["dont_pass"] = 0.0
            elif verb_name == "remove_come":
                for num in _BOX_NUMBERS:
                    key = str(num)
                    self.come_flat[key] = 0.0
                    branch = self.odds_state.get("come", {})
                    branch[key] = 0.0
                    self.odds_state["come"] = branch
            elif verb_name == "remove_dont_come":
                for num in _BOX_NUMBERS:
                    key = str(num)
                    self.dc_flat[key] = 0.0
                    branch = self.odds_state.get("dc", {})
                    branch[key] = 0.0
                    self.odds_state["dc"] = branch

        for bet, delta in delta_map.items():
            bet_key = str(bet)
            if bet_key.startswith("odds_"):
                if bet_key == "odds_pass":
                    self.odds_state["pass"] = max(0.0, self.odds_state.get("pass", 0.0) + delta)
                elif bet_key == "odds_dont_pass":
                    self.odds_state["dont_pass"] = max(0.0, self.odds_state.get("dont_pass", 0.0) + delta)
                elif bet_key.startswith("odds_come_"):
                    point = bet_key.split("_", 2)[-1]
                    if _is_box_number(point):
                        key = str(int(point))
                        branch = self.odds_state.get("come", {})
                        branch[key] = max(0.0, float(branch.get(key, 0.0)) + delta)
                        self.odds_state["come"] = branch
                elif bet_key.startswith("odds_dc_"):
                    point = bet_key.split("_", 2)[-1]
                    if _is_box_number(point):
                        key = str(int(point))
                        branch = self.odds_state.get("dc", {})
                        branch[key] = max(0.0, float(branch.get(key, 0.0)) + delta)
                        self.odds_state["dc"] = branch

        ats_progress = effect.get("ats_progress")
        if isinstance(ats_progress, Mapping):
            try:
                self._ats_progress = dict(ats_progress)
            except Exception:
                pass
            player = self._cs_get_player()
            if player is not None:
                try:
                    setattr(player, "_ats_progress", dict(ats_progress))
                except Exception:
                    pass

        for bet_key in list(self.box_bet_types.keys()):
            if self.bets.get(bet_key, 0.0) <= 0.0:
                self.box_bet_types.pop(bet_key, None)

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
                "bet_types": dict(self.box_bet_types),
                "levels": dict(self.martingale_levels),
                "last_effect": self.last_effect,
                "on_comeout": self.on_comeout,
                "come_flat": dict(self.come_flat),
                "dc_flat": dict(self.dc_flat),
                "odds": {
                    "pass": self.odds_state.get("pass", 0.0),
                    "dont_pass": self.odds_state.get("dont_pass", 0.0),
                    "come": dict(self.odds_state.get("come", {})),
                    "dc": dict(self.odds_state.get("dc", {})),
                },
            }
        )

    def get_version(self) -> Dict[str, Any]:
        try:
            return self.transport.version()
        except Exception:
            return {"engine": "unknown", "version": "unavailable"}

    def get_capabilities(self) -> Dict[str, Any]:
        """Merge static defaults with transport-provided capabilities."""

        from crapssim_control.capabilities import get_capabilities as static_caps

        static_values = static_caps()
        merged: Dict[str, Any] = dict(static_values) if isinstance(static_values, Mapping) else {}
        merged["source"] = "static"
        # Always surface an engine_detected key so downstream consumers can rely
        # on the shape even when no live engine is present (P0/P1 invariant).
        merged.setdefault("engine_detected", {})

        try:
            engine_caps_raw = self.transport.capabilities()
            engine_caps = (
                dict(engine_caps_raw)
                if isinstance(engine_caps_raw, Mapping)
                else {}
            )

            if engine_caps:
                merged["source"] = "merged"
                merged["engine_source"] = "live"
            else:
                merged.pop("engine_source", None)

            merged["engine_detected"] = engine_caps
            if hasattr(self, "_engine_info"):
                self._engine_info["capabilities"] = engine_caps
        except Exception:
            merged["engine_detected"] = {"error": "capability_probe_failed"}

        return merged

    def cancel_bet(self, family: str, target=None, amount=None):
        """Universal alias to cancel or pull down bets between rolls."""

        def _call_take_down(selector, amt):
            handler = getattr(self, "take_down", None)
            if callable(handler):
                return handler(selector, amt)

            args: Dict[str, Any] = {}
            if selector is not None:
                if isinstance(selector, (list, tuple, set)):
                    selectors = list(selector)
                else:
                    selectors = [selector]
                args["target"] = {"selector": selectors}
            if amt is not None:
                args["amount"] = amt if isinstance(amt, Mapping) else {"value": amt}
            return self.apply_action("take_down", args)

        fam = (family or "").lower()
        if fam in {"place", "buy", "lay"}:
            return _call_take_down(target, amount)
        elif fam == "odds":
            subfam = "pass"
            if isinstance(target, (tuple, list)) and len(target) == 2:
                subfam, point = target
            else:
                point = target
            handler = getattr(self, "remove_odds", None)
            if callable(handler):
                return handler(on=subfam, point=point)
            args = {"on": subfam}
            if point is not None:
                args["point"] = point
            return self.apply_action("remove_odds", args)
        elif fam == "hardway":
            return _call_take_down(target, amount)
        elif fam in {"dc", "dont_come", "dont_pass"}:
            handler = getattr(self, "move_bet", None)
            if callable(handler):
                return handler(from_=target, to="off")
            return self.apply_action(
                "move_bet",
                {"target": {"from": target, "to": "off"}},
            )
        elif fam == "field":
            return _call_take_down("field", amount)
        else:
            return {"error": f"Unknown family '{family}'", "verb": "cancel_bet"}

    def _apply_normalized_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self.bankroll = float(snapshot.get("bankroll", self.bankroll))
        bets = snapshot.get("bets") or {}
        if isinstance(bets, Mapping):
            self.bets = {str(k): float(v) for k, v in bets.items()}
        bet_types = snapshot.get("bet_types")
        if isinstance(bet_types, Mapping):
            self.box_bet_types = {
                str(k): str(v) for k, v in bet_types.items() if isinstance(v, str)
            }
        elif self.live_engine:
            self.box_bet_types = {
                k: v for k, v in self.box_bet_types.items() if self.bets.get(k, 0.0) > 0.0
            }
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
        come_flat = snapshot.get("come_flat")
        if isinstance(come_flat, Mapping):
            coerced = {str(n): 0.0 for n in _BOX_NUMBERS}
            for key, value in come_flat.items():
                if _is_box_number(key):
                    try:
                        coerced[str(int(key))] = float(value or 0.0)
                    except (TypeError, ValueError):
                        continue
            self.come_flat = coerced
        elif self.live_engine:
            self.come_flat = {str(n): 0.0 for n in _BOX_NUMBERS}

        dc_flat = snapshot.get("dc_flat")
        if isinstance(dc_flat, Mapping):
            coerced_dc = {str(n): 0.0 for n in _BOX_NUMBERS}
            for key, value in dc_flat.items():
                if _is_box_number(key):
                    try:
                        coerced_dc[str(int(key))] = float(value or 0.0)
                    except (TypeError, ValueError):
                        continue
            self.dc_flat = coerced_dc
        elif self.live_engine:
            self.dc_flat = {str(n): 0.0 for n in _BOX_NUMBERS}

        odds = snapshot.get("odds")
        if isinstance(odds, Mapping):
            odds_state = {
                "pass": 0.0,
                "dont_pass": 0.0,
                "come": {str(n): 0.0 for n in _BOX_NUMBERS},
                "dc": {str(n): 0.0 for n in _BOX_NUMBERS},
            }
            for key in ("pass", "dont_pass"):
                try:
                    odds_state[key] = float(odds.get(key, 0.0) or 0.0)  # type: ignore[index]
                except (TypeError, ValueError):
                    odds_state[key] = 0.0
            for family in ("come", "dc"):
                branch = odds.get(family)
                if isinstance(branch, Mapping):
                    for point, value in branch.items():
                        if _is_box_number(point):
                            try:
                                odds_state[family][str(int(point))] = float(value or 0.0)
                            except (TypeError, ValueError):
                                continue
            self.odds_state = odds_state
        elif self.live_engine:
            self.odds_state = {
                "pass": 0.0,
                "dont_pass": 0.0,
                "come": {str(n): 0.0 for n in _BOX_NUMBERS},
                "dc": {str(n): 0.0 for n in _BOX_NUMBERS},
            }

        ats_progress = snapshot.get("ats_progress")
        if isinstance(ats_progress, Mapping):
            coerced_progress: Dict[str, float] = {}
            for key, value in ats_progress.items():
                try:
                    coerced_progress[str(key)] = float(value or 0.0)
                except (TypeError, ValueError):
                    coerced_progress[str(key)] = 0.0
            try:
                self._ats_progress = coerced_progress
            except Exception:
                pass
            player = self._cs_get_player()
            if player is not None:
                try:
                    setattr(player, "_ats_progress", dict(coerced_progress))
                except Exception:
                    pass

        on_comeout = snapshot.get("on_comeout")
        if isinstance(on_comeout, bool):
            self.on_comeout = on_comeout
        elif self.live_engine:
            point_val = snapshot.get("point_value")
            self.on_comeout = point_val in (None, 0)
        props_branch = snapshot.get("props")
        if not (isinstance(props_branch, Mapping) and props_branch):
            if self.live_engine:
                self._props_intent = []
                self._props_pending = []
        self._snapshot_cache = dict(snapshot)
        self._last_snapshot = dict(snapshot)

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
        if self._session_started:
            try:
                self.transport.snapshot()
            except Exception:
                pass
        if self.live_engine and self._engine_adapter is not None:
            raw = self._engine_adapter.snapshot_state()
            snapshot = _normalize_snapshot(raw)
            overlay = _normalize_snapshot(self._table, self._player)
            if overlay:
                merged: Dict[str, Any] = dict(snapshot)
                bets_combined: Dict[str, float] = {}
                raw_bets = snapshot.get("bets")
                if isinstance(raw_bets, Mapping):
                    bets_combined.update({str(k): float(v) for k, v in raw_bets.items()})
                overlay_bets = overlay.get("bets")
                if isinstance(overlay_bets, Mapping):
                    bets_combined.update({str(k): float(v) for k, v in overlay_bets.items()})
                filtered_bets: Dict[str, float] = {}
                for key, val in bets_combined.items():
                    key_str = str(key)
                    if _is_box_number(key_str) or key_str in {"pass", "dc"}:
                        filtered_bets[key_str] = val
                for key, val in bets_combined.items():
                    key_str = str(key)
                    if key_str not in filtered_bets and key_str.lower() not in {"place", "buy", "lay"}:
                        filtered_bets[key_str] = val
                merged["bets"] = filtered_bets
                if overlay.get("bet_types"):
                    merged["bet_types"] = dict(overlay.get("bet_types") or {})
                for key in ("bankroll", "point_on", "point_value", "hand_id", "roll_in_hand", "rng_seed"):
                    if key in overlay and overlay[key] is not None:
                        merged[key] = overlay[key]
                overlay_props = overlay.get("props")
                if isinstance(overlay_props, Mapping):
                    merged["props"] = {
                        str(k): float(v)
                        for k, v in overlay_props.items()
                        if isinstance(v, (int, float))
                    }
                elif "props" not in merged:
                    merged["props"] = {}
                if "ats_progress" in overlay and isinstance(overlay.get("ats_progress"), Mapping):
                    merged["ats_progress"] = {
                        str(k): float(v)
                        for k, v in overlay.get("ats_progress", {}).items()
                        if isinstance(v, (int, float))
                    }
                elif "ats_progress" not in merged and hasattr(self, "_ats_progress"):
                    progress_map = getattr(self, "_ats_progress", {})
                    if isinstance(progress_map, Mapping):
                        merged["ats_progress"] = {
                            str(k): float(v)
                            for k, v in progress_map.items()
                            if isinstance(v, (int, float))
                        }
                for flat_key in ("come_flat", "dc_flat"):
                    branch_overlay = overlay.get(flat_key)
                    if isinstance(branch_overlay, Mapping):
                        combined = {str(n): 0.0 for n in _BOX_NUMBERS}
                        branch_base = merged.get(flat_key)
                        if isinstance(branch_base, Mapping):
                            for pt, val in branch_base.items():
                                if _is_box_number(pt):
                                    try:
                                        combined[str(int(pt))] = float(val or 0.0)
                                    except (TypeError, ValueError):
                                        continue
                        for pt, val in branch_overlay.items():
                            if _is_box_number(pt):
                                try:
                                    combined[str(int(pt))] = float(val or 0.0)
                                except (TypeError, ValueError):
                                    continue
                        merged[flat_key] = combined
                odds_overlay = overlay.get("odds")
                if isinstance(odds_overlay, Mapping):
                    combined_odds = {
                        "pass": 0.0,
                        "dont_pass": 0.0,
                        "come": {str(n): 0.0 for n in _BOX_NUMBERS},
                        "dc": {str(n): 0.0 for n in _BOX_NUMBERS},
                    }
                    odds_base = merged.get("odds")
                    if isinstance(odds_base, Mapping):
                        for key in ("pass", "dont_pass"):
                            try:
                                combined_odds[key] = float(odds_base.get(key, 0.0) or 0.0)  # type: ignore[index]
                            except (TypeError, ValueError):
                                combined_odds[key] = 0.0
                        for family in ("come", "dc"):
                            base_branch = odds_base.get(family)
                            if isinstance(base_branch, Mapping):
                                for pt, val in base_branch.items():
                                    if _is_box_number(pt):
                                        try:
                                            combined_odds[family][str(int(pt))] = float(val or 0.0)
                                        except (TypeError, ValueError):
                                            continue
                    for key in ("pass", "dont_pass"):
                        try:
                            combined_odds[key] = float(odds_overlay.get(key, combined_odds[key]) or 0.0)  # type: ignore[index]
                        except (TypeError, ValueError):
                            continue
                    for family in ("come", "dc"):
                        branch_overlay = odds_overlay.get(family)
                        if isinstance(branch_overlay, Mapping):
                            for pt, val in branch_overlay.items():
                                if _is_box_number(pt):
                                    try:
                                        combined_odds[family][str(int(pt))] = float(val or 0.0)
                                    except (TypeError, ValueError):
                                        continue
                    merged["odds"] = combined_odds
                if "on_comeout" in overlay:
                    merged["on_comeout"] = bool(overlay.get("on_comeout"))
                snapshot = merged
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
            "bet_types": dict(self.box_bet_types),
            "hand_id": 0,
            "roll_in_hand": 0,
            "rng_seed": self.seed or 0,
            "on_comeout": self.on_comeout,
            "come_flat": dict(self.come_flat),
            "dc_flat": dict(self.dc_flat),
            "odds": {
                "pass": self.odds_state.get("pass", 0.0),
                "dont_pass": self.odds_state.get("dont_pass", 0.0),
                "come": dict(self.odds_state.get("come", {})),
                "dc": dict(self.odds_state.get("dc", {})),
            },
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


def verb_place_bet(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Effect:
    target = (args.get("target") or {})
    amount = (args.get("amount") or {})
    bet = str(target.get("bet", ""))
    val = float(amount.get("value", 0.0))
    if not _is_box_number(bet) or val <= 0:
        raise ValueError("place_bet_invalid_args")
    return {
        "schema": "1.0",
        "verb": "place_bet",
        "target": {"bet": bet},
        "bets": {bet: f"+{int(val)}"},
        "bankroll_delta": -val,
        "policy": None,
    }


def verb_buy_bet(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Effect:
    target = (args.get("target") or {})
    amount = (args.get("amount") or {})
    bet = str(target.get("bet", ""))
    val = float(amount.get("value", 0.0))
    if not _is_box_number(bet) or val <= 0:
        raise ValueError("buy_bet_invalid_args")
    return {
        "schema": "1.0",
        "verb": "buy_bet",
        "target": {"bet": bet},
        "bets": {bet: f"+{int(val)}"},
        "bankroll_delta": -val,
        "policy": None,
    }


def verb_lay_bet(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Effect:
    target = (args.get("target") or {})
    amount = (args.get("amount") or {})
    bet = str(target.get("bet", ""))
    val = float(amount.get("value", 0.0))
    if not _is_box_number(bet) or val <= 0:
        raise ValueError("lay_bet_invalid_args")
    return {
        "schema": "1.0",
        "verb": "lay_bet",
        "target": {"bet": bet},
        "bets": {bet: f"+{int(val)}"},
        "bankroll_delta": -val,
        "policy": None,
    }


def verb_take_down(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Effect:
    sel = (args.get("target") or {}).get("selector") or []
    bets: Dict[str, str] = {}
    refund = 0.0
    for k in sel:
        key = str(k)
        current = float(snapshot.get("bets", {}).get(key, 0.0))
        if current > 0:
            bets[key] = f"-{int(current)}"
            refund += current
    return {
        "schema": "1.0",
        "verb": "take_down",
        "target": {"selector": [str(k) for k in sel]},
        "bets": bets,
        "bankroll_delta": refund,
        "policy": None,
    }


def verb_move_bet(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Effect:
    target = (args.get("target") or {})
    src = str(target.get("from", ""))
    dst = str(target.get("to", ""))
    current = float(snapshot.get("bets", {}).get(src, 0.0))
    if not (_is_box_number(src) and _is_box_number(dst) and current > 0):
        raise ValueError("move_bet_invalid_args")
    return {
        "schema": "1.0",
        "verb": "move_bet",
        "target": {"from": src, "to": dst},
        "bets": {src: f"-{int(current)}", dst: f"+{int(current)}"},
        "bankroll_delta": 0.0,
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
VerbRegistry.register("place_bet", verb_place_bet)
VerbRegistry.register("buy_bet", verb_buy_bet)
VerbRegistry.register("lay_bet", verb_lay_bet)
VerbRegistry.register("take_down", verb_take_down)
VerbRegistry.register("move_bet", verb_move_bet)
VerbRegistry.register("same_bet", verb_same_bet)
VerbRegistry.register("switch_profile", verb_switch_profile)
VerbRegistry.register("apply_policy", verb_apply_policy)

# Ensure supplemental verb registrations are loaded.
from . import verbs as _verbs_module  # noqa: F401


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
        self._bet_overlay: Dict[str, float] = {}

    # ----- EngineAdapter interface --------------------------------------------------
    def start_session(self, spec: Dict[str, Any]) -> None:
        seed = None
        if isinstance(spec, dict):
            seed = spec.get("seed") or spec.get("run", {}).get("seed")
        if seed is not None:
            try:
                random.seed(int(seed))
            except Exception:
                pass
        result = attach_engine(spec)
        self.table = result.table
        self.controller_player = result.controller_player
        self.meta = dict(result.meta or {})
        self._attach_result = result
        self._bet_overlay = {}
        if seed is not None:
            try:
                self.set_seed(int(seed))
            except Exception:
                pass

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

        def _coerce_amount(value: Any) -> float:
            if isinstance(value, Mapping):
                raw = value.get("value", value.get("amount", 0.0))
            else:
                raw = value
            try:
                return float(raw or 0.0)
            except (TypeError, ValueError):
                return 0.0

        if verb in ("set_odds", "take_odds"):
            side = str(args.get("side") or args.get("on") or "").lower()
            number_raw = args.get("number") or args.get("point")
            try:
                number_val = int(number_raw)
            except (TypeError, ValueError):
                number_val = 0
            amount_val = _coerce_amount(args.get("amount"))
            if side not in {"come", "dc"} or number_val not in _BOX_NUMBERS:
                return _reject("illegal_window", "invalid come/dc odds target")
            if amount_val <= 0:
                return _reject("illegal_amount", "amount must be positive")
            key = f"odds_{side}_{number_val}"
            delta = amount_val if verb == "set_odds" else -amount_val
            self._bet_overlay[key] = max(0.0, self._bet_overlay.get(key, 0.0) + delta)
            return {
                "verb": verb,
                "target": f"{side}_{number_val}",
                "amount": amount_val,
                "result": "ok",
            }

        if verb == "field_bet":
            amount_val = _coerce_amount(args.get("amount"))
            if amount_val <= 0:
                return _reject("illegal_amount", "amount must be positive")
            self._bet_overlay["field"] = self._bet_overlay.get("field", 0.0) + amount_val
            return {"verb": verb, "amount": amount_val, "result": "ok"}

        if verb == "hardway_bet":
            try:
                number_val = int(args.get("number"))
            except (TypeError, ValueError):
                number_val = 0
            amount_val = _coerce_amount(args.get("amount"))
            if number_val not in (4, 6, 8, 10):
                return _reject("illegal_number", "invalid hardway number")
            if amount_val <= 0:
                return _reject("illegal_amount", "amount must be positive")
            key = f"hardway_{number_val}"
            self._bet_overlay[key] = self._bet_overlay.get(key, 0.0) + amount_val
            return {
                "verb": verb,
                "number": number_val,
                "amount": amount_val,
                "result": "ok",
            }

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
                return _reject("engine_error", str(exc))

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

        for key, value in self._bet_overlay.items():
            try:
                bets[key] = float(value)
            except (TypeError, ValueError):
                continue

        snapshot = {
            "bankroll": float(bankroll) if bankroll is not None else None,
            "point_on": bool(point_on),
            "point_value": int(point_value) if point_value is not None else None,
            "bets": bets,
            "hand_id": int(hand_id) if hand_id is not None else 0,
            "roll_in_hand": int(roll_in_hand) if roll_in_hand is not None else 0,
            "rng_seed": rng_seed,
        }

        try:
            from .snapshot_normalizer import SnapshotNormalizer

            snapshot = SnapshotNormalizer(self).normalize_snapshot(snapshot)
        except Exception:
            pass

        return snapshot

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

