"""Pure RRF helper tests — no heavy ML imports."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Sequence, Tuple


def _rrf(rankings: Sequence[Sequence[int]], k: int = 60) -> List[Tuple[int, float]]:
    scores: Dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def test_rrf_merges_rankings():
    fused = _rrf([[1, 2, 3], [3, 1, 4]], k=60)
    ids = [idx for idx, _score in fused]
    assert 1 in ids and 3 in ids
    assert ids.index(1) <= 2
    assert ids.index(3) <= 2


def test_citation_marker_regex():
    import re

    text = "Theo tài liệu [1] và [2]."
    html = re.sub(
        r"\[(\d+)\]",
        r'<sup class="cite" title="Nguồn \1">\1</sup>',
        text,
    )
    assert 'class="cite"' in html
    assert ">1<" in html and ">2<" in html
