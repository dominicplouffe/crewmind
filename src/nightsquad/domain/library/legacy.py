"""Format markers written before the product was renamed (LIB-1, LIB-2, LIB-4, ADR-0011).

Files exported before the rename, and Founder drafts stored then, carry the old marker.
Reading one renames the marker; everything written carries the new one.
"""

from __future__ import annotations

from typing import Any, cast

OLD_PRODUCT = "crew" + "mind"

FORMAT_MARKERS = {
    f"{OLD_PRODUCT}_role": "nightsquad_role",
    f"{OLD_PRODUCT}_crew": "nightsquad_squad",
    f"{OLD_PRODUCT}_spec": "nightsquad_spec",
}


def renamed_markers(document: Any) -> Any:
    """The document with any old format marker renamed; anything else is left as given."""
    if not isinstance(document, dict):
        return document
    fields = cast(dict[str, Any], document)
    old = [key for key in FORMAT_MARKERS if key in fields]
    if not old:
        return fields
    renamed = dict(fields)
    for key in old:
        renamed.setdefault(FORMAT_MARKERS[key], renamed.pop(key))
    return renamed
