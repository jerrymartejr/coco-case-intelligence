# Demo script — 4 minutes

A shot list for the submission video. Every prompt is written out; type them verbatim.
The order is deliberate: the *inference* first, what it costs second. A judge who watches
only the first ninety seconds should already have seen the hard thing working.

**Before you record**

- [ ] `dbt build` is green and **do not run it again**. `resolved` is a judgement the model
      makes per case, so the unresolved count and the revenue total shift slightly on every
      rebuild. Rebuild mid-recording and the numbers on screen stop matching what the agent
      says.
- [ ] `bash scripts/register_skills.sh`, then `cortex -c case_intel` **once** and complete
      the login, so no browser window appears mid-take. (If your connection is named
      something else, use that name. It needs browser or PAT auth — CoCo's SQL tool cannot
      use the key pair dbt authenticates with.)
- [ ] Streamlit is open in a tab and has finished its first load, so the cold-start pause
      is behind you. `streamlit run app/streamlit_app.py`
- [ ] One PDF open in a viewer: `data/synthetic/documents/esc_0003.pdf`
- [ ] Terminal font large enough to read at 1080p.

**Numbers as of the pinned build** — say these, but check the screen: 614 records,
192 planted cases, 244 resolved cases, 41 PDFs.

---

## 0:00 — 0:30 · The mess

**Show:** a split of four raw source files, then the PDF.

```bash
head -c 400 data/synthetic/unstructured/chat.ndjson
head -20 seeds/raw_email.csv
```

Then open `esc_0003.pdf` on screen.

**Say:** "Five formats. A chat transcript, an email with headers, a QA note, a CSAT
survey, and this — a real PDF escalation form, sitting in a Snowflake stage as a binary
file. Same customer, same problem, five different systems. And not one of these records
carries an identifier that any of the others share. There is no case id in this data
anywhere."

---

## 0:30 — 1:10 · Ask one question, get an answer that spans all five

**Show:** the terminal, CoCo already open.

**Type:**

```
What are customers actually saying about damaged items in multi-unit orders?
```

**Expect:** `search_case_records` fires. It queries the `CASE_RECORD_SEARCH` service and
answers by quoting real records — PDF escalation forms, customer emails and QA notes,
each named by `record_id`, grouped into about five distinct cases, with revenue at risk
attached to the unresolved ones.

**Say:** "One question. The answer is quoting a PDF, an email and a QA note, and it knows
which *case* each belongs to and what that case is worth. That grouping is not in the
source data. It was inferred."

> If retrieval is slow, keep talking — the service has a one-day target lag and answers
> in a few seconds once warm. This is why you warmed it in the checklist.

---

## 1:10 — 2:10 · "Why are these one case?" — the heart of it

**Type:**

```
Why are the records in CASE_G007 one case? Show me the evidence for each link, and tell me whether it is fully keyless.
```

**Expect:** `explain_case_linkage` fires and returns roughly this: Viktor Sokolov, five
records across five channels inside a 17.3-hour window, **all ten edges semantic**, cosine
similarities from 0.712 to 0.877, and the explicit conclusion that the case is fully
keyless — no email address, no order reference, no resolved customer used anywhere.

**Say:** "Ten links, every one of them made without an identifier. A binary PDF tied to a
chat message by a surname, the meaning of the complaint, and thirteen hours. And it is not
asserting that — those edges are a table. The system kept its own reasoning."

**Then switch to Streamlit**, top section, *Case anatomy*. It opens on `CASE_G007` by
default. Scroll the member records, then point at the evidence list and the graph.

**Say:** "Same case, same evidence, drawn out. Five formats down the left, and each edge
labelled with what justified it."

---

## 2:10 — 2:50 · How do we know it is right?

**Show:** the *How do we know the linking is right?* panel in Streamlit.

**Say:** "This is scored against a ground-truth key the pipeline never reads. Tiers A, B
and C are at 100% — but I would not lead with that, because those tiers are generated
under exactly the conditions the resolver needs, so a perfect score there measures my
generator, not my method.

Tier D is the real number. It breaks those conditions on purpose, at collision rates taken
from real-shaped reference data where 82% of customers share a surname with someone.

Look at the two extremes. Where two different people share a surname, write in the same
hours, about the same issue, *and* carry identity evidence — precision 1.000. The order
proves they are two people; nothing in the text could. And where they carry no identifier
at all — precision **zero**. Every pair merges. That is the honest limit of keyless
linking, and it is the reason the structured side is in this system at all."

---

## 2:50 — 3:40 · What it costs, and what to do

**Type:**

```
What is the biggest driver of revenue at risk, and why?
```

**Expect:** `diagnose_top_drivers` ranks by `root_cause_category` — the controlled
vocabulary, not the free text — and names the top driver with its case count and total.

**Then:**

```
Recommend a concrete action for that driver, and draft the message to send the owning team.
```

**Expect:** `recommend_action` then `deliver_action`. **`deliver_action` will return a
formatted, ready-to-send message rather than posting it, because no Slack or ticketing MCP
target is configured.** Say so plainly — do not discover it live:

**Say:** "No delivery integration is wired up here, so it hands back the message ready to
send. That fallback is deliberate: the skill checks for a target and degrades to drafting
rather than failing."

---

## 3:40 — 4:00 · Close

**Say:** "Five formats including a binary one, linked into cases with no shared key, fused
with the structured order and CSAT data, measured against ground truth including where it
breaks, and all of it queryable in plain English through CoCo. The whole pipeline is one
`dbt build`, and accuracy is a build gate — if the linking regresses, the build fails."

**Show:** the repo URL and the live app URL on screen.

<!-- TODO: paste the deployed Streamlit URL here once it is live, and read it out. -->

---

## If something goes wrong

| Symptom | Do this |
|---|---|
| CoCo picks the wrong skill | Re-ask using the words in the skill's trigger list, e.g. "show me the evidence" for linkage. |
| A browser login pops up | You skipped the checklist. Cut, log in, restart the take. |
| Streamlit is slow on first paint | The recommendation panel makes a live Cortex call. It is the last thing to fill in; keep talking. |
| A number on screen differs from this script | Trust the screen. Someone rebuilt. Never say a figure you have not just read. |
