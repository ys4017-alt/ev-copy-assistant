# Team decisions

Decisions the team makes together. When an item is decided, fill in **Decision**, **Why** and **Date**,
then move it from "Pending" to "Decided". Details and pros/cons for each item are in the Team Decision tab of
[`project_steps_share_en.html`](project_steps_share_en.html).

## Pending

| # | What to decide | Options | Current state | Decision | Why | Date |
|---|---|---|---|---|---|---|
| 1 | Re-test retrieval with human-written questions | Questions per person · deadline · who checks the answers | Only one so far (`data/eval_questions_user.json`, U01) | | | |
| 2 | Length limits per channel, especially **email body length** | ① Stronger instructions ② Adjust the limit (e.g. 90–200 words; update guide section 6.3 and `check.py` too) ③ Add a rewrite pass that only fixes length | Email bodies come out at 98–107 words; the limit is 120–200 | | | |
| 3 | Confirm or revise the brand comparison guide (`data/brand_comparison.md`) | Confirm / revise each of its 5 parts | In use as the reference since Step 2-2b | | | |
| 4 | Finalize the 22 judge answer sentences (`data/judge_labels.json`) | Verdict rule · J04 · J20 · new test sentences. Label without looking at the judge's output first | Provisional; judge agreement 86% (tuned on the same set) | | | |
| 5 | Use approved copy as few-shot examples first | Approved first / synthetic ads only / mix | Implemented as "approved first" (`retrieval.get_examples`) | | | |
| 6 | Groq key on the professor's computer | A. The professor gets a free key / B. The team sends one and revokes it after grading | Without a key, `/health`, `/options`, `/retrieve`, `/check`, `/copies` still work | | | |
| 7 | Which `ev.db` goes in the submission image | Clean / keep approved copy as examples | Kept for now: 3 example copies (2 approved, 1 saved) | | | |
| 8 | Connect ACN-Data charging records to copy generation | A. Connect for industry-wide claims only, with a source, never next to a model name / B. Leave out and explain in the report | Not connected. The records have no car model or brand and only show charging habits at one workplace garage (Caltech) in 2018–2020. The proposal lists ACN-Data | | | |

## Decided

| # | What | Decision | Why | Date |
|---|---|---|---|---|
| | | | | |
