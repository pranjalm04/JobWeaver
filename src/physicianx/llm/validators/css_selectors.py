from __future__ import annotations

from functools import lru_cache

from physicianx.llm.validators.exceptions import OutputValidationError


@lru_cache(maxsize=1)
def _minimal_soup():
    from bs4 import BeautifulSoup

    return BeautifulSoup(
        "<html><body><div id='root'><a class='job' href='#'></a></div></body></html>",
        "html.parser",
    )


def assert_css_selector_syntax(selector: str, *, field: str) -> None:
    """Ensure `selector` is non-empty and parses for BeautifulSoup/soupsieve `select()`."""

    s = selector.strip()
    if not s:
        raise OutputValidationError(f"{field}: selector must not be empty when required.")
    soup = _minimal_soup()
    try:
        soup.select(s)
    except Exception as e:
        raise OutputValidationError(f"{field}: invalid CSS selector {s!r}: {e}") from e
