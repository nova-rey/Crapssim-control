"""risk_schema.py — defines structured schema for bankroll and risk policy settings."""

from dataclasses import dataclass, field
from typing import Dict, Optional, Literal, Any


@dataclass
class RecoveryPolicy:
    enabled: bool = False
    mode: Literal["none", "flat_recovery", "step_recovery"] = "none"


@dataclass
class RiskPolicy:
    version: str = "1.0"
    max_drawdown_pct: Optional[float] = None
    max_heat: Optional[float] = None
    bet_caps: Dict[str, float] = field(default_factory=dict)
    recovery: RecoveryPolicy = field(default_factory=RecoveryPolicy)


def load_risk_policy(spec: Dict[str, Any]) -> RiskPolicy:
    """Load risk policy from spec or return defaults."""
    run_risk = ((spec or {}).get("run") or {}).get("risk", {}) or {}
    policy = RiskPolicy()

    if "max_drawdown_pct" in run_risk:
        try:
            val = float(run_risk["max_drawdown_pct"])
            if 0 <= val <= 100:
                policy.max_drawdown_pct = val
        except Exception:
            pass

    if "max_heat" in run_risk:
        try:
            val = float(run_risk["max_heat"])
            if val >= 0:
                policy.max_heat = val
        except Exception:
            pass

    if "bet_caps" in run_risk and isinstance(run_risk["bet_caps"], dict):
        for k, v in run_risk["bet_caps"].items():
            try:
                policy.bet_caps[str(k)] = float(v)
            except Exception:
                continue

    recovery = run_risk.get("recovery", {})
    if isinstance(recovery, dict):
        policy.recovery.enabled = bool(recovery.get("enabled", False))
        mode = str(recovery.get("mode", "none")).lower()
        if mode in ("flat_recovery", "step_recovery"):
            policy.recovery.mode = mode
        else:
            policy.recovery.mode = "none"

    return policy
