"""Checks for the adoption rule in docs/phase-4/TARGETS.md (sections 1 and 2).

FLOORS holds those thresholds. A missing number fails its check. This module
reports the conditions; it does not adopt a ranking change.
"""
from __future__ import annotations

from .evaluation import paired_ndcg_comparison

# docs/phase-4/TARGETS.md sections 1 and 2, agreed 25 September 2026.
FLOORS = {
    "ndcg_gain": 0.03,
    "ndcg_at_10": 0.63,
    "mrr": 0.69,
    "mrr_doc": 0.88,
    "document_queries": 13,
    "false_notice_rate": 0.10,
    "notice_recall": 0.68,
    "category_min_n": 8,
    "category_max_loss": 0.05,
    "judged_at_10": 0.9,
}


def _result(name, value, threshold, passed, missing=False):
    return {"name": name, "value": value, "threshold": threshold,
            "passed": passed, "missing": missing}


def _missing(name, threshold):
    return _result(name, None, threshold, False, missing=True)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _entry(run, group, metric):
    if not isinstance(run, dict):
        return None
    aggregate = run.get("aggregate")
    if not isinstance(aggregate, dict):
        return None
    group_data = aggregate.get(group)
    if not isinstance(group_data, dict):
        return None
    entry = group_data.get(metric)
    return entry if isinstance(entry, dict) else None


def _mean(run, group, metric):
    entry = _entry(run, group, metric)
    if entry is None:
        return None
    return _number(entry.get("mean"))


def _at_least(run, group, metric, name, bound, threshold):
    value = _mean(run, group, metric)
    if value is None:
        return _missing(name, threshold)
    return _result(name, value, threshold, value >= bound)


def _at_most(run, group, metric, name, bound, threshold):
    value = _mean(run, group, metric)
    if value is None:
        return _missing(name, threshold)
    return _result(name, value, threshold, value <= bound)


def _ndcg_gain(baseline, candidate):
    name = "ndcg_gain"
    threshold = f">= {FLOORS['ndcg_gain']:.2f}"
    base = _mean(baseline, "split:test", "ndcg_at_10")
    cand = _mean(candidate, "split:test", "ndcg_at_10")
    if base is None or cand is None:
        return _missing(name, threshold)
    gain = round(cand - base, 6)
    return _result(name, gain, threshold, gain >= FLOORS["ndcg_gain"])


def _paired_ci(baseline, candidate):
    name = "paired_ci"
    threshold = "both ends > 0"
    baseline_rows = baseline.get("queries") if isinstance(baseline, dict) else None
    candidate_rows = candidate.get("queries") if isinstance(candidate, dict) else None
    if not isinstance(baseline_rows, list) or not isinstance(candidate_rows, list):
        return _missing(name, threshold)
    report = paired_ndcg_comparison(baseline_rows, candidate_rows)
    group = report["splits"].get("test")
    ci = None if not group else group.get("ci95")
    if ci is None:
        return _missing(name, threshold)
    lo, hi = ci
    if _number(lo) is None or _number(hi) is None:
        return _missing(name, threshold)
    interval = (float(lo), float(hi))
    return _result(name, interval, threshold, interval[0] > 0 and interval[1] > 0)


def _document_first(candidate):
    name = "document_first_act"
    required = FLOORS["document_queries"]
    threshold = f"{required} of {required}"
    rows = candidate.get("queries") if isinstance(candidate, dict) else None
    if not isinstance(rows, list):
        return _missing(name, threshold)
    documents = [row for row in rows if isinstance(row, dict) and row.get("level") == "document"]
    successes = []
    for row in documents:
        value = _number(row.get("success_at_1_doc"))
        if value is None:
            return _missing(name, threshold)
        successes.append(value)
    hits = sum(1 for value in successes if value == 1.0)
    n = len(documents)
    return _result(name, {"successes": hits, "rows": n}, threshold, hits == required and n == required)


