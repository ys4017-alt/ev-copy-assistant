"""Checks for generated ad copy.

check_rules(): deterministic rules from the brand guides (free, instant).

    python check.py    # self-check: past ads in ev.db — off-brand ones must be flagged, approved ones must pass
"""

import math
import re
import sqlite3
from functools import lru_cache

from retrieval import BRANDS, COPY_FIELDS, DATA, DB_PATH, GUIDES, MODEL_BRAND, get_specs

LIMITS = {"social": {"headline": 40, "text": 125}, "search": {"headline": 30, "description": 90},
          "email": {"subject": 50, "preheader": 90}}
EMAIL_WORDS = (120, 200)
SPEC_FIELDS = ["variant", "range_miles", "battery_capacity_kwh", "charging_speed_kw", "acceleration_0_60_mph",
               "top_speed_mph", "price_usd", "drive_type", "seating_capacity", "cargo_volume_cubic_ft",
               "warranty_years"]

# Feature names that belong to one brand; the other brands must not use them.
# Completes each guide's "other brands' feature names" line (e.g. Supercharger is in no list).
FEATURE_OWNER = {
    "Supercharger": "Tesla", "Autosteer": "Tesla", "Traffic-Aware Cruise Control": "Tesla",
    "Full Self-Driving": "Tesla", "Sentry Mode": "Tesla", "Trip Planner": "Tesla", "Autopilot": "Tesla",
    "i-PEDAL": "Hyundai", "V2L": "Hyundai", "Bluelink": "Hyundai", "Smart Cruise Control": "Hyundai",
    "Highway Driving Assist": "Hyundai", "Lane Following Assist": "Hyundai",
    "Super Cruise": "Chevrolet", "One-Pedal Driving": "Chevrolet", "Regen on Demand": "Chevrolet",
    "PowerBase": "Chevrolet", "OnStar": "Chevrolet", "Midgate": "Chevrolet",
}
# Driver-assistance names per brand: any of them in copy needs an attention line.
ASSIST_NAMES = {
    "Tesla": ["Autosteer", "Traffic-Aware Cruise Control", "Full Self-Driving"],
    "Hyundai": ["Smart Cruise Control", "Lane Following Assist", "Lane Keeping Assist", "Highway Driving Assist"],
    "Chevrolet": ["Super Cruise", "Adaptive Cruise Control", "Lane Keep Assist"],
}
ATTENTION = re.compile(r"pay attention|stay(s)? (alert|attentive|in control)|hands on the wheel|"
                       r"driver (must|stays|remains)|supervis", re.I)
NAME_DIGITS = re.compile(r"\b(Model 3|IONIQ [56]|Level [12]|V2L|0[-–]60)\b", re.I)
NON_DRIVING_HANDS_FREE = re.compile(r"liftgate|trunk|tailgate|phone|call|voice", re.I)


@lru_cache(maxsize=None)
def banned_terms(brand):
    """Plain banned terms from the guide's section 3.3; conditional bullets are coded in check_rules."""
    text = (DATA / GUIDES[brand]).read_text()
    block = text.split("### 3.3", 1)[1].split("\n#", 1)[0]
    terms = []
    for line in block.splitlines():
        if not line.startswith("- ") or " without " in line:
            continue
        line = line[2:].split(" — ")[0].split(" (")[0].replace("other brands' feature names:", "")
        for term in line.split(","):
            term = term.strip().strip('"')
            if term and not term.startswith(("or ", "competitor")):
                terms.append(term)
    return terms


def _has(term, text):
    if not term[0].isalnum():  # "#1"
        return term.lower() in text.lower()
    return re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text, re.I) is not None


def _sentences(text):
    return re.split(r"(?<=[.!?])\s+", text)


def number_problems(text, model):
    spec = get_specs(model) if model else None
    allowed = set()
    for f in SPEC_FIELDS:
        v = (spec or {}).get(f)
        if isinstance(v, (int, float)):
            whole = math.floor(v + 0.5)  # round half up: Python's round(50.5) is 50
            allowed |= {str(v), str(whole), str(round(v, 1)), f"{whole:,}", f"{v:,.2f}"}
    # Models often write "Level 2" or "0-60" with a no-break space or a Unicode hyphen.
    text = re.sub(r"[\u00a0\u202f]", " ", re.sub(r"[\u2010-\u2015]", "-", text))
    found = re.findall(r"\d[\d,]*(?:\.\d+)?", NAME_DIGITS.sub(" ", text))
    return [x for x in found if x.rstrip(".,") not in allowed]


