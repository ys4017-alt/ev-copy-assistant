"""Retrieval for the EV copywriting assistant.

Numbers come only from ev.db (get_specs). Past approved ads come from ev.db
(get_examples) and become few-shot examples in the generation step.

The knowledge base (KB) that copy is grounded in = feature cards + brand guide sections
(build_kb, retrieve). It holds no manual text, so it can ship with the app.
The full-manual FAISS index (build_manual_index) is a local tool for writing cards only.

    python retrieval.py                 # self-check
    python retrieval.py build           # (re)build the KB: index/kb.json + index/kb.npy
    python retrieval.py build-manual    # (re)build the local manual index: index/chunks.*
"""

import json
import re
import sqlite3
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
DB_PATH = HERE / "ev.db"
DATA = HERE / "data"
INDEX_DIR = HERE / "index"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# MiniLM reads ~256 tokens, so chunks stay near 200 words.
CHUNK_WORDS = 200
OVERLAP_WORDS = 40
MIN_PAGE_WORDS = 30

# Full owner's manuals only; the quick reference guides repeat the same content.
# Model names match ev.db so a chunk can be joined to its spec row.
MANUALS = [
    ("Tesla", "Model 3", "tesla_model3_Owners_Manual.pdf"),
    ("Tesla", "Model Y", "tesla_modely_Owners_Manual.pdf"),
    ("Tesla", "Cybertruck", "tesla_cybertruck_Owners_Manual.pdf"),
    ("Hyundai", "Ioniq 5", "2027_ioniq-5_2027_IONIQ_5_NEA_OM.pdf"),
    ("Hyundai", "Ioniq 6", "2025_ioniq-6_CE-2025-en_US-WEB-2C_FINAL.pdf"),
    ("Hyundai", "Kona Electric", "2025_kona-ev_2025_Kona_Electric_SX2_EV_OM.pdf"),
    ("Chevrolet", "Equinox EV", "2026_chevrolet_equinox_ev_Owner_Manual.pdf"),
    ("Chevrolet", "Blazer EV", "2026_chevrolet_blazer_ev_Owner_Manual.pdf"),
    ("Chevrolet", "Silverado EV", "2026_chevrolet_silverado_ev_Owner_Manual.pdf"),
]
GUIDES = {
    "Tesla": "brand_guidelines_tesla.md",
    "Hyundai": "brand_guidelines_hyundai.md",
    "Chevrolet": "brand_guidelines_chevrolet.md",
}
# "### IONIQ 5" in a guide refers to the ev.db model "Ioniq 5".
GUIDE_MODEL_HEADINGS = {"IONIQ 5": "Ioniq 5", "IONIQ 6": "Ioniq 6"}

CARDS_PATH = DATA / "feature_cards.json"
KB_JSON = INDEX_DIR / "kb.json"
KB_NPY = INDEX_DIR / "kb.npy"

# Lower-case name in a brief -> ev.db model. Longest names are matched first.
MODEL_ALIASES = {
    "model 3": "Model 3", "model y": "Model Y", "cybertruck": "Cybertruck",
    "ioniq 5": "Ioniq 5", "ioniq 6": "Ioniq 6", "kona electric": "Kona Electric", "kona": "Kona Electric",
    "equinox ev": "Equinox EV", "equinox": "Equinox EV", "blazer ev": "Blazer EV", "blazer": "Blazer EV",
    "silverado ev": "Silverado EV", "silverado": "Silverado EV",
}
BRANDS = ("Tesla", "Hyundai", "Chevrolet")
MODEL_BRAND = {"Model 3": "Tesla", "Model Y": "Tesla", "Cybertruck": "Tesla",
               "Ioniq 5": "Hyundai", "Ioniq 6": "Hyundai", "Kona Electric": "Hyundai",
               "Equinox EV": "Chevrolet", "Blazer EV": "Chevrolet", "Silverado EV": "Chevrolet"}
# Questions about wording, tone or rules go to the brand guide even when they name a feature.
BRAND_CUE = re.compile(
    r"\b(how (are|do|should|can) we (say|describe|talk|word|phrase|mention|write|refer)|allowed to|"
    r"can we (say|mention|use|call)|tone|voice|sound like|wording|banned|off-limits|forbidden|"
    r"headline|subject line|preheader|call to action|calls to action|cta|disclaimer|hashtag|"
    r"character limit|how many characters|audience|buyer|story do we|lead with|brand guide)\b", re.I)
