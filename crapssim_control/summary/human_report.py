import json
import pathlib
from textwrap import dedent


def _read_json(path):
    return json.loads(pathlib.Path(path).read_text())


def _safe(p: pathlib.Path, name: str):
    q = p / name
    if q.exists():
        return q
    # tolerate slight naming differences (e.g., summary.json under artifacts root)
    candidates = list(p.glob("**/" + name))
    return candidates[0] if candidates else None


def generate(artifacts_dir: str) -> str:
    """
    Create a human-readable markdown report next to summary.json.
    Inputs (must already exist from prior run):
      - summary.json
      - manifest.json (optional; enrich header if present)
      - decisions.csv (optional; pick a handful of rows)
    Returns path to report.md
    """
    a = pathlib.Path(artifacts_dir)
    summary_p = _safe(a, "summary.json")
    if not summary_p:
        raise FileNotFoundError("summary.json not found in artifacts")

    manifest_p = _safe(a, "manifest.json")
    decisions_p = _safe(a, "decisions.csv")

    summary = _read_json(summary_p)
    manifest = _read_json(manifest_p) if manifest_p else {}
    flags = manifest.get("run", {}).get("flags", {}) if manifest else {}

    # Minimal fields; tolerate absence
    stats = summary.get("stats", {})
    bankroll = summary.get("bankroll", {})
    pso = stats.get("pso_count") or summary.get("pso_count")
    peak = bankroll.get("peak") or stats.get("bankroll_peak")
    trough = bankroll.get("trough") or stats.get("bankroll_trough")
    drawdown = stats.get("max_drawdown")

    header = dedent(
        f"""\
    # CSC Run Summary (Human)

    **Artifacts:** `{a}`  
    **Flags:** {flags if flags else "{}"}
    """
    )
    body = []

    body.append("## Bankroll & Risk\n")
    body.append(f"- Peak bankroll: {peak}\n" if peak is not None else "- Peak bankroll: (n/a)\n")
    body.append(
        f"- Trough bankroll: {trough}\n" if trough is not None else "- Trough bankroll: (n/a)\n"
    )
    body.append(
        f"- Max drawdown: {drawdown}\n" if drawdown is not None else "- Max drawdown: (n/a)\n"
    )
    body.append(f"- PSO count: {pso}\n" if pso is not None else "- PSO count: (n/a)\n")

    # Top rules (if present)
    top_rules = summary.get("top_rules") or []
    if top_rules:
        body.append("\n## Top Rules Fired\n")
        for item in top_rules[:10]:
            rid = item.get("rule_id", "unknown")
            cnt = item.get("count", "?")
            body.append(f"- {rid}: {cnt}\n")

    # Decisions storyboard (sample a few lines if available)
    if decisions_p and decisions_p.exists():
        rows = []
        with decisions_p.open() as fp:
            header_line = fp.readline()  # header
            for i, line in enumerate(fp):
                if i >= 8:  # small illustrative slice
                    break
                rows.append(line.strip())
        if rows:
            body.append("\n## Decision Storyboard (first 8)\n")
            body.append("```\n")
            for r in rows:
                body.append(r + "\n")
            body.append("```\n")

    report_p = a / "report.md"
    report_p.write_text(header + "\n" + "".join(body))
    return str(report_p)