def check_rules(variant, brand, channel, model=None, cards=None):
    """List of rule problems for one variant (empty = pass)."""
    fields = COPY_FIELDS[channel]
    copy = " ".join(variant.get(f, "") for f in fields)
    full = copy + " " + variant.get("disclaimer", "")
    problems = []

    for field, limit in LIMITS[channel].items():
        if len(variant.get(field, "")) > limit:
            problems.append(f"length: {field} is {len(variant[field])} chars (max {limit})")
    if channel == "email":
        n = len(variant.get("body", "").split())
        if not EMAIL_WORDS[0] <= n <= EMAIL_WORDS[1]:
            problems.append(f"length: body is {n} words ({EMAIL_WORDS[0]}-{EMAIL_WORDS[1]})")

    for term in banned_terms(brand):
        if _has(term, copy):
            problems.append(f"banned: '{term}'")
    for name, owner in FEATURE_OWNER.items():
        if owner != brand and _has(name, copy) and f"banned: '{name}'" not in problems:
            problems.append(f"other brand's feature: '{name}' ({owner})")
    for m, owner in MODEL_BRAND.items():
        if owner != brand and _has(m, copy):
            problems.append(f"competitor model: '{m}'")
    for other in BRANDS:
        if other != brand and _has(other, copy) and f"banned: '{other}'" not in problems:
            problems.append(f"competitor brand: '{other}'")

    if brand == "Tesla":
        if re.search(r"Full Self-Driving(?! \(Supervised\))", copy):
            problems.append("Full Self-Driving without '(Supervised)'")
        if _has("FSD", copy):
            problems.append("banned: 'FSD'")
    for sentence in _sentences(copy):
        if not _has("hands-free", sentence) or NON_DRIVING_HANDS_FREE.search(sentence):
            continue
        if brand == "Chevrolet" and not (_has("Super Cruise", sentence) and "compatible road" in sentence.lower()):
            problems.append("hands-free without 'Super Cruise' and 'compatible roads' in the same sentence")
        elif brand == "Hyundai":
            problems.append("hands-free used about driving")

    if re.search(r"\d[\d,]*\s*(mi|miles)\b|\brange of \d", copy, re.I) and "actual range varies" not in full.lower():
        problems.append("range stated without 'Actual range varies...' disclaimer")
    if any(_has(n, copy) for n in ASSIST_NAMES[brand]) and not ATTENTION.search(full):
        problems.append("driver assistance named without an attention/supervision line")
    if brand == "Hyundai" and _has("V2L", copy) and not re.search(r"reduc\w*.{0,40}range|range.{0,40}reduc|lowers? range", full, re.I):
        problems.append("V2L without noting it reduces driving range")

    if copy.count("!") > 1:
        problems.append("more than one exclamation mark")
    for head in ("headline", "subject"):
        if "!" in variant.get(head, ""):
            problems.append(f"exclamation mark in {head}")
    if brand == "Hyundai" and re.search(r"\bIoniq\b", copy):
        problems.append("write 'IONIQ' in capitals")

    bad_numbers = number_problems(copy, model)
    if bad_numbers:
        problems.append(f"numbers not in specs: {bad_numbers}")
    if cards is not None:
        unknown = set(variant.get("sources", [])) - set(cards)
        if unknown:
            problems.append(f"cites cards it was not given: {sorted(unknown)}")
    return problems


@lru_cache(maxsize=None)
def voice_traits(brand):
    """'### 1.1 Direct' ... -> {'Direct': '<that subsection>'} from the guide's Brand Voice section."""
    text = (DATA / GUIDES[brand]).read_text()
    out = {}
    for block in text.split("\n### ")[1:]:
        head, _, body = block.partition("\n")
        if re.match(r"1\.\d ", head):
            out[head.split(" ", 1)[1].strip()] = body.split("\n## ")[0].strip()
    return out


