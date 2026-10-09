from backend.engine.feedback import GENERIC, feedback_for, mistake_code


def test_word_mistakes_use_the_tile_classifier():
    assert mistake_code("dictation_letters", ["b", "a", "h", "a", "y"], ["b", "a", "h", "a"]) == "P_OMIT_FINAL"
    assert mistake_code("missing_letter", ["m", "e", "s", "a"], ["m", "i", "s", "a"]) == "P_SUB_VOWEL"
    assert mistake_code("dictation_syllables", ["sa", "pa", "tos"], ["sa", "tos"]) == "P_OMIT_MID"


def test_sentence_order_and_punctuation():
    expected = ["Si", "Ana", "ay", "nasa", "bahay."]
    assert mistake_code("sentence_builder", expected, ["bahay.", "Si", "Ana", "ay", "nasa"]) == "SN_ORDER"
    assert mistake_code("sentence_builder", expected, ["si", "Ana", "ay", "nasa", "bahay"]) == "SN_PUNCT"
    assert mistake_code("sentence_builder", expected, ["Si", "Ana", "ay", "bahay."]) == "SN_ORDER"


def test_templates_fill_name_and_syllables(rules):
    fb = feedback_for(rules, "P_OMIT_FINAL", name="Ben", syllables=["ba", "hay"], slots=5)
    assert fb.message_fil == "Malapit na, Ben!"
    assert fb.hint_fil == "Pakinggan ang huling pantig: ba-HAY."

    fb = feedback_for(rules, "S_SYLL_MISS", name="Ben", syllables=["sa", "pa", "tos"], slots=7)
    assert fb.message_fil == "Konti na lang!"
    assert fb.hint_fil == "Pumalakpak tayo: sa-pa-tos. Ilang pantig?"

    fb = feedback_for(rules, "O_NG", name="Ben", syllables=["ngi", "pin"], slots=5)
    assert (fb.message_fil, fb.hint_fil) == ("Kaya mo ito!", 'Hanapin ang tile na "ng."')

    fb = feedback_for(rules, "P_ADD", name="Ben", syllables=["ma", "ta"], slots=4)
    assert fb.hint_fil == "Bilangin ang mga kahon: 4 lang."


def test_correct_lines_rotate(rules):
    lines = [feedback_for(rules, "CORRECT", name="Ana", syllables=[], slots=0, turn=k).message_fil
             for k in range(3)]
    assert lines[0] == "Ang galing mo, Ana!"
    assert len(set(lines)) == 3


def test_unknown_code_uses_generic_fallback(rules):
    fb = feedback_for(rules, "NOT_A_CODE", name="Mila", syllables=["a"], slots=1)
    assert fb.message_fil == GENERIC.format(name="Mila") == "Subukan natin ulit, Mila!"
    assert fb.hint_fil is None


def test_hint_can_be_left_out(rules):
    fb = feedback_for(rules, "P_OMIT_FINAL", name="Ben", syllables=["ba", "hay"], slots=5, with_hint=False)
    assert fb.message_fil == "Malapit na, Ben!"
    assert fb.hint_fil is None
