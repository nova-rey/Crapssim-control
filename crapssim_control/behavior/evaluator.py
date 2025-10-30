from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from .dsl_parser import RuleDef
from .verbs import VerbRegistry, default_registry
from .journal import DecisionsJournal, DecisionAttempt

DecisionSnapshot = Dict[str, Any]


def _eval_bool(expr: str, ctx: Dict[str, Any]) -> bool:
    # tiny safe evaluator: replace operators with python, map vars from ctx
    # supports: > < >= <= == !=, && || ! via pre-normalization
    s = expr.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
    # replace true/false
    s = s.replace("true", "True").replace("false", "False")
    # prepare local dict with only whitelisted keys present in ctx
    # Python eval here is avoided; we instead do a very constrained eval using comparisons
    # minimal hack: split tokens and rebuild — safe subset
    # For MVP we rely on Python eval but only with literals from ctx and operator tokens
    allowed = {k: ctx.get(k) for k in ctx.keys()}
    # BEWARE: In earlier phases we avoided eval; for DSL MVP we keep it controlled:
    return bool(eval(s, {"__builtins__": {}}, allowed))  # guarded by parser whitelist


@dataclass
class _CooldownState:
    rolls: int = 0
    hands: int = 0
    point_cycles: int = 0


class BehaviorEngine:
    def __init__(
        self,
        rules: List[RuleDef],
        verbs: Optional[VerbRegistry] = None,
        once_per_window: bool = True,
        verbose: bool = False,
    ):
        self.rules = rules
        self.verbs = verbs or default_registry()
        self.once_per_window = once_per_window
        self.verbose = verbose
        self._cooldowns: Dict[str, _CooldownState] = {}
        self.last_attempt: Optional[DecisionAttempt] = None

    def _decrement_scope(self, scope: str) -> None:
        for st in self._cooldowns.values():
            if scope == "roll":
                st.rolls = max(0, st.rolls - 1)
            elif scope == "hand":
                st.hands = max(0, st.hands - 1)
            elif scope == "point_cycle":
                st.point_cycles = max(0, st.point_cycles - 1)

    def on_scope_advance(self, scope: str) -> None:
        self._decrement_scope(scope)

    def evaluate_window(
        self, window: str, snap: Dict[str, Any], journal: DecisionsJournal
    ) -> Optional[Dict[str, Any]]:
        # Evaluate rules in spec order; stop after first applied (if once_per_window)
        self.last_attempt = None
        for r in self.rules:
            # cooldown
            st = self._cooldowns.setdefault(r.id, _CooldownState())
            if r.cooldown:
                if (
                    (r.cooldown.get("rolls", 0) and st.rolls > 0)
                    or (r.cooldown.get("hands", 0) and st.hands > 0)
                    or (r.cooldown.get("point_cycles", 0) and st.point_cycles > 0)
                ):
                    if self.verbose:
                        journal.write(
                            DecisionAttempt(
                                snap.get("roll_index", 0),
                                window,
                                r.id,
                                "dsl",
                                r.when,
                                False,
                                r.then,
                                getattr(r, "args", {}),
                                False,
                                False,
                                "COOLDOWN",
                            )
                        )
                    continue
            # guards
            ok = True
            for g in r.guards or []:
                try:
                    if not _eval_bool(g, snap):
                        ok = False
                        break
                except Exception:
                    ok = False
                    break
            if not ok:
                if self.verbose:
                    journal.write(
                        DecisionAttempt(
                            snap.get("roll_index", 0),
                            window,
                            r.id,
                            "dsl",
                            r.when,
                            False,
                            r.then,
                            getattr(r, "args", {}),
                            False,
                            False,
                            "GUARD_FALSE",
                        )
                    )
                continue
            # when
            try:
                cond = _eval_bool(r.when, snap)
            except Exception:
                journal.write(
                    DecisionAttempt(
                        snap.get("roll_index", 0),
                        window,
                        r.id,
                        "dsl",
                        r.when,
                        False,
                        r.then,
                        getattr(r, "args", {}),
                        False,
                        False,
                        "WHEN_EVAL_ERROR",
                    )
                )
                continue
            if not cond:
                if self.verbose:
                    journal.write(
                        DecisionAttempt(
                            snap.get("roll_index", 0),
                            window,
                            r.id,
                            "dsl",
                            r.when,
                            False,
                            r.then,
                            getattr(r, "args", {}),
                            False,
                            False,
                            None,
                        )
                    )
                continue

            # build intent via verb registry
            intent = self.verbs.apply(r.then, getattr(r, "args", {}))
            # legality is enforced upstream; we only propose
            attempt = DecisionAttempt(
                snap.get("roll_index", 0),
                window,
                r.id,
                "dsl",
                r.when,
                True,
                r.then,
                getattr(r, "args", {}),
                True,
                True,
                None,
            )
            journal.write(attempt)
            self.last_attempt = attempt
            # set cooldowns
            if r.cooldown:
                rolls_cd = int(r.cooldown.get("rolls", 0))
                hands_cd = int(r.cooldown.get("hands", 0))
                point_cd = int(r.cooldown.get("point_cycles", 0))
                if rolls_cd:
                    st.rolls = max(st.rolls, rolls_cd + 1)
                if hands_cd:
                    st.hands = max(st.hands, hands_cd + 1)
                if point_cd:
                    st.point_cycles = max(st.point_cycles, point_cd + 1)
            return intent if self.once_per_window else intent
        return None
