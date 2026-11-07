import pytest

from services.deck_parser import DeckParseError, DeckParser


def test_parses_quantity_formats_and_ignores_blank_lines() -> None:
    result = DeckParser().parse("  1 Sol Ring  \n1x Arcane Signet\nCommand Tower\n\n")

    assert [(entry.quantity, entry.name) for entry in result] == [
        (1, "Sol Ring"),
        (1, "Arcane Signet"),
        (1, "Command Tower"),
    ]


def test_parses_multiple_copies() -> None:
    result = DeckParser().parse("12x Island\n2 Sol Ring")

    assert [entry.quantity for entry in result] == [12, 2]


def test_removes_trailing_set_and_collector_metadata() -> None:
    result = DeckParser().parse(
        "Academy Manufactor (BLC) 264\n1x Burakos, Party Leader (CLB) 653"
    )

    assert [(entry.quantity, entry.name) for entry in result] == [
        (1, "Academy Manufactor"),
        (1, "Burakos, Party Leader"),
    ]


def test_parses_commander_names_with_quantity_and_set_metadata() -> None:
    names = DeckParser().parse_names(
        "1x Burakos, Party Leader (CLB) 653\n1x Folk Hero (CLB) 650"
    )

    assert names == ["Burakos, Party Leader", "Folk Hero"]
    assert DeckParser().parse_names(" ") == []


def test_does_not_change_typographical_errors_or_unmatched_parentheses() -> None:
    result = DeckParser().parse("NIghthawk Scavenger\nCard Name (Custom Edition)")

    assert [entry.name for entry in result] == [
        "NIghthawk Scavenger",
        "Card Name (Custom Edition)",
    ]


@pytest.mark.parametrize("decklist", ["0 Sol Ring", "2", "1x", ""])
def test_rejects_invalid_lines(decklist: str) -> None:
    with pytest.raises(DeckParseError):
        DeckParser().parse(decklist)