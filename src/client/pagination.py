"""Page/size pagination, shared by every list endpoint (§52).

Numbered pagination, because that is what a table needs: "page 7 of 42" is a
place a reader can return to, and the envelope below carries the total and the
page count so a footer can say it.

**The keyset-cursor mode that used to live here is gone.** It was a base64 JSON
token with an `encode`/`decode` pair and no caller: the two things that
actually scroll — the Data Explorer's "load more" in its scanning modes, and
the log tail — do it differently and for good reasons. Load-more accumulates
*pages* of the same question client-side, so a reader who scrolls and then
narrows is never shown two answers at once. The tail keys on a **line id**,
because two lines can share a millisecond and a timestamp cursor either repeats
them or drops them; an id needs no envelope. Dead code with a docstring
promising a strategy nothing uses is worse than the absence of both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 25
#: The sizes a *saved* view may carry, and the ones the pagers offer. Narrower
#: than "1 to MAX_PAGE_SIZE" on purpose: a page size somebody typed into a URL
#: is fine, and one stored in a saved search has to be a value the pager can
#: show as selected.
PAGE_SIZE_CHOICES = (10, 25, 50, 100, 200)


@dataclass(slots=True)
class Page:
    page: int
    page_size: int
    sort: str
    order: str

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def parse_page(args, *, default_sort: str, default_order: str = "desc") -> Page:
    from client.errors import ValidationError

    try:
        page = max(1, int(args.get("page", 1)))
        page_size = int(args.get("page_size", DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError) as exc:
        raise ValidationError("page and page_size must be integers") from exc

    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise ValidationError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")

    order = (args.get("order") or default_order).lower()
    if order not in ("asc", "desc"):
        raise ValidationError("order must be 'asc' or 'desc'")

    return Page(page=page, page_size=page_size, sort=args.get("sort") or default_sort, order=order)


def envelope(items: list[Any], total: int, page: Page, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "items": items,
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
        "pages": max(1, (total + page.page_size - 1) // page.page_size),
        "sort": page.sort,
        "order": page.order,
    }
    body.update(extra)
    return body


def parse_uuid(value: str, *, field: str = "id"):
    """Validate a path parameter before it reaches SQL.

    An arbitrary string in a UUID comparison makes PostgreSQL raise
    `invalid input syntax for type uuid`, which surfaces as a 500 for what is
    plainly a client error.
    """
    from uuid import UUID

    from client.errors import ValidationError

    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be a UUID", details={field: str(value)}) from exc
