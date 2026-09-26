"""Reciprocal rank fusion across retrieval methods. Search does not call this yet."""


def reciprocal_rank_fusion(rankings: dict[str, list[str]], k: int = 60, limit: int | None = None) -> list[dict]:
    """Score each key by the sum of 1/(k + rank) over methods, rank counted from 1.

    A key missing from a method adds nothing. A key repeated in one list counts
    once, at its earliest rank. Order is score descending, then best rank
    ascending, then key ascending.
    """
    if k < 1:
        raise ValueError('k must be at least 1.')
    if not rankings:
        raise ValueError('rankings must contain at least one method.')
    best: dict[str, dict[str, int]] = {}
    for method, ranking in rankings.items():
        if not isinstance(ranking, list):
            raise ValueError(f'{method} ranking must be a list.')
        seen: set[str] = set()
        for rank, key in enumerate(ranking, start=1):
            if key in seen:
                continue
            seen.add(key)
            best.setdefault(key, {})[method] = rank
    rows = []
    for key, ranks in best.items():
        score = round(sum(1 / (k + rank) for rank in ranks.values()), 9)
        rows.append((-score, min(ranks.values()), key, ranks))
    rows.sort()
    fused = [{'key': key, 'score': -negated, 'ranks': ranks}
             for negated, _best_rank, key, ranks in rows]
    if limit is None:
        return fused
    return fused[:limit]
