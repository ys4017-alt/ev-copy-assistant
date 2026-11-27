"""Check data/feature_cards.json against the manuals (needs the local PDFs).

- every card has the fields, a known brand/model/feature, and pages inside its PDF
- no digits in title/summary/caution (numbers come from ev.db only)
- no run of COPY_RUN or more words copied from the cited pages (cards are paraphrased)
"""

import json
import re
from functools import lru_cache

from pypdf import PdfReader

from retrieval import DATA, MANUALS, clean_page

COPY_RUN = 8
FEATURES = {
    "home_charging", "fast_charging", "charging_how_to", "scheduled_charging", "regen_braking",
    "adaptive_cruise", "steering_assist", "advanced_driver_assist", "route_planning", "preconditioning",
    "mobile_app", "software_updates", "security_camera", "climate_parked", "cargo_space", "towing",
    "power_outlets", "energy_tips", "cabin_climate",
}
SOURCE_OF = {(b, m): f for b, m, f in MANUALS}
# Names and official terms that contain digits but are not spec numbers.
NAMES_WITH_DIGITS = ["Model 3", "IONIQ 5", "IONIQ 6", "Level 1", "Level 2", "V2L"]


@lru_cache(maxsize=None)
def reader(filename):
    return PdfReader(DATA / "manuals" / filename)


def words(text):
    return re.findall(r"[a-z]+", text.lower())


def ngrams(ws, n):
    return {tuple(ws[i:i + n]) for i in range(len(ws) - n + 1)}


def check(card):
    problems = []
    key = (card["brand"], card["model"])
    if SOURCE_OF.get(key) != card["source"]:
        problems.append(f"source should be {SOURCE_OF.get(key)}")
        return problems
    if card["feature"] not in FEATURES:
        problems.append(f"unknown feature {card['feature']}")
    prefix = {"Tesla": "TSL", "Hyundai": "HYU", "Chevrolet": "CHV"}[card["brand"]]
    if not (card["card_id"].startswith(prefix + "-") and card["card_id"].endswith("-" + card["feature"])):
        problems.append(f"card_id should look like {prefix}-<model>-{card['feature']}")
    text = " ".join([card["title"], card["summary"], card["caution"]])
    for name in NAMES_WITH_DIGITS:
        text = text.replace(name, "")
    if re.search(r"\d", text):
        problems.append("contains a digit")
    n_pages = len(reader(card["source"]).pages)
    page_words = []
    for p in card["pages"]:
        if not 1 <= p <= n_pages:
            problems.append(f"page {p} outside 1..{n_pages}")
            continue
        page_words += words(clean_page(reader(card["source"]).pages[p - 1].extract_text()))
    copied = ngrams(words(card["summary"]), COPY_RUN) & ngrams(page_words, COPY_RUN)
    if copied:
        problems.append(f"copies {len(copied)} {COPY_RUN}-word runs, e.g. '{' '.join(next(iter(copied)))}'")
    if not 2 <= len(re.findall(r"[.!?](?:\s|$)", card["summary"])) <= 4:
        problems.append("summary should be 2-4 sentences")
    return problems


def main():
    cards = json.loads((DATA / "feature_cards.json").read_text())["cards"]
    ids = [c["card_id"] for c in cards]
    assert len(ids) == len(set(ids)), "duplicate card_id"
    bad = 0
    for card in cards:
        for p in check(card):
            bad += 1
            print(f"{card['card_id']}: {p}")
    per_model = {}
    for c in cards:
        per_model[c["model"]] = per_model.get(c["model"], 0) + 1
    print(f"{len(cards)} cards {per_model}; {bad} problems")
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
