"""policy_engine.py — Core risk and bankroll policy evaluation logic."""

from typing import Dict, Any
from crapssim_control.risk_schema import RiskPolicy


class PolicyEngine:
    """Evaluates drawdown, heat, bet caps, and recovery adjustments deterministically."""

    def __init__(self, policy: RiskPolicy):
        self.policy = policy

    def check_drawdown(self, current_bankroll: float, peak_bankroll: float) -> bool:
        """Return False if drawdown exceeds max_drawdown_pct."""
        if not self.policy.max_drawdown_pct:
            return True
        if peak_bankroll <= 0:
            return True
        drawdown_pct = ((peak_bankroll - current_bankroll) / peak_bankroll) * 100
        return drawdown_pct <= self.policy.max_drawdown_pct

    def check_heat(self, active_bets_sum: float) -> bool:
        """Return False if total bet exposure exceeds max_heat."""
        if not self.policy.max_heat:
            return True
        return active_bets_sum <= self.policy.max_heat

    def check_bet_cap(self, bet_type: str, amount: float) -> bool:
        """Return False if individual bet exceeds cap."""
        cap = self.policy.bet_caps.get(bet_type)
        if cap is None:
            return True
        return amount <= cap

    def apply_recovery(self, previous_loss: float) -> float:
        """Adjusts next bet amount based on recovery mode."""
        if not self.policy.recovery.enabled or previous_loss <= 0:
            return 0.0

        mode = self.policy.recovery.mode
        if mode == "flat_recovery":
            return previous_loss
        if mode == "step_recovery":
            # Example: scale by 1.5x increments
            return previous_loss * 1.5
        return 0.0

    def evaluate(self, action: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry: evaluate if a proposed action is allowed under policy."""
        result = {
            "allowed": True,
            "modified": False,
            "reason": None,
            "adjusted_amount": None,
            "policy_triggered": [],
        }

        bankroll = float(snapshot.get("bankroll_after", snapshot.get("bankroll", 0)))
        peak = float(snapshot.get("bankroll_peak", bankroll))
        active = float(snapshot.get("active_bets_sum", 0))
        bet_type = str(action.get("verb", ""))
        amount = float(action.get("args", {}).get("amount", 0))

        if not self.check_drawdown(bankroll, peak):
            result["allowed"] = False
            result["reason"] = "drawdown_limit"
            result["policy_triggered"].append("drawdown_limit")
            return result

        if not self.check_heat(active):
            result["allowed"] = False
            result["reason"] = "heat_limit"
            result["policy_triggered"].append("heat_limit")
            return result

        if not self.check_bet_cap(bet_type, amount):
            result["allowed"] = False
            result["reason"] = "bet_cap"
            result["policy_triggered"].append("bet_cap")
            return result

        prev_loss = float(snapshot.get("previous_loss", 0))
        adjustment = self.apply_recovery(prev_loss)
        if adjustment > 0:
            result["modified"] = True
            result["adjusted_amount"] = adjustment
            result["policy_triggered"].append("recovery_applied")

        return result
