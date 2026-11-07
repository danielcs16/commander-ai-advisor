import httpx

from services.edhrec_service import EDHRecService
from utils.cache import ProviderCache


class FakeEDHRec:
    def __init__(self):
        self.calls = 0

    def get_commander_data(self, commander):
        self.calls += 1
        return {"commander": commander}

    def get_card_combos(self, commander):
        return {"combos": []}

    def get_commanders_average_deck(self, commander):
        return {"decklist": []}


def test_calls_documented_methods_and_caches_results():
    client = FakeEDHRec()
    service = EDHRecService(client=client, cache=ProviderCache())

    assert service.get_commander_data("Test Commander") == {"commander": "Test Commander"}
    assert service.get_commander_data("Test Commander") == {"commander": "Test Commander"}
    assert client.calls == 1
    assert service.get_commander_combos("Test Commander") == {"combos": []}
    assert service.get_average_deck("Test Commander") == {"decklist": []}


def test_missing_method_and_provider_error_degrade_to_empty_data():
    class BrokenEDHRec:
        def get_commander_data(self, commander):
            raise TimeoutError("offline")

    service = EDHRecService(client=BrokenEDHRec())
    assert service.get_commander_data("Unavailable") == {}
    assert service.get_top_cards("Unavailable") == {}


def test_current_page_fallback_parses_categories_and_caches_page():
    html = """
    <div>
      <a class="sticky"></a>
      <div class="heading">Instants</div>
      <div class="content"><div><ul class="cards_grid">
        <li><a href="/cards/swords-to-plowshares"><span>Swords to Plowshares</span></a></li>
        <li><a href="/cards/anguished-unmaking"><span>Anguished Unmaking</span></a></li>
      </ul></div></div>
    </div>
    """
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=html)

    class LegacyEDHRec:
        @staticmethod
        def format_card_name(commander):
            return commander.lower().replace(" ", "-").replace("'", "").replace(",", "")

        def get_build_id(self):
            return None

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://edhrec.com",
    )
    service = EDHRecService(client=LegacyEDHRec(), http_client=http_client, cache=ProviderCache())

    result = service.get_all_commander_data("Nalia de'Arnise")
    cached_result = service.get_all_commander_data("Nalia de'Arnise")

    assert result == cached_result
    assert [request.url.path for request in requests] == ["/commanders/nalia-dearnise"]
    records = result["commander_page_recommendations"]["Instants"]
    assert [record["name"] for record in records] == ["Swords to Plowshares", "Anguished Unmaking"]
    assert all(record["edhrec_source"] == "Instants" for record in records)
    assert all("synergy" not in record and "inclusion" not in record for record in records)