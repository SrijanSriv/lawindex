"""Retrieval metrics and per-query/aggregate evaluation rows.

Pure functions only: everything a caller needs (a ranking, a query, a search
response, a per-query grade map, the corpus records) is passed in. Nothing
here reads a file or the network. Schemas and the grading scale are defined
in docs/phase-4/BENCHMARK_PLAN.md and lawindex/benchmark.py.
"""
from __future__ import annotations

import math
import random

from .benchmark import RELEVANT

EXCLUDED_REASONS = ("document_level", "out_of_corpus", "no_relevant_judged")
PROVISION_METRICS = ("ndcg_at_10", "mrr", "recall_at_10", "recall_at_20", "p_at_5", "p_at_10",
                     "success_at_3", "judged_at_10")
DOC_METRICS = ("mrr_doc", "success_at_1_doc", "recall_at_3_doc")
BOOTSTRAPPED_METRICS = ("ndcg_at_10", "mrr")


def _round(value):
    return value if value is None else round(value, 6)


def dcg(gains) -> float:
    """Discounted cumulative gain: sum of (2**g - 1) / log2(i + 2) over positions i from 0."""
    return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranking, grades: dict, k: int = 10):
    """DCG of the top k (unjudged gain 0) over the DCG of the ideal top k of judged grades."""
    actual = dcg(grades.get(key, 0) for key in ranking[:k])
    ideal = dcg(sorted(grades.values(), reverse=True)[:k])
    return None if ideal == 0 else actual / ideal


def mrr(ranking, grades: dict, cutoff: int = 20) -> float:
    """Reciprocal rank of the first key graded >= RELEVANT within cutoff, else 0.0."""
    for position, key in enumerate(ranking[:cutoff], start=1):
        if grades.get(key, 0) >= RELEVANT:
            return 1.0 / position
    return 0.0


def recall_at_k(ranking, grades: dict, k: int):
    """Relevant (>=RELEVANT) keys retrieved in the top k, over all relevant judged keys."""
    relevant = {key for key, g in grades.items() if g >= RELEVANT}
    if not relevant:
        return None
    retrieved = sum(1 for key in ranking[:k] if key in relevant)
    return retrieved / len(relevant)


def precision_at_k(ranking, grades: dict, k: int) -> float:
    """Relevant keys in the top k, over k (a short ranking still divides by k)."""
    relevant = sum(1 for key in ranking[:k] if grades.get(key, 0) >= RELEVANT)
    return relevant / k


def success_at_k_best(ranking, grades: dict, k: int = 3):
    """1.0 if a key carrying the query's best judged grade (>=RELEVANT) is in the top k."""
    if not grades:
        return None
    best = max(grades.values())
    if best < RELEVANT:
        return None
    best_keys = {key for key, g in grades.items() if g == best}
    return 1.0 if any(key in best_keys for key in ranking[:k]) else 0.0


def judged_at_k(ranking, grades: dict, k: int = 10):
    """Share of the top min(k, len(ranking)) that has a judgment."""
    if not ranking:
        return None
    top = ranking[:k]
    return sum(1 for key in top if key in grades) / len(top)


def act_ranking(ranking, act_of: dict) -> list:
    """Distinct Act slugs in order of first appearance."""
    seen, out = set(), []
    for key in ranking:
        slug = act_of[key]
        if slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out


def doc_metrics(ranking, act_of: dict, relevant_acts) -> dict:
    """Document-level metrics over the ranking collapsed to distinct Acts.

    `relevant_acts` must be non-empty; the caller decides when there is
    nothing to score (see evaluate_query's "None if there are none").
    """
    acts = act_ranking(ranking, act_of)
    relevant = set(relevant_acts)
    reciprocal = 0.0
    for position, slug in enumerate(acts, start=1):
        if slug in relevant:
            reciprocal = 1.0 / position
            break
    success_at_1 = 1.0 if acts and acts[0] in relevant else 0.0
    recall_at_3 = (sum(1 for slug in acts[:3] if slug in relevant) / len(relevant)) if relevant else None
    return {"mrr_doc": reciprocal, "success_at_1_doc": success_at_1, "recall_at_3_doc": recall_at_3}


