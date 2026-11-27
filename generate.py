"""Write ad copy from a brief, grounded in feature cards, spec numbers and the brand guide.

    python generate.py     # self-check: 6 briefs (3 brands x 2 channels)

The LLM call follows the course's M7 pattern: the openai SDK with a provider's base_url.
"""

import json
import os
import re
import time
from functools import lru_cache

from openai import APIError, OpenAI, RateLimitError

from check import EMAIL_WORDS, LIMITS, SPEC_FIELDS, check_rules
from retrieval import (COPY_FIELDS, DATA, GUIDES, GUIDE_MODEL_HEADINGS, HERE, detect_model,
                       get_examples, get_specs, retrieve_for_copy)

PROVIDER = {"base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY"}
MODEL = "openai/gpt-oss-120b"
FALLBACK_MODEL = "qwen/qwen3.8-27b"  # used when the main model errors (rate limit, outage)
N_VARIANTS = 2
K_CARDS = 5  # 3 left gaps the model filled from its own knowledge

CHANNEL_SECTION = {"social": "6.1", "search": "6.2", "email": "6.3"}
# Guide sections sent with every request: rules are applied every time, not searched for.
ALWAYS_SECTIONS = ["1.", "2.", "3.", "4."]
# ev.db model -> name written in copy (Hyundai styles IONIQ in capitals).
COPY_NAME = {v: k for k, v in GUIDE_MODEL_HEADINGS.items()}


def _api_key():
    if os.environ.get(PROVIDER["key_env"]):
        return os.environ[PROVIDER["key_env"]]
    env_file = HERE / ".env"  # local runs; the Docker image has no .env
    for line in (env_file.read_text().splitlines() if env_file.exists() else []):
        if line.startswith(PROVIDER["key_env"] + "="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{PROVIDER['key_env']} is not set in the environment or project/.env")


@lru_cache(maxsize=1)
def _client():
    # The httpx2 in this environment cannot decode Groq's default compression; gzip works.
    # max_retries=0: on a rate limit, switch to the fallback model instead of waiting.
    return OpenAI(api_key=_api_key(), base_url=PROVIDER["base_url"], max_retries=0,
                  default_headers={"Accept-Encoding": "gzip"})


@lru_cache(maxsize=None)
def guide_sections(brand):
    """Heading title -> that heading's text, including its subsections."""
    lines = (DATA / GUIDES[brand]).read_text().splitlines()
    heads = [(i, len(l) - len(l.lstrip("#")), l.lstrip("#").strip())
             for i, l in enumerate(lines) if l.startswith("## ") or l.startswith("### ")]
    out = {}
    for n, (i, level, title) in enumerate(heads):
        end = next((j for j, lv, _ in heads[n + 1:] if lv <= level), len(lines))
        out[title] = "\n".join(lines[i:end]).strip()
    return out


def guide_text(brand, channel, model):
    sections = guide_sections(brand)
    # "## 1." etc. already contain their ### subsections.
    parts = [sections[t] for t in sections if t.split()[0] in ALWAYS_SECTIONS]
    parts += [sections[t] for t in sections if t.startswith(CHANNEL_SECTION[channel] + " ")]
    heading = COPY_NAME.get(model, model)
    if model and heading in sections:
        parts.append("### Model messaging: " + sections[heading].split("\n", 1)[1])
    return "\n\n".join(parts)


def spec_text(model):
    spec = get_specs(model) if model else None
    if not spec:
        return "No model selected: do not state any numbers."
    lines = [f"- {f}: {round(spec[f], 2) if isinstance(spec[f], float) else spec[f]}" for f in SPEC_FIELDS]
    return f"{spec['brand']} {model} ({spec['year']}), synthetic class dataset:\n" + "\n".join(lines)


def build_messages(brief, brand, channel, model=None, n=N_VARIANTS):
    """Fill the basket: feature cards, spec numbers, brand rules and approved past ads."""
    # A model chosen in the UI but not named in the brief still narrows the card search.
    query = brief if not model or detect_model(brief) == model else f"{COPY_NAME.get(model, model)} {brief}"
    found = retrieve_for_copy(query, brand, k_cards=K_CARDS)
    model = model or found["model"]
    cards = [h[1] for h in found["cards"]]
    examples = get_examples(brand, model or "", channel)
    fields = COPY_FIELDS[channel]
    card_text = "\n".join(f"[{c['card_id']}] {c['text']} (Caution: {c['caution'] or 'none'})" for c in cards)
    example_text = "\n".join(json.dumps({f: e[f] for f in fields}, ensure_ascii=False) for e in examples)
    system = (
        f"You are a senior copywriter for {brand}'s electric vehicles. Write ad copy that follows the brand guide "
        "exactly. Ground every feature claim in the FEATURE CARDS and respect each card's Caution. "
        "Use numbers only from SPECS, written as given (you may round to a whole number); never invent a number. "
        "If the cards do not support a claim, leave it out. "
        "Do not write any other number, including times of day or counts. "
        "Disclaimers (range, supervision, availability) go in the separate \"disclaimer\" field, not in the copy. "
        f"Return JSON only: {{\"variants\": [{{{', '.join(repr(f) + ': ...' for f in fields)}, "
        "\"disclaimer\": ..., \"sources\": [card ids used]}}]}} with exactly "
        f"{n} variants that take clearly different angles.\n\n# BRAND GUIDE\n{guide_text(brand, channel, model)}")
    limits = [f"{f}: at most {c} characters" for f, c in LIMITS[channel].items()]
    if channel == "email":
        limits.append(f"body: {EMAIL_WORDS[0]}-{EMAIL_WORDS[1]} words")
    user = (f"BRIEF: {brief}\nCHANNEL: {channel}\nMODEL: {COPY_NAME.get(model, model) or 'not specified'}\n"
            f"HARD LIMITS (count before answering): {'; '.join(limits)}\n\n"
            f"# FEATURE CARDS\n{card_text}\n\n# SPECS\n{spec_text(model)}\n\n"
            f"# APPROVED PAST ADS (same brand and channel; match the voice, do not copy)\n{example_text or 'none'}")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}], cards, model


