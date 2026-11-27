"""Smoke-test a running API server.

    python test_api.py                       # http://localhost:8000, endpoints without the LLM
    python test_api.py --llm                 # also /generate and /copy (needs GROQ_API_KEY in the server)
    python test_api.py --base http://host:port
"""

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "http://localhost:8000"


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, headers={"Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main():
    ok = True

    def expect(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")

    s, h = call("GET", "/health")
    expect("GET /health", s == 200 and h["status"] == "ok", h)

    s, o = call("GET", "/options")
    expect("GET /options", s == 200 and "Model Y" in o["brands"]["Tesla"], list(o.get("brands", {})))

    s, r = call("POST", "/retrieve", {"query": "How does IONIQ 5 power a campsite?", "brand": "Hyundai"})
    top = r.get("hits", [{}])[0].get("card_id")
    expect("POST /retrieve", s == 200 and r["route"] == "technical" and top.startswith("HYU-I5"), f"top={top}")

    bad = {"headline": "The REVOLUTIONARY Model Y!!", "text": "Never worry about range. FSD drives you."}
    s, c = call("POST", "/check", {"brand": "Tesla", "channel": "social", "model": "Model Y", "variant": bad})
    expect("POST /check flags off-brand copy", s == 200 and not c["passed"] and len(c["problems"]) >= 3,
           f"{len(c.get('problems', []))} problems")

    s, e = call("POST", "/check", {"brand": "Hyundai", "channel": "social", "model": "Model Y", "variant": bad})
    expect("POST /check flags a competitor model", s == 200 and any("competitor" in p for p in e["problems"]))

    s, _ = call("POST", "/generate", {"brief": "x road trip", "brand": "Hyundai", "model": "Model Y"})
    expect("model from another brand -> 422", s == 422)

    good = {"headline": "Model Y plans your road trip", "text": "Trip Planner adds Supercharger stops.",
            "disclaimer": ""}
    s, saved = call("POST", "/copies", {"brief": "api smoke test", "brand": "Tesla", "channel": "social",
                                         "model": "Model Y", "variant": good, "status": "approved"})
    cid = saved.get("id")
    s2, rows = call("GET", "/copies?brand=Tesla")
    expect("POST/GET /copies", s == 200 and any(r["id"] == cid for r in rows), f"id={cid}")
    s, _ = call("PATCH", f"/copies/{cid}", {"status": "saved"})
    s2, _ = call("DELETE", f"/copies/{cid}")
    expect("PATCH + DELETE /copies/{id}", s == 200 and s2 == 200)

    if "--llm" in sys.argv:
        if not h.get("llm_key_present"):
            s, g = call("POST", "/generate", {"brief": "road trip charging stops", "brand": "Tesla"})
            expect("no key -> 503 with instructions", s == 503 and "GROQ_API_KEY" in g.get("detail", ""))
        else:
            s, g = call("POST", "/copy", {"brief": "Road trip: the car plans the charging stops for you",
                                          "brand": "Tesla", "channel": "social", "model": "Model Y"})
            expect("POST /copy", s == 200 and len(g.get("variants", [])) >= 1,
                   f"passed={g.get('passed')} attempts={g.get('attempts')} {g.get('seconds')}s")
            if s == 200:
                for v in g["variants"]:
                    print("      ", v["headline"], "|", v["text"][:90], "| review:", v["review"])
    print("ALL PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