INDUSTRY_CUE = re.compile(
    r"\b(industry|all brands|across brands|every brand|other brands|compare brands|"
    r"most evs|evs in general|electric vehicles in general|any ev)\b", re.I)

CHEVY_HEADER = re.compile(r"Chevrolet \S+(?: EV)? Owner Manual \(GMNA[^)]*\) - \d{4} \d+ ")

# Which column ranks an ad's performance, per channel.
RANK_METRIC = {"social": "ctr", "search": "ctr", "email": "click_rate"}
COPY_FIELDS = {
    "social": ["headline", "text"],
    "search": ["headline", "description"],
    "email": ["subject", "preheader", "body"],
}


def _connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def get_specs(model):
    """Return the spec row for a model as a dict, or None if the model is unknown."""
    with _connect() as con:
        row = con.execute("SELECT * FROM specs WHERE model = ?", (model,)).fetchone()
    return dict(row) if row else None


SAVED_DDL = """CREATE TABLE IF NOT EXISTS saved_copies (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    brand TEXT, model TEXT, channel TEXT, brief TEXT, variant_json TEXT, review_json TEXT, status TEXT)"""


def save_copy(brand, model, channel, brief, variant, review, status):
    """Store one variant the marketer saved or approved. status: 'saved' or 'approved'.

    The same copy for the same brief is one row: approving a saved copy upgrades it,
    saving an approved copy leaves it approved.
    """
    variant_json = json.dumps(variant, sort_keys=True)
    with _connect() as con:
        con.execute(SAVED_DDL)
        row = con.execute("SELECT id, status FROM saved_copies WHERE brand = ? AND channel = ? AND brief = ? "
                          "AND variant_json = ?", (brand, channel, brief, variant_json)).fetchone()
        if row:
            if status == "approved" and row["status"] != "approved":
                con.execute("UPDATE saved_copies SET status = 'approved', review_json = ? WHERE id = ?",
                            (json.dumps(review), row["id"]))
            return row["id"]
        cur = con.execute(
            "INSERT INTO saved_copies (brand, model, channel, brief, variant_json, review_json, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (brand, model, channel, brief, variant_json, json.dumps(review), status))
        return cur.lastrowid


def set_copy_status(copy_id, status):
    """'saved' takes a copy out of the few-shot examples; 'approved' puts it back."""
    with _connect() as con:
        return con.execute("UPDATE saved_copies SET status = ? WHERE id = ?", (status, copy_id)).rowcount


def delete_copy(copy_id):
    with _connect() as con:
        return con.execute("DELETE FROM saved_copies WHERE id = ?", (copy_id,)).rowcount


def list_copies(brand=None):
    with _connect() as con:
        con.execute(SAVED_DDL)
        rows = con.execute("SELECT * FROM saved_copies WHERE ? IS NULL OR brand = ? ORDER BY id DESC",
                           (brand, brand)).fetchall()
    return [dict(r, variant=json.loads(r["variant_json"]), review=json.loads(r["review_json"])) for r in rows]


def get_examples(brand, model, channel, k=2, include_approved=True):
    """Return up to k example ads for few-shot prompting.

    Copy the marketer approved in the app comes first (newest, same model preferred), so the
    tool follows their choices; synthetic past ads fill the rest, best performing first.
    """
    out = []
    if include_approved:
        with _connect() as con:
            con.execute(SAVED_DDL)
            rows = con.execute(
                "SELECT id, model, variant_json FROM saved_copies WHERE brand = ? AND channel = ? "
                "AND status = 'approved' ORDER BY (model = ?) DESC, id DESC LIMIT ?",
                (brand, channel, model, k)).fetchall()
        for r in rows:
            v = json.loads(r["variant_json"])
            out.append({"ad_id": f"APPROVED-{r['id']}", "model": r["model"], "cta": None,
                        **{f: v.get(f, "") for f in COPY_FIELDS[channel]}})
    if len(out) >= k:
        return out
    metric = RANK_METRIC[channel]
    fields = ", ".join(["ad_id", "model", "cta", metric] + COPY_FIELDS[channel])
    query = f"""
        SELECT {fields} FROM ads
        WHERE brand = ? AND channel = ? AND approved = 1
        ORDER BY (model = ?) DESC, {metric} DESC
        LIMIT ?
    """
    with _connect() as con:
        rows = con.execute(query, (brand, channel, model, k - len(out))).fetchall()
    return out + [dict(r) for r in rows]


def clean_page(text):
    """Collapse whitespace and drop extraction noise; return '' for pages not worth indexing."""
    text = CHEVY_HEADER.sub("", re.sub(r"\s+", " ", text or ""))
    # Hyundai PDFs carry image labels such as "1C_WindowOpenClose".
    text = " ".join(w for w in text.split() if "_" not in w)
    # Table-of-contents and index pages are mostly dot leaders.
    if text.count("....") > 5 or len(text.split()) < MIN_PAGE_WORDS:
        return ""
    return text


def windows(words):
    """Split a word list into overlapping CHUNK_WORDS windows."""
    step = CHUNK_WORDS - OVERLAP_WORDS
    starts = range(0, max(len(words) - OVERLAP_WORDS, 1), step)
    return [" ".join(words[s:s + CHUNK_WORDS]) for s in starts]


def manual_chunks():
    from pypdf import PdfReader

    chunks = []
    for brand, model, filename in MANUALS:
        reader = PdfReader(DATA / "manuals" / filename)
        for page_no, page in enumerate(reader.pages, start=1):
            text = clean_page(page.extract_text())
            for piece in windows(text.split()) if text else []:
                chunks.append({"kind": "manual", "brand": brand, "model": model,
                               "source": filename, "page": page_no, "section": None, "text": piece})
    return chunks


def guide_chunks():
    """One chunk per guide subsection (### or ##), with its heading path kept in the text."""
    chunks = []
    for brand, filename in GUIDES.items():
        h2 = h3 = None
        body = []

        def flush():
            words = " ".join(body).split()
            # Skip the "not an official document" note above the first heading: it carries no rules.
            if not words or h2 is None:
                return
            section = " > ".join(h for h in (h2, h3) if h)
            model = GUIDE_MODEL_HEADINGS.get(h3, h3) if h3 and h2 == "5. Model Messaging" else None
            for piece in windows(words):
                chunks.append({"kind": "guide", "brand": brand, "model": model,
                               "source": filename, "page": None, "section": section, "text": piece})

        for line in (DATA / filename).read_text().splitlines():
            if line.startswith("## ") or line.startswith("### "):
                flush()
                body = []
                if line.startswith("## "):
                    h2, h3 = line[3:].strip(), None
                else:
                    h3 = line[4:].strip()
            elif line.strip() and line.strip() != "---":
                body.append(line.strip())
        flush()
    return chunks


def embed_text(chunk):
    """Text the model sees: brand, model and source type first, so 'Model Y charging' matches Model Y pages."""
    if chunk["kind"] == "manual":
        return f"{chunk['brand']} {chunk['model']} owner's manual: {chunk['text']}"
    if chunk["kind"] == "card":
        return f"{chunk['brand']} {chunk['model']} feature: {chunk['text']}"
    return f"{chunk['brand']} brand guide, {chunk['section']}: {chunk['text']}"


def card_chunks():
    chunks = []
    for c in json.loads(CARDS_PATH.read_text())["cards"]:
        chunks.append({"kind": "card", "brand": c["brand"], "model": c["model"], "card_id": c["card_id"],
                       "feature": c["feature"], "source": c["source"], "page": c["pages"], "section": None,
                       "text": f"{c['title']}. {c['summary']}", "caution": c["caution"]})
    return chunks


@lru_cache(maxsize=1)
def _encoder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL)