def judge(texts, brand, cards, specs, tone=False):
    """Grounding (and optionally voice) review by an LLM other than the writer.

    texts: copy strings to review. cards: basket card dicts (card_id, text, caution).
    Returns one dict per text: {"claims": [{"claim", "supported", "evidence"}], "tone": {trait: 1-5}}.
    """
    from generate import FALLBACK_MODEL, MODEL, chat_json  # generate imports this module

    card_text = "\n".join(f"[{c['card_id']}] {c['text']}" for c in cards)
    numbered = "\n".join(f"TEXT {i + 1}: {t}" for i, t in enumerate(texts))
    tone_rule = ""
    if tone:
        traits = voice_traits(brand)
        tone_rule = ("\nAlso score each text from 1 (poor) to 5 (excellent) on each voice trait below, as "
                     "\"tone\": {trait: score}.\n" + "\n".join(f"- {k}: {v}" for k, v in traits.items()))
    system = (
        "You are a strict fact-checker for car ad copy. Split each TEXT into its factual claims about the "
        "vehicle: features, how they behave, and numbers. Skip mood, style and calls to action. "
        "A claim is supported only if the FEATURE CARDS or SPECS below state it. Outside knowledge does not "
        "count, even when true. Mark a claim unsupported when it adds a capability, behavior, device, "
        "component or number that no card or spec states, or when it contradicts a card. "
        "These are still supported: numbers rounded from SPECS (7.31 -> about 7), everyday usage scenes and "
        "benefits that follow from a stated feature (camping, errands, long drives), and plain paraphrase. "
        "Return JSON only: {\"results\": [{\"claims\": [{\"claim\": ..., \"supported\": true|false, "
        "\"evidence\": card id or \"SPECS\" or \"none\"}]" + (", \"tone\": {...}" if tone else "") +
        "}]} with one result per TEXT, in order." + tone_rule)
    user = f"# FEATURE CARDS\n{card_text}\n\n# SPECS\n{specs}\n\n# TEXTS\n{numbered}"
    parsed, _, _ = chat_json([{"role": "system", "content": system}, {"role": "user", "content": user}],
                             models=(FALLBACK_MODEL, MODEL))
    results = parsed.get("results", []) if isinstance(parsed, dict) else parsed
    results = (results + [{"claims": []}] * len(texts))[:len(texts)]
    return [{"claims": r.get("claims", []), "tone": r.get("tone", {})} for r in results]


def unsupported(review):
    return [c["claim"] for c in review["claims"] if not c.get("supported")]


def calibrate():
    """Agreement between judge() and the labelled claims in data/judge_labels.json."""
    import json
    import time
    from generate import spec_text

    labels = json.loads((DATA / "judge_labels.json").read_text())["claims"]
    all_cards = {c["card_id"]: c for c in json.loads((DATA / "feature_cards.json").read_text())["cards"]}
    groups = {}
    for lab in labels:
        groups.setdefault((lab["brand"], lab["model"], tuple(lab["cards"])), []).append(lab)
    agree, rows = 0, []
    for n, ((brand, model, card_ids), labs) in enumerate(groups.items()):
        if n:
            time.sleep(8)  # stay inside the free tier's tokens-per-minute limit
        cards = [{"card_id": i, "text": f"{all_cards[i]['title']}. {all_cards[i]['summary']}"} for i in card_ids]
        reviews = judge([l["claim"] for l in labs], brand, cards, spec_text(model))
        for lab, rev in zip(labs, reviews):
            verdict = not unsupported(rev)
            agree += verdict == lab["supported"]
            rows.append((lab, verdict))
    n_unsup = sum(not l["supported"] for l, _ in rows)
    caught = sum(not l["supported"] and not v for l, v in rows)
    false_alarm = sum(l["supported"] and not v for l, v in rows)
    print(f"judge agreement: {agree}/{len(rows)} = {agree / len(rows):.0%} | unsupported caught {caught}/{n_unsup} | "
          f"false alarms {false_alarm}/{len(rows) - n_unsup}")
    for lab, verdict in rows:
        if verdict != lab["supported"]:
            print(f"  DISAGREE {lab['id']} label={lab['supported']} judge={verdict}: {lab['claim']}")


def self_check():
    """Past ads: every off-brand ad must be flagged; every approved ad must pass."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    ads = [dict(r) for r in con.execute("SELECT * FROM ads")]
    caught, passed, wrong = 0, 0, []
    for ad in ads:
        variant = {f: ad[f] for f in COPY_FIELDS[ad["channel"]]}
        variant["disclaimer"] = ad.get("disclaimer") or ""
        problems = check_rules(variant, ad["brand"], ad["channel"], ad["model"])
        if ad["approved"]:
            passed += not problems
        else:
            caught += bool(problems)
        if bool(problems) == bool(ad["approved"]):
            wrong.append(f"{ad['ad_id']} approved={ad['approved']} -> {problems or 'no problems'}")
        elif not ad["approved"]:
            print(f"  caught {ad['ad_id']}: {problems}")
    n_bad = sum(not a["approved"] for a in ads)
    print(f"off-brand ads caught: {caught}/{n_bad}; approved ads passing: {passed}/{len(ads) - n_bad}")
    for w in wrong:
        print("  WRONG", w)
    return not wrong


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["judge"]:
        calibrate()
        raise SystemExit(0)
    for b in BRANDS:
        print(b, "banned terms from guide 3.3:", banned_terms(b))
    raise SystemExit(0 if self_check() else 1)
