import json
import os
import tempfile

from crapssim_control.journal import append_effect_summary_line


def test_jsonl_lines_include_verb_and_schema():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "effect_summaries.jsonl")
        # missing verb on purpose to exercise inference
        append_effect_summary_line(p, {"bets": {"8": "+12"}, "bankroll_delta": -12.0})
        append_effect_summary_line(p, {"verb": "place_bet", "bets": {"6": "+6"}, "bankroll_delta": -6.0})
        data = [json.loads(s) for s in open(p, encoding="utf-8").read().splitlines() if s.strip()]
        assert len(data) == 2
        for obj in data:
            assert "verb" in obj and isinstance(obj["verb"], str) and obj["verb"]  # non-empty
            assert "schema" in obj and obj["schema"] == "1.0"
            # stable keys present
            for k in ("target", "bets", "bankroll_delta", "policy"):
                assert k in obj
