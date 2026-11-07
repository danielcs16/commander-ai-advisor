import logging
import time

import streamlit as st

from config.settings import get_settings
from models.bracket import Bracket
from models.card import CardData
from prompts.deck_analysis import MAX_PROMPT_CANDIDATES
from services.bracket_service import BracketService
from services.candidate_service import CandidateService
from services.deck_analyzer import DeckAnalyzer
from services.deck_parser import DeckParseError, DeckParser
from services.deck_validator import DeckValidator
from services.edhrec_service import EDHRecService
from services.llm_service import LLMService, LLMServiceError
from services.recommendation_validator import RecommendationValidator
from services.scryfall_service import ScryfallService, ScryfallServiceError
from utils.cache import ProviderCache
from utils.logger import get_logger


st.set_page_config(page_title="Commander AI Deck Advisor", page_icon="♜", layout="wide")
st.title("Commander AI Deck Advisor")
st.caption("Scryfall card facts · EDHREC trends · bracket-aware strategy")

COLOR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
SERVICE_CACHE_VERSION = "edhrec-current-page-fallback-v4"


def _bracket_label(value: Bracket) -> str:
    name = "cEDH" if value == Bracket.CEDH else value.name.title()
    return f"{int(value)} - {name}"


@st.cache_resource
def get_services(cache_version: str):
    settings = get_settings()
    cache = ProviderCache(settings.cache_ttl_seconds)
    scryfall = ScryfallService(cache=cache)
    edhrec = EDHRecService(cache=cache)
    return scryfall, edhrec


def _read_commander_names(value: str) -> list[str]:
    return DeckParser().parse_names(value)


def _display_card(card: CardData | None, name: str) -> None:
    if card is None:
        st.markdown(f"**{name}**")
        return
    image = card.image_uris.get("normal") or card.image_uris.get("large") or card.image_uris.get("small")
    if image:
        st.image(image, width=220)
    st.markdown(f"**{card.name}**")
    if card.mana_cost:
        st.caption(card.mana_cost)
    if card.type_line:
        st.caption(card.type_line)
    if card.price_usd is not None:
        st.caption(f"Indicative price: ${card.price_usd:.2f}")


def _show_analysis(analysis, cards, commanders, stats, target, rejected, candidates) -> None:
    identity_codes = {color for commander in commanders for color in commander.color_identity}
    identity = [COLOR_NAMES.get(color, color) for color in "WUBRG" if color in identity_codes]
    current = analysis.current_bracket_estimate
    first, second, third = st.columns(3)
    first.metric("Commander(s)", " + ".join(card.name for card in commanders))
    second.metric("Color Identity", " / ".join(identity) if identity else "Colorless")
    third.metric("Target Bracket", _bracket_label(target))
    st.metric("Estimated Current Bracket", f"{current}" if current else "Unavailable")

    st.subheader("Strategy")
    st.write(", ".join(analysis.detected_strategy) if analysis.detected_strategy else "No strategy labels returned.")
    strengths, weaknesses = st.columns(2)
    with strengths:
        st.markdown("**Strengths**")
        for item in analysis.strengths:
            st.write(f"- {item}")
    with weaknesses:
        st.markdown("**Weaknesses**")
        for item in analysis.weaknesses:
            st.write(f"- {item}")

    st.subheader("Deck Profile")
    left, right = st.columns(2)
    with left:
        st.metric("Lands", stats.lands)
        st.metric("Average Mana Value", f"{stats.average_mana_value:.2f}" if stats.average_mana_value is not None else "N/A")
        st.markdown("**Mana Curve**")
        st.bar_chart(stats.mana_curve)
    with right:
        st.metric("Ramp", len(stats.categories.get("Ramp", [])))
        st.metric("Card Draw", len(stats.categories.get("Card Draw", [])))
        st.metric("Interaction", len(stats.categories.get("Counterspell", [])) + len(stats.categories.get("Removal", [])))
        st.metric("Removal", len(stats.categories.get("Removal", [])))
        st.metric("Board Wipes", len(stats.categories.get("Board Wipe", [])))
        st.metric("Win Conditions", len(stats.categories.get("Win Condition", [])))
    with st.expander("Deterministic card categories"):
        for category, names in stats.categories.items():
            st.write(f"**{category}:** {', '.join(names)}")

    st.subheader("Recommended Changes")
    candidate_by_name = {candidate.name.casefold(): candidate for candidate in candidates}
    card_by_name = {card.name.casefold(): card for card in cards}
    for index, change in enumerate(analysis.changes, start=1):
        st.markdown(f"**{index}. {change.change_type} · {change.priority}**")
        remove_col, arrow_col, add_col = st.columns([1, 0.15, 1])
        with remove_col:
            st.caption("REMOVE")
            _display_card(card_by_name.get(change.remove.casefold()), change.remove)
        with arrow_col:
            st.markdown("### →")
        with add_col:
            st.caption("ADD")
            candidate = candidate_by_name.get(change.add.casefold())
            card_data = CardData.model_validate(candidate.card_data) if candidate else None
            _display_card(card_data, change.add)
        st.write(f"**Category:** {change.category}  ·  **Why:** {change.reason}")
        synergy = candidate_by_name.get(change.add.casefold())
        if synergy and synergy.edhrec_synergy is not None:
            st.caption(f"EDHREC synergy: {synergy.edhrec_synergy:g}")
        st.divider()

    st.subheader("Summary")
    st.write(analysis.final_summary)
    if rejected:
        st.info(f"{len(rejected)} invalid card-change suggestion(s) were discarded. Details are recorded in the application log.")


