"""FastAPI server for the EV Copywriting Assistant.

    uvicorn api:app --port 8000          # local
    docker run -p 8000:80 -e GROQ_API_KEY=... ev-copy    # see README

Interactive docs at /docs. Endpoints that need no LLM (/health, /options, /retrieve, /check,
/copies) work without GROQ_API_KEY; /generate and /copy return 503 with instructions if it is missing.
"""

from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

import generate as gen
from check import EMAIL_WORDS, LIMITS, check_rules
from pipeline import run
from retrieval import (BRANDS, COPY_FIELDS, MODEL_BRAND, _encode, _kb, delete_copy, list_copies, retrieve,
                       save_copy, set_copy_status)

Brand = Literal["Tesla", "Hyundai", "Chevrolet"]
Channel = Literal["social", "search", "email"]


@asynccontextmanager
async def lifespan(app):
    _encode(["warm up"])  # load the embedding model and KB once, not on the first request
    _kb()
    yield


app = FastAPI(title="EV Copywriting Assistant API", version="1.0", lifespan=lifespan,
              description="RAG ad-copy generator for EV marketers: retrieval over owner's-manual feature "
                          "cards and brand guides, LLM generation (Groq), rule checks and an LLM fact-check "
                          "judge, orchestrated with LangGraph. Brand guides, specs and past ads are synthetic "
                          "class data.")


class BriefIn(BaseModel):
    brief: str = Field(min_length=3, examples=["Road trip: the car plans the charging stops for you"])
    brand: Brand = "Tesla"
    channel: Channel = "social"
    model: Optional[str] = Field(None, description="ev.db model name, e.g. 'Model Y', 'Ioniq 5'. "
                                                   "Omit to let the brief decide.", examples=["Model Y"])

    @model_validator(mode="after")
    def model_matches_brand(self):
        if self.model and MODEL_BRAND.get(self.model) != self.brand:
            raise ValueError(f"model must be one of {[m for m, b in MODEL_BRAND.items() if b == self.brand]}")
        return self


class RetrieveIn(BaseModel):
    query: str = Field(min_length=3, examples=["How does IONIQ 5 power a campsite?"])
    brand: Optional[Brand] = Field("Hyundai", description="Omit for an industry-wide search.")
    k: int = Field(5, ge=1, le=10)


class CheckIn(BaseModel):
    brand: Brand = "Tesla"
    channel: Channel = "social"
    model: Optional[str] = Field(None, examples=["Model Y"])
    variant: dict = Field(examples=[{"headline": "The REVOLUTIONARY Model Y!!",
                                     "text": "Never worry about range. FSD drives you everywhere.",
                                     "disclaimer": ""}])


class SaveIn(BriefIn):
    variant: dict = Field(examples=[{"headline": "Model Y plans your road trip",
                                     "text": "Trip Planner adds Supercharger stops along the route.",
                                     "disclaimer": ""}])
    review: dict = Field(default_factory=dict)
    status: Literal["saved", "approved"] = "saved"


class StatusIn(BaseModel):
    status: Literal["saved", "approved"]


def _need_key():
    try:
        gen._api_key()
    except RuntimeError:
        raise HTTPException(503, "GROQ_API_KEY is not set. Start the container with "
                                 "-e GROQ_API_KEY=<key> (free key: https://console.groq.com/keys).")


def _llm(fn, *args, **kwargs):
    _need_key()
    try:
        return fn(*args, **kwargs)
    except RuntimeError as e:  # both models still rate-limited after waiting
        raise HTTPException(503, f"LLM unavailable: {e}. The free tier allows about 3 requests per minute.")


def _chunk_out(score, c):
    return {"score": round(score, 4), "kind": c["kind"], "brand": c["brand"], "model": c["model"],
            "card_id": c.get("card_id"), "section": c.get("section"), "text": c["text"]}


@app.get("/")
def root():
    return {"name": app.title, "docs": "/docs", "endpoints": ["/health", "/options", "/retrieve", "/check",
                                                              "/generate", "/copy", "/copies"]}


@app.get("/health")
def health():
    try:
        gen._api_key()
        key = True
    except RuntimeError:
        key = False
    return {"status": "ok", "kb_chunks": len(_kb()[0]), "llm_key_present": key, "llm": gen.MODEL}


@app.get("/options")
def options():
    """Brands, models and channel limits accepted by the other endpoints."""
    return {"brands": {b: [m for m, mb in MODEL_BRAND.items() if mb == b] for b in BRANDS},
            "channels": {c: {"fields": COPY_FIELDS[c], "char_limits": LIMITS[c],
                             **({"body_words": EMAIL_WORDS} if c == "email" else {})} for c in COPY_FIELDS}}


@app.post("/retrieve")
def retrieve_endpoint(req: RetrieveIn):
    """Route a query (technical / brand / industry) and return the grounding chunks. No LLM."""
    r = retrieve(req.query, req.brand, k=req.k)
    return {"route": r["route"], "model": r["model"], "hits": [_chunk_out(s, c) for s, c in r["hits"]]}


@app.post("/check")
def check_endpoint(req: CheckIn):
    """Rule check for one piece of copy (length, banned words, numbers, disclaimers). No LLM."""
    missing = [f for f in COPY_FIELDS[req.channel] if f not in req.variant]
    if missing:
        raise HTTPException(422, f"variant needs fields {COPY_FIELDS[req.channel]}; missing {missing}")
    problems = check_rules(req.variant, req.brand, req.channel, req.model)
    return {"passed": not problems, "problems": problems}


@app.post("/generate")
def generate_endpoint(req: BriefIn):
    """One draft with two variants, no review (about 2 s)."""
    r = _llm(gen.generate, req.brief, req.brand, req.channel, req.model)
    return {k: r[k] for k in ("variants", "model", "cards", "llm", "seconds", "tokens")} | \
        {"specs": r["basket"]["specs"]}


@app.post("/copy")
def copy_endpoint(req: BriefIn):
    """Full pipeline: draft -> rule check -> fact-check judge -> one rewrite if needed."""
    s = _llm(run, req.brief, req.brand, req.channel, req.model)
    d = s["draft"]
    return {"passed": s["passed"], "attempts": s["attempts"], "seconds": s["seconds"], "model": d["model"],
            "cards": d["cards"], "llm": d["llm"],
            "variants": [dict(v, review={"rule_problems": r["rules"], "unsupported_claims": r["unsupported"],
                                         "tone": r["tone"]})
                         for v, r in zip(d["variants"], s["reviews"])],
            "earlier_versions": len(s.get("history", []))}


@app.get("/copies")
def copies_list(brand: Optional[Brand] = None):
    """Saved and approved copy. Approved copy is used as a few-shot example for later requests."""
    return [{k: row[k] for k in ("id", "created_at", "status", "brand", "model", "channel", "brief", "variant")}
            for row in list_copies(brand)]


@app.post("/copies")
def copies_save(req: SaveIn):
    return {"id": save_copy(req.brand, req.model, req.channel, req.brief, req.variant, req.review, req.status)}


@app.patch("/copies/{copy_id}")
def copies_status(copy_id: int, req: StatusIn):
    if not set_copy_status(copy_id, req.status):
        raise HTTPException(404, "no such copy")
    return {"id": copy_id, "status": req.status}


@app.delete("/copies/{copy_id}")
def copies_delete(copy_id: int):
    if not delete_copy(copy_id):
        raise HTTPException(404, "no such copy")
    return {"deleted": copy_id}
