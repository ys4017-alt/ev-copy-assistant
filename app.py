"""EV Copywriting Assistant — Streamlit UI.

    streamlit run app.py

The draft appears as soon as it is written (~2 s); rule and fact checks attach when they finish,
and a version with problems is rewritten once.
"""

import json

import streamlit as st

from check import check_rules, judge, unsupported
from pipeline import MAX_ATTEMPTS, _copy_text, passed, run
from retrieval import (BRANDS, COPY_FIELDS, DATA, MODEL_BRAND, _encode, _kb, delete_copy, list_copies,
                       save_copy, set_copy_status)

COPY_NAME = {"Ioniq 5": "IONIQ 5", "Ioniq 6": "IONIQ 6"}
CHANNELS = {"social": "Social ad", "search": "Search ad", "email": "Email"}

st.set_page_config(page_title="EV Copy Assistant", page_icon="⚡", layout="wide")


@st.cache_resource
def warm_up():
    """Load the embedding model and knowledge base once per server, not per click."""
    _encode(["warm up"])
    _kb()
    return {c["card_id"]: c for c in json.loads((DATA / "feature_cards.json").read_text())["cards"]}


CARDS = warm_up()


# --- rendering ----------------------------------------------------------------------------------

def show_copy(variant, channel):
    if channel == "social":
        st.markdown(f"**{variant['headline']}**")
        st.write(variant["text"])
    elif channel == "search":
        st.markdown(f":blue[**{variant['headline']}**]")
        st.write(variant["description"])
    else:
        st.markdown(f"**Subject:** {variant['subject']}")
        st.caption(f"Preheader: {variant['preheader']}")
        st.write(variant["body"])
    if variant.get("disclaimer"):
        st.caption(variant["disclaimer"])
    if variant.get("edited"):
        st.caption("✏️ Edited by you")
    sources = [CARDS[c]["title"] for c in variant.get("sources", []) if c in CARDS]
    if sources:
        st.caption("Grounded in: " + " · ".join(sources))


def show_review(review):
    problems = review["rules"] + [f"Unsupported claim: {c}" for c in review["unsupported"]]
    if problems:
        st.warning(f"{len(problems)} issue(s)\n\n" + "\n".join(f"- {p}" for p in problems))
    else:
        st.success("Passed rule and fact checks")
    if review.get("tone"):
        cols = st.columns(len(review["tone"]))
        for col, (trait, score) in zip(cols, review["tone"].items()):
            col.metric(trait, f"{score}/5")


def draw_variants(area, state, status):
    """Draw both variants into `area`. status: 'checking' while the judge runs, else reviews are shown."""
    channel = state["channel"]
    with area.container():
        cols = st.columns(len(state["draft"]["variants"]))
        for i, (col, variant) in enumerate(zip(cols, state["draft"]["variants"])):
            with col, st.container(border=True):
                st.markdown(f"#### Version {i + 1}")
                if status == "final" and st.session_state.get(f"editing{i}"):
                    edit_form(state, i, variant)
                    continue
                show_copy(variant, channel)
                if status == "checking":
                    st.info("Checking rules and facts…")
                elif state.get("reviews"):
                    show_review(state["reviews"][i])
                if status == "final":
                    final_buttons(state, i, variant)


def final_buttons(state, i, variant):
    review = state["reviews"][i]
    b1, b2, b3 = st.columns(3)
    if b1.button("Edit", key=f"edit{i}", use_container_width=True):
        st.session_state[f"editing{i}"] = True
        st.rerun()
    if b2.button("Save", key=f"save{i}", use_container_width=True):
        save_copy(state["brand"], state["draft"]["model"], state["channel"], state["brief"], variant, review, "saved")
        st.toast("Saved")
    if b3.button("Approve", key=f"approve{i}", type="primary", use_container_width=True):
        save_copy(state["brand"], state["draft"]["model"], state["channel"], state["brief"], variant, review, "approved")
        st.toast("Approved — future copy for this brand and channel will use it as an example")


def edit_form(state, i, variant):
    """Let the marketer rewrite a version, then run the same rule and fact checks on it."""
    channel = state["channel"]
    edited = {}
    for f in COPY_FIELDS[channel] + ["disclaimer"]:
        if f == "body":
            edited[f] = st.text_area("Body", variant.get(f, ""), key=f"field{i}_{f}", height=220)
        else:
            edited[f] = st.text_input(f.capitalize(), variant.get(f, ""), key=f"field{i}_{f}")
    c1, c2 = st.columns(2)
    if c1.button("Apply & re-check", key=f"apply{i}", type="primary", use_container_width=True):
        new = dict(variant, **edited, edited=True)
        draft = state["draft"]
        with st.spinner("Checking your edit…"):
            rules_found = check_rules(new, state["brand"], channel, draft["model"], draft["cards"])
            j = judge([_copy_text(new, channel)], state["brand"], draft["basket"]["cards"],
                      draft["basket"]["specs"], tone=True)[0]
        draft["variants"][i] = new
        state["reviews"][i] = {"rules": rules_found, "unsupported": unsupported(j), "tone": j["tone"],
                               "claims": j["claims"]}
        st.session_state[f"editing{i}"] = False
        st.rerun()
    if c2.button("Cancel", key=f"cancel{i}", use_container_width=True):
        st.session_state[f"editing{i}"] = False
        st.rerun()