def bootstrap_ci(values, resamples: int = 1000, seed: int = 0):
    """95% percentile interval of the mean, via a fixed-seed bootstrap. None values must be
    dropped by the caller before this is called; an empty list here also yields None."""
    if not values:
        return None
    values = list(values)
    n = len(values)
    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    return (_round(percentile(means, 2.5)), _round(percentile(means, 97.5)))


def percentile(values, p: float):
    """Nearest-rank percentile; None for an empty sequence."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(p / 100 * len(ordered))))
    return ordered[rank - 1]


def _numeric_ndcg(row: dict):
    value = row.get("ndcg_at_10")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _rows_by_id(rows, label: str) -> dict:
    index = {}
    for row in rows:
        qid = row["id"]
        if qid in index:
            raise ValueError(f"{label} has duplicate query id {qid}")
        index[qid] = row
    return index


def paired_ndcg_comparison(baseline_rows, candidate_rows, resamples: int = 1000, seed: int = 0) -> dict:
    """Paired bootstrap of per-query nDCG@10 differences, one result per split.

    Difference is candidate minus baseline. Queries are paired by id, in id
    order, and only when both runs have a numeric nDCG@10 and the same split.
    The interval is `bootstrap_ci` on those differences (95%, default 1,000
    resamples, seed 0). This reports the interval; it does not decide adoption.
    """
    baseline = _rows_by_id(baseline_rows, "baseline")
    candidate = _rows_by_id(candidate_rows, "candidate")
    diffs_by_split: dict = {}
    unscored = []
    unpaired = []
    for qid in sorted(set(baseline) | set(candidate)):
        base = baseline.get(qid)
        cand = candidate.get(qid)
        if base is None:
            unpaired.append({"id": qid, "reason": "only in candidate"})
            continue
        if cand is None:
            unpaired.append({"id": qid, "reason": "only in baseline"})
            continue
        if base.get("split") != cand.get("split"):
            raise ValueError(f"{qid}: split {base.get('split')!r} != {cand.get('split')!r}")
        base_ndcg = _numeric_ndcg(base)
        cand_ndcg = _numeric_ndcg(cand)
        if base_ndcg is None and cand_ndcg is None:
            unscored.append(qid)
            continue
        if base_ndcg is None or cand_ndcg is None:
            side = "baseline" if base_ndcg is None else "candidate"
            unpaired.append({"id": qid, "reason": f"ndcg_at_10 missing in {side}"})
            continue
        diffs_by_split.setdefault(base["split"], []).append(_round(cand_ndcg - base_ndcg))

    splits = {}
    for split, diffs in sorted(diffs_by_split.items()):
        splits[split] = {
            "n": len(diffs),
            "mean_difference": _round(sum(diffs) / len(diffs)),
            "ci95": bootstrap_ci(diffs, resamples=resamples, seed=seed),
        }
    return {"resamples": resamples, "seed": seed, "splits": splits,
            "unscored": unscored, "unpaired": unpaired}


def evaluate_query(query: dict, response: dict, grades: dict, records: dict) -> dict:
    """One evaluation row for a query, given the live search response and its judged grades.

    `grades` is the {provision_key: grade} map for this one query (judged pairs only).
    `records` is the corpus (snapshot.records): {key: {..., "act_slug": ...}}.
    """
    ranking = [r["key"] for r in response["results"]]
    notices = [n["code"] for n in response["notices"]]
    row = {"id": query["id"], "category": query["category"], "scope": query["scope"],
           "level": query["level"], "split": query["split"], "ranking": ranking, "notices": notices,
           "search_ms": _round(response["trace"]["search_ms"])}

    if query["level"] != "provision":
        excluded_reason = "document_level"
    elif query["scope"] == "out_of_corpus":
        excluded_reason = "out_of_corpus"
    elif not grades or max(grades.values()) < RELEVANT:
        excluded_reason = "no_relevant_judged"
    else:
        excluded_reason = None
    row["excluded_reason"] = excluded_reason

    if excluded_reason is None:
        row["ndcg_at_10"] = _round(ndcg_at_k(ranking, grades, 10))
        row["mrr"] = _round(mrr(ranking, grades))
        row["recall_at_10"] = _round(recall_at_k(ranking, grades, 10))
        row["recall_at_20"] = _round(recall_at_k(ranking, grades, 20))
        row["p_at_5"] = _round(precision_at_k(ranking, grades, 5))
        row["p_at_10"] = _round(precision_at_k(ranking, grades, 10))
        row["success_at_3"] = _round(success_at_k_best(ranking, grades, 3))
        row["judged_at_10"] = _round(judged_at_k(ranking, grades, 10))
        row["unjudged_in_top_10"] = [key for key in ranking[:10] if key not in grades]
    else:
        for name in PROVISION_METRICS:
            row[name] = None
        row["unjudged_in_top_10"] = None

    if query["scope"] == "out_of_corpus":
        relevant_acts = set()
    elif query["level"] == "document":
        relevant_acts = set(query.get("relevant_acts", []))
    else:
        relevant_acts = {records[key]["act_slug"] for key, g in grades.items()
                         if g >= RELEVANT and key in records}
    if query["scope"] != "out_of_corpus" and relevant_acts:
        act_of = {key: records[key]["act_slug"] for key in set(ranking) | set(grades) if key in records}
        doc = doc_metrics(ranking, act_of, relevant_acts)
        row["mrr_doc"] = _round(doc["mrr_doc"])
        row["success_at_1_doc"] = _round(doc["success_at_1_doc"])
        row["recall_at_3_doc"] = _round(doc["recall_at_3_doc"])
    else:
        for name in DOC_METRICS:
            row[name] = None

    expected_notices = query.get("expected_notices") or []
    row["notice_hit"] = all(code in notices for code in expected_notices) if expected_notices else None
    if query["scope"] == "in_corpus":
        row["false_notice"] = any(code.endswith("_not_indexed") for code in notices) or "weak_match" in notices
    else:
        row["false_notice"] = None
    return row


def aggregate(rows: list) -> dict:
    """Means (ignoring None) of every metric, grouped overall / by split / category / scope,
    with bootstrap CIs for nDCG@10 and MRR, notice recall / false-notice rate, and latency
    percentiles (overall only). Also lists excluded query ids per reason."""
    metric_names = PROVISION_METRICS + DOC_METRICS

    def summarize(name, group_rows):
        summary = {"n": len(group_rows)}
        for metric in metric_names:
            values = [r[metric] for r in group_rows if r.get(metric) is not None]
            entry = {"mean": _round(sum(values) / len(values)) if values else None, "n": len(values)}
            if metric in BOOTSTRAPPED_METRICS:
                entry["ci95"] = bootstrap_ci(values)
            summary[metric] = entry
        for metric, out_name in (("notice_hit", "notice_recall"), ("false_notice", "false_notice_rate")):
            values = [r[metric] for r in group_rows if r.get(metric) is not None]
            summary[out_name] = {"mean": _round(sum(values) / len(values)) if values else None, "n": len(values)}
        if name == "overall":
            latencies = [r["search_ms"] for r in group_rows if r.get("search_ms") is not None]
            summary["p50_ms"] = percentile(latencies, 50)
            summary["p95_ms"] = percentile(latencies, 95)
        return summary

    groups = {"overall": rows}
    for split in sorted({r["split"] for r in rows}):
        groups[f"split:{split}"] = [r for r in rows if r["split"] == split]
    for category in sorted({r["category"] for r in rows}):
        groups[f"category:{category}"] = [r for r in rows if r["category"] == category]
    for scope in sorted({r["scope"] for r in rows}):
        groups[f"scope:{scope}"] = [r for r in rows if r["scope"] == scope]

    result = {name: summarize(name, group_rows) for name, group_rows in groups.items()}
    result["excluded"] = {reason: sorted(r["id"] for r in rows if r.get("excluded_reason") == reason)
                          for reason in EXCLUDED_REASONS}
    return result