decklist = st.text_area(
    "Paste your Commander decklist",
    height=260,
    placeholder="1 Sol Ring\n1 Arcane Signet\n1 Command Tower\n1 Counterspell",
)
commander_text = st.text_area("Commander(s), one per line", height=72, placeholder="Leave blank to try automatic detection")
bracket_service = BracketService()
target_bracket = st.selectbox(
    "Qual bracket você deseja para este deck?",
    list(Bracket),
    format_func=_bracket_label,
    index=1,
)
st.caption(bracket_service.get_rules(target_bracket).description)

if st.button("Analyze Deck", type="primary", icon="🔎"):
    logger = get_logger()
    started_at = time.monotonic()
    try:
        entries = DeckParser().parse(decklist)
    except DeckParseError as exc:
        st.error(str(exc))
        st.stop()

    commander_names = _read_commander_names(commander_text)
    requested_names = list(dict.fromkeys([entry.name for entry in entries] + commander_names))
    logger.info("Starting deck analysis: bracket=%s cards=%d", int(target_bracket), sum(entry.quantity for entry in entries))
    try:
        scryfall, edhrec = get_services(SERVICE_CACHE_VERSION)
        resolved = scryfall.get_cards_by_names(requested_names)
    except ScryfallServiceError as exc:
        st.error(f"Scryfall validation could not be completed. No LLM analysis was run. {exc}")
        st.stop()

    unknown = [name for name in requested_names if resolved.get(name.casefold()) is None]
    if unknown:
        st.error("Scryfall could not resolve these exact card names. Correct the list before analysis: " + ", ".join(unknown))
        st.stop()

    cards: list[CardData] = []
    for entry in entries:
        card = resolved[entry.name.casefold()]
        cards.append(card.model_copy(update={"quantity": entry.quantity}))

    if not commander_names:
        possible = [
            card for card in cards
            if card.quantity == 1 and scryfall.can_be_commander(card)
        ]
        if len(possible) == 1:
            commander_names = [possible[0].name]
        else:
            choices = ", ".join(card.name for card in possible) or "none confidently identified"
            st.error(f"Commander detection is ambiguous ({choices}). Enter the Commander(s) above.")
            st.stop()

    commanders = [resolved[name.casefold()] for name in commander_names]
    invalid_commanders = [card.name for card in commanders if not scryfall.can_be_commander(card)]
    if invalid_commanders:
        st.error("These cards are not identified by Scryfall as potential Commanders: " + ", ".join(invalid_commanders))
        st.stop()
    illegal_commanders = [card.name for card in commanders if card.commander_legal is not True]
    if illegal_commanders:
        st.error("These Commanders are not confirmed legal in Commander: " + ", ".join(illegal_commanders))
        st.stop()
    pairing_error = scryfall.validate_commander_pairing(commanders)
    if pairing_error:
        st.error(pairing_error)
        st.stop()
    for commander in commanders:
        if commander.name.casefold() not in {card.name.casefold() for card in cards}:
            cards.append(commander)

    report = DeckValidator().validate(cards, commanders)
    stats = DeckAnalyzer().analyze(cards)
    current_bracket = bracket_service.estimate(stats)
    if report.errors:
        with st.expander(f"Deck validation errors ({len(report.errors)})", expanded=True):
            for error in report.errors:
                st.error(error)
    if report.warnings:
        with st.expander(f"Deck validation warnings ({len(report.warnings)})"):
            for warning in report.warnings:
                st.warning(warning)

    llm = None
    try:
        candidates = CandidateService(edhrec, scryfall).generate(commanders[0].name, commanders, cards)
        llm_candidates = candidates[:MAX_PROMPT_CANDIDATES]
        if not candidates:
            st.warning("EDHREC did not provide any Scryfall-validated candidates. Card-change recommendations will be omitted.")
        llm = LLMService()
        payload = {
            "commanders": [card.name for card in commanders],
            "deck": [card.model_dump() for card in cards],
            "deterministic_stats": stats.model_dump(),
            "validation": report.model_dump(),
            "estimated_current_bracket": current_bracket,
            "current_bracket_rules": bracket_service.get_rules(current_bracket).model_dump(),
            "target_bracket": int(target_bracket),
            "target_bracket_rules": bracket_service.get_rules(target_bracket).model_dump(),
            "candidate_list": [candidate.model_dump() for candidate in llm_candidates],
        }
        analysis = llm.analyze(payload)
        analysis.commanders = [card.name for card in commanders]
        analysis.current_bracket_estimate = current_bracket
        analysis.target_bracket = int(target_bracket)
        analysis, rejected = RecommendationValidator(scryfall).validate(
            analysis,
            cards,
            commanders,
            llm_candidates,
        )
        for item in rejected:
            logger.warning("RecommendationRejected remove=%s add=%s reason=%s", item.remove, item.add, item.reason)
        _show_analysis(analysis, cards, commanders, stats, target_bracket, rejected, llm_candidates)
    except LLMServiceError as exc:
        st.error(str(exc))
    except ScryfallServiceError as exc:
        st.error(f"Scryfall validation failed. Recommendations were not displayed as valid. {exc}")
    finally:
        if llm is not None:
            llm.close()
        logger.info("Deck analysis finished in %.2fs", time.monotonic() - started_at)