def show_evidence(state):
    draft = state["draft"]
    with st.expander("Evidence: what the copy was allowed to use"):
        st.markdown("**Feature cards** (summaries of the owner's manual)")
        for card_id in draft["cards"]:
            c = CARDS[card_id]
            st.markdown(f"- **{c['title']}** — {c['summary']}  \n"
                        f"  <small>Caution: {c['caution'] or 'none'} · Source: {c['source']} p. "
                        f"{', '.join(map(str, c['pages']))}</small>", unsafe_allow_html=True)
        st.markdown("**Spec numbers** (synthetic class dataset)")
        st.code(draft["basket"]["specs"], language=None)
    if state.get("history"):
        with st.expander(f"Earlier version (rewritten to fix {sum(len(r['rules']) + len(r['unsupported']) for r in state['history'][-1]['reviews'])} issue(s))"):
            old = state["history"][-1]
            for i, (v, r) in enumerate(zip(old["draft"]["variants"], old["reviews"]), 1):
                st.markdown(f"**Version {i} before**")
                show_copy(v, state["channel"])
                show_review(r)


# --- page ---------------------------------------------------------------------------------------

st.title("⚡ EV Copywriting Assistant")
st.caption("Ad copy grounded in owner's-manual facts and brand voice. Brand guides, specs and past ads are "
           "synthetic class data; feature cards summarize real owner's manuals.")

with st.sidebar:
    brand = st.selectbox("Brand", BRANDS)
    models = [m for m, b in MODEL_BRAND.items() if b == brand]
    model = st.selectbox("Model", ["(any)"] + models, format_func=lambda m: COPY_NAME.get(m, m))
    channel = st.radio("Channel", list(CHANNELS), format_func=CHANNELS.get)
    brief = st.text_area("Brief", placeholder="e.g. Road trip: the car plans the charging stops for you", height=120)
    go = st.button("Write copy", type="primary", use_container_width=True, disabled=not brief.strip())

create, saved = st.tabs(["Create", "Saved & approved"])

with create:
    if go:
        status_line = st.empty()
        area = st.empty()

        def on_update(node, state, seconds):
            if node in ("write", "rewrite"):
                label = "Draft" if node == "write" else "Rewritten draft"
                status_line.caption(f"{label} ready in {seconds}s · checking…")
                draw_variants(area, state, "checking")
            elif node == "review":
                if not passed(state) and state["attempts"] < MAX_ATTEMPTS:
                    status_line.caption(f"Issues found at {seconds}s · rewriting once…")
                draw_variants(area, state, "reviewed")

        with st.spinner("Writing…"):
            result = run(brief.strip(), brand, channel, None if model == "(any)" else model, on_update=on_update)
        st.session_state["result"] = result
        for k in [k for k in st.session_state if k.startswith(("editing", "field"))]:
            del st.session_state[k]
        st.rerun()  # redraw from session state so the Save / Approve buttons work

    if "result" in st.session_state:
        r = st.session_state["result"]
        st.caption(f"{r['brand']} · {COPY_NAME.get(r['draft']['model'], r['draft']['model']) or 'any model'} · "
                   f"{CHANNELS[r['channel']]} · “{r['brief']}” · {r['seconds']}s total · "
                   f"{'passed' if r['passed'] else 'issues remain'} after {r['attempts']} attempt(s)")
        draw_variants(st.empty(), r, "final")
        show_evidence(r)

with saved:
    rows = list_copies(None)
    if not rows:
        st.info("Nothing saved yet. Use Save or Approve on a version.")
    for row in rows:
        with st.container(border=True):
            st.markdown(f"**{row['status'].upper()}** · {row['brand']} · {COPY_NAME.get(row['model'], row['model'] or 'any')} · "
                        f"{CHANNELS[row['channel']]} · {row['created_at']} UTC  \nBrief: {row['brief']}")
            show_copy(row["variant"], row["channel"])
            c1, c2, _ = st.columns([1, 1, 3])
            if row["status"] == "approved":
                if c1.button("Unapprove", key=f"unapprove{row['id']}", use_container_width=True):
                    set_copy_status(row["id"], "saved")
                    st.rerun()
            elif c1.button("Approve", key=f"reapprove{row['id']}", use_container_width=True):
                set_copy_status(row["id"], "approved")
                st.rerun()
            confirm_key = f"confirm_delete{row['id']}"
            if not st.session_state.get(confirm_key):
                if c2.button("Delete", key=f"delete{row['id']}", use_container_width=True):
                    st.session_state[confirm_key] = True
                    st.rerun()
            else:
                st.warning("Delete this copy permanently? This cannot be undone.")
                d1, d2, _ = st.columns([1, 1, 3])
                if d1.button("Confirm delete", key=f"yes{row['id']}", type="primary", use_container_width=True):
                    delete_copy(row["id"])
                    del st.session_state[confirm_key]
                    st.rerun()
                if d2.button("Cancel", key=f"no{row['id']}", use_container_width=True):
                    del st.session_state[confirm_key]
                    st.rerun()