def _encode(texts):
    return _encoder().encode(texts, batch_size=64, normalize_embeddings=True)


def build_kb():
    chunks = card_chunks() + guide_chunks()
    INDEX_DIR.mkdir(exist_ok=True)
    np.save(KB_NPY, _encode([embed_text(c) for c in chunks]))
    KB_JSON.write_text(json.dumps(chunks, ensure_ascii=False))
    _kb.cache_clear()
    return chunks


@lru_cache(maxsize=1)
def _kb():
    """KB chunks, their embeddings, and a TF-IDF index over the same texts (built on load; tiny)."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    chunks = json.loads(KB_JSON.read_text())
    texts = [embed_text(c) for c in chunks]
    tfidf = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True).fit(texts)
    return chunks, np.load(KB_NPY), tfidf, tfidf.transform(texts)


RRF_K = 60  # standard reciprocal rank fusion constant


def _ranks(scores):
    return np.argsort(np.argsort(-scores))


def _find_model(query):
    """(alias as written, ev.db model) for the first model named in the query, else (None, None)."""
    for alias in sorted(MODEL_ALIASES, key=len, reverse=True):
        m = re.search(rf"\b{re.escape(alias)}\b", query, re.I)
        if m:
            return m.group(0), MODEL_ALIASES[alias]
    return None, None


def detect_model(query):
    return _find_model(query)[1]


def search(qvec, kind, brand=None, model=None, k=5, query=None):
    """Top-k KB chunks of one kind, filtered by brand and model. Returns (score, chunk) pairs.

    With query text, meaning (embedding) and exact words (TF-IDF) are combined by
    reciprocal rank fusion, so a literal term like "zero emissions" is not missed.
    Without it, the score is plain cosine similarity (used by route()).
    """
    chunks, vecs, tfidf, lex = _kb()
    ids = [i for i, c in enumerate(chunks)
           if c["kind"] == kind and (brand is None or c["brand"] == brand)
           and (model is None or c["model"] == model)]
    if not ids:
        return []
    scores = vecs[ids] @ qvec
    if query is not None:
        lexical = (lex[ids] @ tfidf.transform([query]).T).toarray().ravel()
        # Chunks sharing no word with the query all rank last instead of in file order.
        lex_rank = np.where(lexical > 0, _ranks(lexical), len(ids))
        scores = 1 / (RRF_K + _ranks(scores)) + 1 / (RRF_K + lex_rank)
    order = np.argsort(-scores)[:k]
    return [(float(scores[j]), chunks[ids[j]]) for j in order]


def route(query, brand, qvec):
    """technical (feature cards), brand (guide) or industry (cards from every brand).

    No LLM, checked in this order: no brand selected or an industry cue -> industry;
    a wording/tone cue -> brand; a model named -> technical; otherwise whichever source
    matches the query better, feature cards or this brand's guide.
    """
    if brand is None or INDUSTRY_CUE.search(query):
        return "industry"
    if BRAND_CUE.search(query):
        return "brand"
    if detect_model(query):
        return "technical"
    best_card = search(qvec, "card", brand, k=1)
    best_guide = search(qvec, "guide", brand, k=1)
    return "brand" if best_guide[0][0] > best_card[0][0] else "technical"


def retrieve(query, brand=None, k=5):
    """Route a query and return the KB chunks to ground copy in.

    A model named in the query narrows technical search only when it belongs to the
    selected brand; a competitor's model never pulls in that competitor's cards.
    """
    qvec = _encode([query])[0]
    kind = route(query, brand, qvec)
    alias, model = _find_model(query)
    if model and brand and MODEL_BRAND[model] != brand:
        model = None
    if kind == "technical":
        hits = _card_search(query, qvec, brand, model, alias, k)
    elif kind == "brand":
        hits = search(qvec, "guide", brand, k=k, query=query)
    else:
        # Every brand contributes, so one brand's wording cannot crowd out the others.
        per_brand = k // 3 + 1
        hits = sorted((h for b in BRANDS for h in search(qvec, "card", b, k=per_brand, query=query)),
                      key=lambda h: -h[0])
    return {"route": kind, "model": model, "hits": hits}


def _card_search(query, qvec, brand, model, alias, k):
    if not model:
        return search(qvec, "card", brand, k=k, query=query)
    # Every card of this model carries its name, so the name would dominate similarity.
    # The model filter already handles it; compare on the rest of the query.
    rest = query.replace(alias, " ")
    return search(_encode([rest])[0], "card", brand, model, k, query=rest)


def retrieve_for_copy(brief, brand, k_cards=3, k_guide=2):
    """Grounding for writing copy: feature cards AND brand guide sections, whatever route() says.

    A brief needs both facts and voice, so a routing mistake cannot leave either out.
    """
    qvec = _encode([brief])[0]
    alias, model = _find_model(brief)
    if model and MODEL_BRAND[model] != brand:
        alias, model = None, None
    return {"model": model,
            "cards": _card_search(brief, qvec, brand, model, alias, k_cards),
            "guide": search(qvec, "guide", brand, k=k_guide, query=brief)}


def build_manual_index():
    import faiss

    chunks = manual_chunks() + guide_chunks()
    model = _encoder()
    vectors = model.encode([embed_text(c) for c in chunks], batch_size=64,
                           normalize_embeddings=True, show_progress_bar=True)
    index = faiss.IndexFlatIP(vectors.shape[1])  # inner product on unit vectors = cosine
    index.add(vectors)
    INDEX_DIR.mkdir(exist_ok=True)
    faiss.write_index(index, str(INDEX_DIR / "chunks.faiss"))
    (INDEX_DIR / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False))
    return chunks


def self_check():
    assert windows(list("abcdefghij")) == ["a b c d e f g h i j"]
    words = [str(i) for i in range(500)]
    parts = windows(words)
    assert all(len(p.split()) <= CHUNK_WORDS for p in parts)
    assert parts[0].split()[-OVERLAP_WORDS:] == parts[1].split()[:OVERLAP_WORDS]
    assert parts[-1].split()[-1] == "499"
    assert clean_page("Contents " + "Charging ....... 12 " * 10) == ""
    assert clean_page("1C_WindowOpenClose " + "word " * 40).split()[0] == "word"

    spec = get_specs("Model Y")
    assert spec["brand"] == "Tesla" and spec["range_miles"] > 0, spec
    assert get_specs("Model Z") is None

    ex = get_examples("Tesla", "Model Y", "social", include_approved=False)
    assert len(ex) == 2 and all(e["model"] == "Model Y" for e in ex), ex
    assert ex[0]["ctr"] >= ex[1]["ctr"]

    # Hyundai has one approved IONIQ 6 social ad, so the second example comes from another model.
    ex = get_examples("Hyundai", "Ioniq 6", "social", include_approved=False)
    assert ex[0]["model"] == "Ioniq 6" and ex[1]["model"] != "Ioniq 6", ex

    # Off-brand ads are never returned.
    with _connect() as con:
        rejected = {r[0] for r in con.execute("SELECT ad_id FROM ads WHERE approved = 0")}
    for brand in ["Tesla", "Hyundai", "Chevrolet"]:
        for channel in RANK_METRIC:
            for e in get_examples(brand, "", channel, k=50, include_approved=False):
                assert e["ad_id"] not in rejected

    print("Model Y spec:", {k: spec[k] for k in ["variant", "range_miles", "charging_speed_kw", "price_usd"]})
    print("Model Y social examples:", [(e["ad_id"], e["ctr"], e["headline"]) for e in get_examples("Tesla", "Model Y", "social", include_approved=False)])
    print("self-check passed")


def kb_check():
    """Routing and brand filtering on a few fixed queries (needs `python retrieval.py build`)."""
    r = retrieve("How fast does Model Y charge at a Supercharger?", "Tesla")
    assert r["route"] == "technical" and r["model"] == "Model Y", r["route"]
    assert r["hits"][0][1]["card_id"] == "TSL-MY-fast_charging", r["hits"][0][1]["card_id"]

    r = retrieve("Which words are banned in our ad copy?", "Hyundai")
    assert r["route"] == "brand", r["route"]
    assert all(h[1]["brand"] == "Hyundai" and h[1]["kind"] == "guide" for h in r["hits"])

    # A competitor's model in a Hyundai brief must not pull in Tesla cards.
    r = retrieve("Write copy that says our car has a bigger frunk than Model Y", "Hyundai")
    assert r["model"] is None and all(h[1]["brand"] == "Hyundai" for h in r["hits"]), r

    r = retrieve("How does regenerative braking work across the industry?", "Tesla")
    assert r["route"] == "industry" and {h[1]["brand"] for h in r["hits"]} == set(BRANDS), r["route"]

    for q, brand in [("hands-free highway driving", "Chevrolet"), ("camping with the car's power", "Hyundai")]:
        r = retrieve(q, brand)
        print(f"{brand:9} | {q:32} -> {r['route']:9} {[h[1].get('card_id') or h[1]['section'] for h in r['hits'][:3]]}")
    print("kb check passed")


if __name__ == "__main__":
    if sys.argv[1:] == ["build"]:
        chunks = build_kb()
        print(f"KB: {len(chunks)} chunks into {KB_JSON.name} / {KB_NPY.name}")
        kb_check()
    elif sys.argv[1:] == ["build-manual"]:
        chunks = build_manual_index()
        print(f"indexed {len(chunks)} manual + guide chunks into {INDEX_DIR}")
    else:
        self_check()
        if KB_JSON.exists():
            kb_check()