def _count(entry):
    if entry is None or "n" not in entry:
        return None
    n = entry.get("n")
    if isinstance(n, bool) or not isinstance(n, (int, float)):
        return None
    if isinstance(n, float) and not n.is_integer():
        return None
    return int(n)


def _categories(baseline, candidate):
    threshold = f">= -{FLOORS['category_max_loss']:.2f}"
    if not isinstance(baseline, dict) or not isinstance(baseline.get("aggregate"), dict):
        return [_missing("category_ndcg", threshold)]
    checks = []
    for name in sorted(key for key in baseline["aggregate"]
                       if isinstance(key, str) and key.startswith("category:")):
        n = _count(_entry(baseline, name, "ndcg_at_10"))
        if n is None:
            checks.append(_missing(name, threshold))
            continue
        if n < FLOORS["category_min_n"]:
            continue
        base = _mean(baseline, name, "ndcg_at_10")
        cand = _mean(candidate, name, "ndcg_at_10")
        if base is None or cand is None:
            checks.append(_missing(name, threshold))
            continue
        delta = round(cand - base, 6)
        checks.append(_result(name, delta, threshold, delta >= -FLOORS["category_max_loss"]))
    return checks


def adoption_report(baseline: dict, candidate: dict) -> dict:
    """Each adoption condition for two loaded run records.

    Reads ``aggregate`` and ``queries`` only. The test-split interval is
    ``paired_ndcg_comparison`` (1,000 resamples, seed 0). Both ends of that
    interval must be above 0.
    """
    judged = f">= {FLOORS['judged_at_10']}"
    checks = [
        _ndcg_gain(baseline, candidate),
        _paired_ci(baseline, candidate),
        _at_least(candidate, "split:test", "ndcg_at_10", "ndcg_at_10",
                  FLOORS["ndcg_at_10"], f">= {FLOORS['ndcg_at_10']:.2f}"),
        _at_least(candidate, "split:test", "mrr", "mrr",
                  FLOORS["mrr"], f">= {FLOORS['mrr']:.2f}"),
        _at_least(candidate, "split:test", "mrr_doc", "mrr_doc",
                  FLOORS["mrr_doc"], f">= {FLOORS['mrr_doc']:.2f}"),
        _document_first(candidate),
        _at_most(candidate, "overall", "false_notice_rate", "false_notice_rate",
                 FLOORS["false_notice_rate"], f"<= {FLOORS['false_notice_rate']:.2f}"),
        _at_least(candidate, "overall", "notice_recall", "notice_recall",
                  FLOORS["notice_recall"], f">= {FLOORS['notice_recall']:.2f}"),
    ]
    checks.extend(_categories(baseline, candidate))
    checks.append(_at_least(candidate, "split:dev", "judged_at_10", "judged_at_10:dev",
                            FLOORS["judged_at_10"], judged))
    checks.append(_at_least(candidate, "split:test", "judged_at_10", "judged_at_10:test",
                            FLOORS["judged_at_10"], judged))
    failed = [check["name"] for check in checks if not check["passed"]]
    verdict = "ALL CONDITIONS MET" if not failed else "NOT MET: " + ", ".join(failed)
    return {"checks": checks, "verdict": verdict}


def _format_value(check) -> str:
    if check["missing"]:
        return "missing"
    value = check["value"]
    if isinstance(value, tuple):
        return f"[{value[0]:.6f}, {value[1]:.6f}]"
    if isinstance(value, float):
        return f"{value:.6f}"
    if isinstance(value, dict):
        return f"{value['successes']} of {value['rows']}"
    return str(value)


def format_adoption_report(report: dict) -> str:
    """One line per check, then the verdict. Aggregates only."""
    lines = []
    for check in report["checks"]:
        status = "pass" if check["passed"] else "fail"
        lines.append(f"{check['name']}: value={_format_value(check)} "
                     f"threshold={check['threshold']} {status}")
    lines.append(report["verdict"])
    return "\n".join(lines)
