from __future__ import annotations

from typing import Optional, Tuple

from physicianx.pipeline.stages.heuristics import check_job_listing_heuristics


def score_listing(html_content: str, url: Optional[str] = None) -> Tuple[float, list]:
    result = check_job_listing_heuristics(html_content, url=url)
    return result.score, result.debug_info
