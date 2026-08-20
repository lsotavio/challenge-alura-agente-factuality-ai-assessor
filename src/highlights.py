from __future__ import annotations


def highlighted_fragments(response: str, target: str) -> list[str]:
    """Recover one or more highlighted fragments from the compact text field."""
    compact_target = target.strip()
    if not compact_target:
        return []
    if compact_target in response:
        return [compact_target]
    fragments = []
    for line in compact_target.splitlines():
        fragment = line.strip()
        if fragment and fragment in response and fragment not in fragments:
            fragments.append(fragment)
    return fragments or [compact_target]


def scoped_target(response: str, target: str) -> str:
    return " | ".join(highlighted_fragments(response, target))
