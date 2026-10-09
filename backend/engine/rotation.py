"""Turn rotation: fixed order, skip absent learners, easy item after N wrong in a row."""


def turn_order(group_order: list[str], present: list[str], rules) -> list[str]:
    """Learners in the group's fixed order. Absent learners are skipped."""
    if rules.rotation.skip_absent:
        return [c for c in group_order if c in present]
    return list(group_order)


def child_for_turn(order: list[str], turn_number: int) -> str:
    """turn_number starts at 1."""
    return order[(turn_number - 1) % len(order)]


def needs_easy_item(first_try_results: list[bool], rules) -> bool:
    """first_try_results: the learner's items, oldest first, True = right on the first try.
    After easy_item_after_wrong wrong items in a row, the next turn is an easy item."""
    n = rules.rotation.easy_item_after_wrong
    return len(first_try_results) >= n and not any(first_try_results[-n:])
