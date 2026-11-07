# Commander AI Deck Advisor

Streamlit application for Commander/EDH deck review. The analysis combines deterministic card/deck facts from Scryfall, popularity and synergy data from EDHREC, and strategic interpretation from an OpenAI model. It does not use the LLM as a source of card facts.

## Architecture

`app.py` orchestrates the user workflow. `services/` contains the parser, deterministic analyzer and validator, bracket rules, candidate pipeline, recommendation validation, and provider adapters. Pydantic models in `models/` define card, deck, bracket, and structured LLM data. Provider caches are namespaced in `utils/cache.py`.

## Install and configure

Use Python 3.12 or newer:

```powershell
python -m venv .venv
& ./.venv/Scripts/Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` and optionally `OPENAI_MODEL` in `.env`. Never commit `.env`. Scryfall and EDHREC do not require credentials.

## Analysis flow

1. `DeckParser` accepts one card per line, optionally prefixed by a quantity (`1 Card`, `1x Card`, or `Card`), and strips trailing set/collector metadata such as `(BLC) 264`. Invalid lines are reported rather than silently corrected.
2. `ScryfallService` resolves deck and Commander names using the Scryfall collection endpoint in batches (up to 75 identifiers), caches results, and supplies objective card details and Commander legality.
3. `DeckValidator`, `DeckAnalyzer`, and `BracketService` calculate validation findings, deck statistics/categories, and an approximate current bracket before the model is called.
4. `EDHRecService` wraps the documented `pyedhrec` methods. If the installed wrapper's data build is unavailable, it falls back to the public commander page and extracts displayed card names/categories only; absent synergy or inclusion metrics remain unavailable rather than being fabricated.
5. `CandidateService` resolves EDHREC suggestions with Scryfall and removes unknown, illegal, out-of-identity, and already-in-deck cards.
6. `LLMService` requests a Pydantic structured response. `RecommendationValidator` then checks removals and additions against the deck, candidate list, Scryfall legality, and Commander color identity. Model-supplied synergy is replaced with the candidate's EDHREC value.

If Scryfall cannot finish validation or exact card names cannot be resolved, the application stops before sending the deck to the LLM. If both EDHREC methods and its public commander page are unavailable, the UI warns that no card changes can be recommended and the LLM receives no candidates; provider statistics are never fabricated. The adapters use bounded timeouts and the system certificate store.

## Source responsibilities

- **Scryfall:** canonical card name, Oracle text, mana value, colors/color identity, types, keywords, legalities, prices, and images.
- **EDHREC:** commander card lists, synergy/popularity data, average deck, and combo data where returned by the library.
- **LLM:** strategy interpretation, strengths/weaknesses, and explanations for proposed changes. It may only select additions from the validated candidate list.

Bracket descriptions and expectations are centralized and can be overridden by passing a replacement rule set to `BracketService`. Current bracket estimation is a heuristic, not an official Wizards rating; the `game_changers` rule field is ready for an updated curated list and is not populated with guessed data.

## Run

From this directory:

```powershell
streamlit run app.py
```

Paste one card per line. The Commander field accepts one card name per line and can hold multiple Commanders. If left blank, the app only auto-detects one unambiguous potential Commander.

## Tests

Tests use mocks and do not call Scryfall, EDHREC, or OpenAI:

```powershell
pytest
```