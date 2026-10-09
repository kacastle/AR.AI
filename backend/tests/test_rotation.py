from backend.engine import rotation

GROUP = ["c_ana", "c_ben", "c_mila"]


def test_fixed_order_skips_absent(rules):
    order = rotation.turn_order(GROUP, ["c_mila", "c_ana"], rules)
    assert order == ["c_ana", "c_mila"]   # group order, not the order of `present`


def test_child_for_turn_cycles(rules):
    order = rotation.turn_order(GROUP, GROUP, rules)
    assert [rotation.child_for_turn(order, t) for t in range(1, 7)] == GROUP + GROUP


def test_easy_item_after_3_wrong_in_a_row(rules):
    assert rules.rotation.easy_item_after_wrong == 3
    assert rotation.needs_easy_item([True, False, False, False], rules)
    assert not rotation.needs_easy_item([False, False, True], rules)
    assert not rotation.needs_easy_item([False, False], rules)
    assert not rotation.needs_easy_item([False, False, False, True], rules)
