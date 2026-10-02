from openlibrary.first_edits.compare import (
    dates_agree,
    languages_agree,
    pages_agree,
    publishers_agree,
    subtitles_agree,
    values_agree,
)


def test_publishers_ignore_noise_words():
    assert publishers_agree(["Alfred A. Knopf"], ["Knopf"])
    assert publishers_agree(["Penguin Books"], ["Penguin"])
    assert publishers_agree(["Doubleday, Anchor Books"], ["Anchor Books"])


def test_publishers_differ_when_no_meaningful_overlap():
    assert not publishers_agree(["Penguin"], ["Anchor Books"])
    assert not publishers_agree(["Simon and Schuster"], ["Scribner"])
    assert not publishers_agree([], ["Scribner"])


def test_dates_compare_by_year():
    assert dates_agree("1994-09-01", "1994.")
    assert dates_agree("October 1, 1988", "1988")
    assert not dates_agree("2017", "1994")
    assert not dates_agree("n.d.", "1994")


def test_pages_tolerate_front_matter():
    assert pages_agree(209, 212)
    assert pages_agree("96", 100)
    assert not pages_agree(209, 226)
    assert not pages_agree(None, 226)


def test_languages_and_subtitles():
    assert languages_agree(["eng"], ["eng", "fre"])
    assert not languages_agree(["eng"], ["ger"])
    assert subtitles_agree("war, memory, and the post-Cold War in Asia", "War, Memory, and the Post–Cold War in Asia")  # noqa: RUF001
    assert not subtitles_agree("A Novel", "or there and back again")


def test_values_agree_treats_empty_as_disagreement():
    assert not values_agree("publishers", [], ["Knopf"])
    assert not values_agree("number_of_pages", None, 100)
    assert values_agree("publishers", ["Knopf"], ["Alfred A. Knopf"])
