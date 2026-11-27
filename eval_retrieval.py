"""Grade retrieve() on data/eval_questions.json.

recall@k   : share of questions with at least one relevant item in the top k
route      : share of questions sent to the expected route (technical / brand / industry)
brand leak : hits from another brand on a non-industry question (must be 0)
"""

import json
import sys
from collections import defaultdict

from retrieval import DATA, retrieve, retrieve_for_copy

K = 5


def section_numbers(section):
    """'3. Vocabulary > 3.3 Banned words' -> {'3', '3.3'}"""
    # The intro above a guide's first heading has an empty section.
    return {part.split()[0].rstrip(".") for part in section.split(" > ") if part}


def is_relevant(chunk, item):
    kind, value = item.split(":", 1)
    if kind == "card":
        return chunk.get("card_id") == value
    if kind == "feature":
        return chunk.get("feature") == value
    return chunk["kind"] == "guide" and value in section_numbers(chunk["section"])


def label(chunk):
    return chunk.get("card_id") or f"guide {chunk['section'].split(' > ')[-1] or 'intro'}"


def main(path, verbose=False):
    questions = json.loads(path.read_text())["questions"]
    print(path.name)
    by_group = defaultdict(lambda: [0, 0])
    route_ok = leaks = 0
    misses = []
    for q in questions:
        r = retrieve(q["query"], q["brand"], k=K)
        chunks = [h[1] for h in r["hits"]]
        hit = any(is_relevant(c, item) for c in chunks for item in q["relevant"])
        # Copy mode: 3 cards + 2 guide sections regardless of route.
        c = retrieve_for_copy(q["query"], q["brand"])
        copy_hit = any(is_relevant(h[1], item) for h in c["cards"] + c["guide"] for item in q["relevant"])
        by_group["copy mode (3 cards + 2 guide)"][0] += copy_hit
        by_group["copy mode (3 cards + 2 guide)"][1] += 1
        route_ok += r["route"] == q["route"]
        if q["route"] != "industry":
            leaks += sum(c["brand"] != q["brand"] for c in chunks)
        for group in ("all", q["brand"], q["route"]):
            by_group[group][0] += hit
            by_group[group][1] += 1
        if not hit or r["route"] != q["route"] or verbose:
            misses.append(f"{q['id']} [{'hit' if hit else 'MISS'}] route {r['route']} (want {q['route']}) | "
                          f"{q['query'][:60]}\n      top: {[label(c) for c in chunks[:3]]}")

    print(f"recall@{K}:")
    for group, (h, n) in by_group.items():
        print(f"  {group:10} {h}/{n} = {h / n:.0%}")
    print(f"route accuracy: {route_ok}/{len(questions)} = {route_ok / len(questions):.0%}")
    print(f"brand leaks: {leaks}")
    if misses:
        print("\nmisses / wrong routes:")
        print("\n".join(misses))


if __name__ == "__main__":
    # python eval_retrieval.py [holdout|user] [-v]
    name = next((f"eval_questions_{s}.json" for s in ("holdout", "user") if s in sys.argv), "eval_questions.json")
    main(DATA / name, verbose="-v" in sys.argv)