def _call(model_name, messages):
    kwargs = {"model": model_name, "messages": messages, "max_tokens": 1500,
              "response_format": {"type": "json_object"}}
    if model_name.startswith("openai/gpt-oss"):
        kwargs["reasoning_effort"] = "low"  # keeps latency under the 3 s target
    return _client().chat.completions.create(**kwargs)


def chat_json(messages, models=(MODEL, FALLBACK_MODEL)):
    """Ask the first model that answers; return (parsed JSON, model used, total tokens).

    If every model is rate-limited, wait once for the reset Groq reports, then try again.
    """
    wait = 10
    for attempt in range(2):
        for i, name in enumerate(models):
            try:
                resp = _call(name, messages)
                break
            except RateLimitError as e:
                wait = float(e.response.headers.get("retry-after", 10))
            except APIError:
                if i == len(models) - 1 and attempt:
                    raise
        else:
            if attempt:
                raise RuntimeError("all models rate-limited after waiting")
            time.sleep(min(wait, 30) + 1)
            continue
        break
    raw = re.sub(r"<think>.*?</think>", "", resp.choices[0].message.content or "", flags=re.S)
    return json.loads(raw), name, resp.usage.total_tokens


def generate(brief, brand, channel, model=None, n=N_VARIANTS, previous=None, feedback=None):
    """Return {"variants", "model", "cards", "basket", "llm", "seconds", "tokens"}.

    previous + feedback: a rewrite. The earlier variants and the problems found in them are
    added to the conversation, so the model fixes those problems instead of starting over.
    """
    messages, cards, model = build_messages(brief, brand, channel, model, n)
    if previous:
        messages += [{"role": "assistant", "content": json.dumps({"variants": previous}, ensure_ascii=False)},
                     {"role": "user", "content": "A reviewer found these problems:\n" + feedback +
                      f"\nRewrite so that every problem is fixed and the rules above still hold. "
                      f"Return the same JSON shape with {n} variants."}]
    start = time.perf_counter()
    parsed, llm, tokens = chat_json(messages)
    variants = parsed if isinstance(parsed, list) else parsed.get("variants", [])
    fields = COPY_FIELDS[channel]
    variants = [v for v in variants if all(isinstance(v.get(f), str) and v[f].strip() for f in fields)]
    if not variants:
        raise ValueError(f"no usable variant in model output: {str(parsed)[:200]}")
    return {"variants": variants, "model": model, "cards": [c["card_id"] for c in cards],
            "basket": {"cards": cards, "specs": spec_text(model)}, "llm": llm,
            "seconds": round(time.perf_counter() - start, 2), "tokens": tokens}


BRIEFS = [
    ("Tesla", "social", "Model Y road trip: the car plans the charging stops for you"),
    ("Tesla", "email", "Cybertruck for contractors: power tools on the job site"),
    ("Hyundai", "search", "IONIQ 5 camping weekend powered by the car"),
    ("Hyundai", "social", "Kona Electric as an easy first EV for city drivers"),
    ("Chevrolet", "email", "Equinox EV for families switching from a gas SUV"),
    ("Chevrolet", "search", "Silverado EV hands-free highway driving on long hauls"),
]

if __name__ == "__main__":
    total = 0
    for i, (brand, channel, brief) in enumerate(BRIEFS):
        if i:
            # ponytail: free tier is 8,000 tokens/min per model (~3 briefs); a fixed pause keeps
            # the batch inside it. A real batch job would read the rate-limit headers instead.
            time.sleep(25)
        r = generate(brief, brand, channel)
        total += r["tokens"]
        print(f"\n=== {brand} / {channel} / {r['model']} | {r['llm']} {r['seconds']}s {r['tokens']} tok")
        print("cards:", r["cards"])
        for i, v in enumerate(r["variants"], 1):
            print(f"  v{i}:", json.dumps({f: v[f] for f in COPY_FIELDS[channel]}, ensure_ascii=False)[:600],
                  "| disclaimer:", (v.get("disclaimer") or "")[:90], "| sources:", v.get("sources"))
        for i, v in enumerate(r["variants"], 1):
            print(f"  v{i} rules:", check_rules(v, brand, channel, r["model"], r["cards"]) or "ok")
    print(f"\ntotal tokens: {total}")
