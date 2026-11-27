"""Write -> check -> rewrite as a LangGraph graph.

    write --> rules --> judge --+--> END            (every variant clean, or rewrite budget used)
                ^               |
                +-- rewrite <---+                   (problems found and attempts < MAX_ATTEMPTS)

Streaming the graph returns the draft as soon as `write` finishes, then the review:
the UI can show copy within ~2 s and attach the checks when they arrive.

    python pipeline.py    # self-check on two briefs
"""

import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from check import check_rules, judge, unsupported
from generate import generate
from retrieval import COPY_FIELDS

MAX_ATTEMPTS = 2  # first draft + one rewrite


class State(TypedDict, total=False):
    brief: str
    brand: str
    channel: str
    model: str
    draft: dict       # latest generate() result
    reviews: list     # one per variant: {"rules", "unsupported", "tone", "claims"}
    attempts: int
    history: list     # earlier drafts with their reviews


def _copy_text(variant, channel):
    # The disclaimer is fine print, not a claim; the rule check already covers it.
    return " ".join(variant[f] for f in COPY_FIELDS[channel])


def write(state):
    draft = generate(state["brief"], state["brand"], state["channel"], state.get("model"))
    return {"draft": draft, "attempts": 1, "history": []}


def rules(state):
    d = state["draft"]
    return {"reviews": [{"rules": check_rules(v, state["brand"], state["channel"], d["model"], d["cards"])}
                        for v in d["variants"]]}


def review(state):
    d = state["draft"]
    results = judge([_copy_text(v, state["channel"]) for v in d["variants"]], state["brand"],
                    d["basket"]["cards"], d["basket"]["specs"], tone=True)
    reviews = [dict(r, unsupported=unsupported(j), tone=j["tone"], claims=j["claims"])
               for r, j in zip(state["reviews"], results)]
    return {"reviews": reviews}


def feedback_text(reviews):
    lines = []
    for i, r in enumerate(reviews, 1):
        for p in r["rules"]:
            lines.append(f"Variant {i}: {p}")
        for c in r["unsupported"]:
            lines.append(f"Variant {i}: unsupported claim '{c}' - remove it or say only what the cards state")
    return "\n".join(lines)


def rewrite(state):
    d = state["draft"]
    new = generate(state["brief"], state["brand"], state["channel"], d["model"],
                   previous=d["variants"], feedback=feedback_text(state["reviews"]))
    history = state["history"] + [{"draft": d, "reviews": state["reviews"]}]
    return {"draft": new, "attempts": state["attempts"] + 1, "history": history}


def passed(state):
    return all(not r["rules"] and not r["unsupported"] for r in state["reviews"])


def next_step(state):
    if passed(state) or state["attempts"] >= MAX_ATTEMPTS:
        return END
    return "rewrite"


def build_graph():
    g = StateGraph(State)
    for name, fn in [("write", write), ("rules", rules), ("review", review), ("rewrite", rewrite)]:
        g.add_node(name, fn)
    g.add_edge(START, "write")
    g.add_edge("write", "rules")
    g.add_edge("rules", "review")
    g.add_conditional_edges("review", next_step, ["rewrite", END])
    g.add_edge("rewrite", "rules")
    return g.compile()


GRAPH = build_graph()


def run(brief, brand, channel, model=None, on_update=None):
    """Run the graph; on_update(node_name, state_so_far, seconds) fires after every node."""
    state = {"brief": brief, "brand": brand, "channel": channel, "model": model}
    start = time.perf_counter()
    for update in GRAPH.stream(state, stream_mode="updates"):
        for node, change in update.items():
            state.update(change)
            if on_update:
                on_update(node, state, round(time.perf_counter() - start, 2))
    state["passed"] = passed(state)
    state["seconds"] = round(time.perf_counter() - start, 2)
    return state


def _print(node, state, seconds):
    if node in ("write", "rewrite"):
        print(f"  [{seconds:5.2f}s] {node}: {state['draft']['llm']}")
        for i, v in enumerate(state["draft"]["variants"], 1):
            print(f"      v{i}:", {f: v[f][:110] for f in COPY_FIELDS[state['channel']]})
    elif node == "review":
        for i, r in enumerate(state["reviews"], 1):
            print(f"  [{seconds:5.2f}s] review v{i}: rules={r['rules'] or 'ok'} | unsupported={r['unsupported'] or 'none'}"
                  f" | tone={r['tone']}")


if __name__ == "__main__":
    from retrieval import _encode, _kb
    t = time.perf_counter()
    _encode(["warm up"]), _kb()  # the app loads these once at startup
    print(f"startup (embedding model + KB): {time.perf_counter() - t:.1f}s")
    for i, (brand, channel, brief) in enumerate([
        ("Chevrolet", "email", "Equinox EV for families switching from a gas SUV"),
        ("Tesla", "social", "Cybertruck for contractors: power tools on the job site"),
    ]):
        if i:
            time.sleep(30)  # free tier: 8,000 tokens/min per model
        print(f"\n=== {brand} / {channel} / {brief}")
        s = run(brief, brand, channel, on_update=_print)
        print(f"  => passed={s['passed']} attempts={s['attempts']} total={s['seconds']}s")
