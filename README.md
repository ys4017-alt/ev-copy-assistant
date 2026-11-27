# EV Copywriting Assistant

A retrieval-augmented generation (RAG) tool that helps marketing teams write ad copy for electric
vehicles. Copy is grounded in owner's-manual facts and spec numbers, written in each brand's voice,
then checked by rules and an LLM fact-check judge before it is returned.

Brands: **Tesla** (main), Hyundai, Chevrolet. Channels: social ad, search ad, email.

---

## Run it (Docker + FastAPI)

```bash
docker build -t ev-copy .
docker run -p 8000:80 -e GROQ_API_KEY=<your key> ev-copy
```

Open **http://localhost:8000/docs** and use "Try it out" on any endpoint.

- The first build takes a few minutes (it downloads CPU-only PyTorch and the embedding model; image ≈ 1.5 GB).
- Port 8000 already in use? Map another one: `docker run -p 8001:80 ...`.
- Without `GROQ_API_KEY` the server still starts: `/health`, `/options`, `/retrieve`, `/check` and `/copies`
  work, and `/generate` and `/copy` answer `503` with instructions.

**Getting a free Groq key (about 2 minutes):** sign in at https://console.groq.com → API Keys →
Create API Key → copy the key that starts with `gsk_`. No payment details needed.

**Smoke test** (standard library only, from this folder):

```bash
python test_api.py --llm                          # http://localhost:8000
python test_api.py --llm --base http://localhost:8001
```

### Endpoints

| Method | Path | What it does | Needs LLM |
|---|---|---|---|
| GET | `/health` | Server status, knowledge-base size, whether a key is present | no |
| GET | `/options` | Brands, models, channels and their length limits | no |
| POST | `/retrieve` | Routes a query (technical / brand / industry) and returns grounding chunks | no |
| POST | `/check` | Rule check of one piece of copy: length, banned words, competitor names, numbers vs specs, disclaimers | no |
| POST | `/generate` | One draft with two variants, no review (~2 s) | yes |
| **POST** | **`/copy`** | **Full pipeline: draft → rule check → fact-check judge → one rewrite if needed (~4–8 s)** | yes |
| GET / POST | `/copies` | List / save copy (`status`: `saved` or `approved`) | no |
| PATCH / DELETE | `/copies/{id}` | Approve, unapprove or delete saved copy | no |

Example:

```bash
curl -X POST localhost:8000/copy -H "Content-Type: application/json" \
  -d '{"brief": "Road trip: the car plans the charging stops for you", "brand": "Tesla", "channel": "social", "model": "Model Y"}'
```

Each returned variant carries its review: `rule_problems`, `unsupported_claims` (claims the judge could
not find in the evidence) and `tone` scores (1–5) for the brand's three voice traits.

---

## How it works

```
brief + brand + channel
   │
   ├─ retrieve: 5 feature cards (embedding + TF-IDF hybrid search, filtered by brand and model)
   ├─ specs: numbers for the model from SQLite (the only allowed source of numbers)
   ├─ brand rules: voice, vocabulary, banned words, claim rules, channel limits (always included)
   └─ examples: 2 approved ads (copy the marketer approved first, then best-performing past ads)
   │
   ▼
write (LLM) ─► rule check ─► fact-check judge ─► pass ──► result
   ▲                                   │
   └──────── rewrite once with the list of problems ◄─ fail
```

| Generative AI technique | Where |
|---|---|
| Embeddings (all-MiniLM-L6-v2) + TF-IDF hybrid retrieval, reciprocal rank fusion | `retrieval.py` |
| Rule-based router (technical / brand / industry) with brand filtering | `retrieval.py` (`route`, `retrieve`) |
| Grounded generation with structured JSON output, few-shot examples, channel templates | `generate.py` |
| Rule-based output checks (Tier 1 evals) | `check.py` (`check_rules`) |
| LLM-as-judge for grounding and tone, calibrated against labelled claims | `check.py` (`judge`, `calibrate`) |
| Agentic write → check → rewrite loop | `pipeline.py` (LangGraph) |
| Feedback loop: approved copy becomes few-shot examples | `retrieval.py` (`get_examples`) |

LLM: Groq `openai/gpt-oss-120b` writes; `qwen/qwen3.8-27b` judges (a different model than the writer)
and is the fallback writer when the first is rate-limited. Calls use the `openai` SDK with Groq's
OpenAI-compatible endpoint, as in the course's M7 notebooks.

---

## Data

| Data | File | Real or synthetic |
|---|---|---|
| Vehicle specs | `ev.db` table `specs` (from the Kaggle "EV Market" CSV) | **Synthetic** dataset |
| Past ad performance | `ev.db` table `ads` (made by `make_ad_samples.py`) | **Synthetic** |
| Brand guidelines | `data/brand_guidelines_{tesla,hyundai,chevrolet}.md` | **Fictional**, written for this project; not official brand documents |
| Feature cards | `data/feature_cards.json` (159 cards, 9 models) | Summaries of real owner's manuals, written in our own words, with PDF page citations |

The owner's manuals themselves are copyrighted and are **not** included in the repository or the image;
they were used locally (`retrieval.py build-manual`, `check_cards.py`) to write and verify the cards.

## Evaluation (current numbers)

| What | Result | Note |
|---|---|---|
| Retrieval recall@5, held-out questions | 90% (18/20) | `eval_retrieval.py holdout`; the set was looked at once while tuning |
| Retrieval brand leaks | 0 | no chunk from another brand on brand-specific questions |
| Rule checker on past ads | off-brand 8/8 caught, approved 32/32 pass | `python check.py` |
| Judge agreement with labelled claims | 86% (19/22) | `python check.py judge`; labels are provisional |
| Latency | draft ~2 s, full `/copy` ~4–8 s | Groq free tier: ~3 requests per minute per model |

## Repository layout

| Path | What it is |
|---|---|
| `api.py` | FastAPI server (the deployed app) |
| `pipeline.py` | LangGraph graph: write → rule check → judge → rewrite |
| `retrieval.py` | Knowledge base, hybrid search, router, SQLite helpers (specs, past ads, saved copy) |
| `generate.py` | Prompt assembly and Groq calls |
| `check.py` | Rule checks and the LLM judge |
| `app.py` | Streamlit UI used in the presentation |
| `test_api.py` | Smoke test for a running server |
| `eval_retrieval.py` | Retrieval evaluation (recall@5, routing, brand leaks) |
| `load_data.py`, `make_ad_samples.py` | Build `ev.db` from `data/ev_market_2026.csv` and the synthetic ads |
| `check_cards.py` | Validates feature cards against the manuals (needs the local PDFs) |
| `ev.db` | SQLite: `specs`, `ads`, `saved_copies` (includes three example saved copies) |
| `data/` | Feature cards, brand guides, brand comparison, ad samples, evaluation sets, judge labels |
| `index/` | Prebuilt knowledge base (`kb.json` text, `kb.npy` embeddings) |
| `docs/project_steps_share_en.html` | Step-by-step project walkthrough and team decisions |

## Local development

Python environment with the packages in `requirements.txt` plus `torch`, `streamlit` and `pypdf`.

```bash
uvicorn api:app --port 8000      # API without Docker (reads GROQ_API_KEY from env or .env)
streamlit run app.py             # presentation UI: edit, save and approve versions
python retrieval.py build        # rebuild the knowledge base after editing cards or guides
python check_cards.py            # validate feature cards against the manuals (needs the PDFs)
python eval_retrieval.py holdout # retrieval recall
python generate.py               # six sample briefs
python pipeline.py               # two briefs through the full graph
```
