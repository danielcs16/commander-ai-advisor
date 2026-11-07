import httpx
import pytest

from services.scryfall_service import ScryfallService, ScryfallServiceError


def card_payload(**updates):
    payload = {
        "name": "Test Card",
        "oracle_id": "oracle-id",
        "mana_cost": "{U}",
        "cmc": 1,
        "type_line": "Instant",
        "oracle_text": "Draw a card.",
        "colors": ["U"],
        "color_identity": ["U"],
        "keywords": [],
        "legalities": {"commander": "legal"},
        "prices": {"usd": "1.25"},
        "scryfall_uri": "https://scryfall.com/card/test",
    }
    payload.update(updates)
    return payload


def make_service(handler, **kwargs):
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.scryfall.test")
    return ScryfallService(client=client, max_retries=kwargs.pop("max_retries", 0), **kwargs)


def test_get_card_by_name_maps_scryfall_data():
    service = make_service(lambda request: httpx.Response(200, json=card_payload()))

    card = service.get_card_by_name("Test Card")

    assert card is not None
    assert card.commander_legal is True
    assert card.price_usd == 1.25
    assert card.color_identity == ["U"]


def test_missing_card_is_cached_as_not_found():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(404, json={"details": "not found"})

    service = make_service(handler)
    assert service.get_card_by_name("Missing") is None
    assert service.get_card_by_name("Missing") is None
    assert calls == 1


def test_server_error_is_reported():
    service = make_service(lambda request: httpx.Response(500), max_retries=0)
    with pytest.raises(ScryfallServiceError, match="HTTP 500"):
        service.get_card_by_name("Test Card")


def test_rate_limit_retries(monkeypatch):
    monkeypatch.setattr("services.scryfall_service.time.sleep", lambda _: None)
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=card_payload())

    assert make_service(handler, max_retries=1).get_card_by_name("Test Card") is not None
    assert calls == 2


def test_timeout_is_reported():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(ScryfallServiceError, match="timed out"):
        make_service(handler).get_card_by_name("Test Card")


def test_double_faced_card_uses_face_image_and_text():
    payload = card_payload(
        name="Front // Back",
        mana_cost=None,
        oracle_text=None,
        type_line=None,
        image_uris=None,
        card_faces=[
            {"mana_cost": "{U}", "oracle_text": "Front text", "type_line": "Creature", "image_uris": {"normal": "front.png"}},
            {"mana_cost": "{1}", "oracle_text": "Back text", "type_line": "Land"},
        ],
    )
    service = make_service(lambda request: httpx.Response(200, json=payload))

    card = service.get_card_by_name("Front // Back")

    assert card is not None
    assert card.oracle_text == "Front text\nBack text"
    assert card.type_line == "Creature // Land"
    assert card.image_uris["normal"] == "front.png"


def test_background_is_commander_eligible_with_choose_a_background_pair():
    commander = ScryfallService._to_card(
        card_payload(
            name="Burakos, Party Leader",
            type_line="Legendary Creature — Orc",
            oracle_text="Choose a Background (You can have a Background as a second commander.)",
            keywords=["Choose a background"],
        )
    )
    background = ScryfallService._to_card(
        card_payload(
            name="Folk Hero",
            type_line="Legendary Enchantment — Background",
            oracle_text="Commander creatures you own have an ability.",
        )
    )

    assert ScryfallService.can_be_commander(background)
    assert ScryfallService.validate_commander_pairing([commander, background]) is None


def test_background_alone_or_without_compatible_commander_is_rejected():
    background = ScryfallService._to_card(
        card_payload(name="Folk Hero", type_line="Legendary Enchantment — Background")
    )
    unrelated = ScryfallService._to_card(
        card_payload(name="Other Commander", type_line="Legendary Creature — Human")
    )

    assert ScryfallService.validate_commander_pairing([background]) is not None
    assert ScryfallService.validate_commander_pairing([unrelated, background]) is not None


def test_bulk_lookup_uses_collection_endpoint():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/cards/named":
            return httpx.Response(404, json={"details": "not found"})
        return httpx.Response(200, json={"data": [card_payload()], "not_found": [{"name": "Missing"}]})

    result = make_service(handler).get_cards_by_names(["Test Card", "Missing"])

    assert result["test card"].name == "Test Card"
    assert result["missing"] is None
    assert len(requests) == 2
    assert requests[0].url.path == "/cards/collection"
    assert requests[1].url.path == "/cards/named"
    assert requests[1].url.params["exact"] == "Missing"


def test_bulk_lookup_maps_double_faced_card_face_names():
    payload = card_payload(
        name="Treasure Map // Treasure Cove",
        card_faces=[
            {"name": "Treasure Map", "mana_cost": "{2}"},
            {"name": "Treasure Cove", "mana_cost": ""},
        ],
    )
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [payload], "not_found": []})

    result = make_service(handler).get_cards_by_names(["Treasure Map"])

    assert result["treasure map"].name == "Treasure Map // Treasure Cove"
    assert len(requests) == 1


def test_bulk_lookup_falls_back_to_exact_name_for_split_card():
    payload = card_payload(name="Dusk // Dawn", type_line="Sorcery // Sorcery")
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/cards/collection":
            return httpx.Response(200, json={"data": [], "not_found": [{"name": "Dusk // Dawn"}]})
        return httpx.Response(200, json=payload)

    result = make_service(handler).get_cards_by_names(["Dusk // Dawn"])

    assert result["dusk // dawn"].name == "Dusk // Dawn"
    assert [request.url.path for request in requests] == ["/cards/collection", "/cards/named"]
    assert requests[1].url.params["exact"] == "Dusk // Dawn"