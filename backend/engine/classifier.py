"""Classify a wrong tile answer into a mistake code from rules.json mistake_types.

Tiles are lists; ng is one tile. Checks, in order:
1. same tiles in a different order        -> O_ORDER
2. n and g given as two tiles where ng was -> O_NG
3. Levenshtein alignment, leftmost mistake decides:
   substitution ng->n -> O_NG; vowel->vowel -> P_SUB_VOWEL; consonant->consonant -> P_SUB_CONS
   (vowel<->consonant goes by the expected tile);
   2+ deleted tiles in a row -> S_SYLL_MISS; 1 deleted at the end -> P_OMIT_FINAL,
   elsewhere -> P_OMIT_MID; an extra tile -> P_ADD.
"""
from typing import Optional

VOWELS = {"a", "e", "i", "o", "u"}


def _merge_ng(tiles: list[str]) -> tuple[list[str], set[int]]:
    """Join each n,g pair into one ng tile. Returns the new list and the merged positions."""
    out, merged, i = [], set(), 0
    while i < len(tiles):
        if tiles[i] == "n" and i + 1 < len(tiles) and tiles[i + 1] == "g":
            merged.add(len(out))
            out.append("ng")
            i += 2
        else:
            out.append(tiles[i])
            i += 1
    return out, merged


def _edit_ops(expected: list[str], given: list[str]) -> list[tuple[str, int, int]]:
    """Levenshtein edit operations left to right: (op, expected_index, given_index).

    op is 'sub', 'del' (tile missing from given) or 'ins' (extra tile in given).
    Ties prefer a deletion as far right as possible, so a missing last tile is final.
    """
    n, m = len(expected), len(given)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if expected[i - 1] == given[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)

    ops, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and d[i][j] == d[i - 1][j] + 1:
            ops.append(("del", i - 1, j))
            i -= 1
        elif i > 0 and j > 0 and expected[i - 1] == given[j - 1] and d[i][j] == d[i - 1][j - 1]:
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + 1:
            ops.append(("sub", i - 1, j - 1))
            i, j = i - 1, j - 1
        else:
            ops.append(("ins", i, j - 1))
            j -= 1
    ops.reverse()
    return ops


def classify(expected: list[str], given: list[str]) -> Optional[str]:
    """Return the mistake code for `given`, or None if it is correct."""
    if given == expected:
        return None

    # 1. Right tiles, wrong order.
    if sorted(given) == sorted(expected):
        return "O_ORDER"

    # 2. ng split into n + g where the word has ng.
    _, positions = _merge_ng(given)
    if any(p < len(expected) and expected[p] == "ng" for p in positions):
        return "O_NG"

    # 3. Alignment: the leftmost operation decides.
    ops = _edit_ops(expected, given)
    op, ei, gi = ops[0]
    if op == "sub":
        want, got = expected[ei], given[gi]
        if want == "ng" and got == "n":
            return "O_NG"
        return "P_SUB_VOWEL" if want in VOWELS else "P_SUB_CONS"
    if op == "ins":
        return "P_ADD"

    # Deletions: count the run of deleted tiles that are next to each other.
    run = 1
    for next_op, next_ei, _ in ops[1:]:
        if next_op == "del" and next_ei == ei + run:
            run += 1
        else:
            break
    if run >= 2:
        return "S_SYLL_MISS"
    return "P_OMIT_FINAL" if ei == len(expected) - 1 else "P_OMIT_MID"
