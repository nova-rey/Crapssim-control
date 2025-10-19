"""Fallback verb handlers for CSC stubs.

These handlers provide deterministic math when the live engine is absent.
"""

from __future__ import annotations

from typing import Any, Dict

from .engine_adapter import VerbRegistry


def _amt(args: Dict[str, Any]) -> float:
    return float((args.get("amount") or {}).get("value", 0.0))


def _pt(args: Dict[str, Any]) -> str | None:
    return str(int(args.get("point"))) if args.get("point") is not None else None


def verb_line_bet(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    side = args.get("side") or "pass"
    val = _amt(args)
    key = "pass" if side == "pass" else "dont_pass"
    if val <= 0:
        raise ValueError("line_bet_invalid_args")
    return {
        "schema": "1.0",
        "verb": "line_bet",
        "target": {"side": side},
        "bets": {key: f"+{int(val)}"},
        "bankroll_delta": -val,
        "policy": None,
    }


def verb_come_bet(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    val = _amt(args)
    if val <= 0:
        raise ValueError("come_bet_invalid_args")
    return {
        "schema": "1.0",
        "verb": "come_bet",
        "bets": {"come": "+{}".format(int(val))},
        "bankroll_delta": -val,
        "policy": None,
    }


def verb_dont_come_bet(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    val = _amt(args)
    if val <= 0:
        raise ValueError("dont_come_bet_invalid_args")
    return {
        "schema": "1.0",
        "verb": "dont_come_bet",
        "bets": {"dc": "+{}".format(int(val))},
        "bankroll_delta": -val,
        "policy": None,
    }


def verb_set_odds(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    on = args.get("on") or "pass"
    val = _amt(args)
    pt = _pt(args)
    if val <= 0:
        raise ValueError("set_odds_invalid_args")
    key = "odds_"
    if on in ("dp", "dont_pass"):
        key += "dont_pass"
    elif on == "dc" and pt:
        key += f"dc_{pt}"
    elif on == "come" and pt:
        key += f"come_{pt}"
    else:
        key += "pass"
    return {
        "schema": "1.0",
        "verb": "set_odds",
        "bets": {key: f"+{int(val)}"},
        "bankroll_delta": -val,
        "policy": None,
    }


def verb_take_odds(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    on = args.get("on") or "pass"
    val = _amt(args)
    pt = _pt(args)
    if val <= 0:
        raise ValueError("take_odds_invalid_args")
    key = "odds_"
    if on in ("dp", "dont_pass"):
        key += "dont_pass"
    elif on == "dc" and pt:
        key += f"dc_{pt}"
    elif on == "come" and pt:
        key += f"come_{pt}"
    else:
        key += "pass"
    return {
        "schema": "1.0",
        "verb": "take_odds",
        "bets": {key: f"-{int(val)}"},
        "bankroll_delta": val,
        "policy": None,
    }


def verb_remove_line(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    bets: Dict[str, str] = {}
    refund = 0.0
    for key in ("pass", "dont_pass"):
        cur = float(snapshot.get("bets", {}).get(key, 0.0))
        if cur > 0:
            bets[key] = f"-{int(cur)}"
            refund += cur
    odds_info = snapshot.get("odds", {}) if isinstance(snapshot.get("odds"), dict) else {}
    for key in ("pass", "dont_pass"):
        cur = float(odds_info.get(key, 0.0))
        if cur > 0:
            bets[f"odds_{key}"] = f"-{int(cur)}"
            refund += cur
    return {
        "schema": "1.0",
        "verb": "remove_line",
        "bets": bets,
        "bankroll_delta": refund,
        "policy": None,
    }


def verb_remove_come(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    bets: Dict[str, str] = {}
    refund = 0.0
    come_flat = snapshot.get("come_flat") if isinstance(snapshot.get("come_flat"), dict) else {}
    odds_info = (
        snapshot.get("odds", {}).get("come", {})
        if isinstance(snapshot.get("odds"), dict)
        else {}
    )
    for p in ("4", "5", "6", "8", "9", "10"):
        cur = float(come_flat.get(p, 0.0)) if come_flat else float(snapshot.get("bets", {}).get(p, 0.0))
        if cur > 0:
            bets[p] = f"-{int(cur)}"
            refund += cur
        oamt = float(odds_info.get(p, 0.0)) if isinstance(odds_info, dict) else 0.0
        if oamt > 0:
            bets[f"odds_come_{p}"] = f"-{int(oamt)}"
            refund += oamt
    return {
        "schema": "1.0",
        "verb": "remove_come",
        "bets": bets,
        "bankroll_delta": refund,
        "policy": None,
    }


def verb_remove_dont_come(snapshot: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    bets: Dict[str, str] = {}
    refund = 0.0
    dc_flat = snapshot.get("dc_flat") if isinstance(snapshot.get("dc_flat"), dict) else {}
    odds_info = (
        snapshot.get("odds", {}).get("dc", {})
        if isinstance(snapshot.get("odds"), dict)
        else {}
    )
    for p in ("4", "5", "6", "8", "9", "10"):
        cur = float(dc_flat.get(p, 0.0)) if dc_flat else 0.0
        if cur > 0:
            bets[p] = f"-{int(cur)}"
            refund += cur
        oamt = float(odds_info.get(p, 0.0)) if isinstance(odds_info, dict) else 0.0
        if oamt > 0:
            bets[f"odds_dc_{p}"] = f"-{int(oamt)}"
            refund += oamt
    return {
        "schema": "1.0",
        "verb": "remove_dont_come",
        "bets": bets,
        "bankroll_delta": refund,
        "policy": None,
    }


VerbRegistry.register("line_bet", verb_line_bet)
VerbRegistry.register("come_bet", verb_come_bet)
VerbRegistry.register("dont_come_bet", verb_dont_come_bet)
VerbRegistry.register("set_odds", verb_set_odds)
VerbRegistry.register("take_odds", verb_take_odds)
VerbRegistry.register("remove_line", verb_remove_line)
VerbRegistry.register("remove_come", verb_remove_come)
VerbRegistry.register("remove_dont_come", verb_remove_dont_come)
