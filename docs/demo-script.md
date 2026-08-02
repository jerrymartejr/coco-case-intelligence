# Demo script — shot list for the submission video

Target: **under 5 minutes after editing** (the form allows 3-5). Record the shots below
in order; the only shot that needs editing is the `dbt build`, which you fast-forward to
its final PASS wall. Every prompt is written out; type them verbatim.

The order is deliberate: input → processing → output, which is what the submission form
asks the video to show, with the inference demonstrated before anything else is claimed.

Cutaway slides come from the deck (`handoff/deck.html`, full-screened in a browser tab —
arrow keys to advance). A slide introduces each segment in one idea; the screen right
after it proves the idea for real. Slides explain, the screen proves.

**Before you record**

- [ ] The **pinned** database is never touched on camera: no `dbt` commands in the main
      repo. The live build happens in the demo clone (`~/personal-dev/
      coco-case-intelligence-demo`), which targets the throwaway `CASE_INTEL_DEMO`
      database — see `handoff/demo-build-runbook.md`.
- [ ] Two terminals ready: **T1** in the demo clone (`.env` sourced, for the build),
      **T2** with CoCo open — `cortex -c case_intel`, already logged in (verified: it
      answered 115). Font readable at 1080p in both.
- [ ] The deck full-screened in one browser tab; the live app loaded in another
      (https://coco-case-intelligence.streamlit.app — recording the deployed URL is a
      judge-visible touch; load it now so the cold start is behind you).
- [ ] Cursor open with the four raw files as tabs (see Shot 2), word wrap on, font
      zoomed for 1080p.
- [ ] One PDF open in a viewer: `data/synthetic/documents/esc_0003.pdf`, minimized.
- [ ] Screen recorder capturing screen + mic. One take per shot is fine; Filmora joins
      them.

**Numbers as of the pinned build** — say these, but check the screen: 614 records,
192 planted cases, 244 cases produced by the resolver, 41 PDFs. (The demo-clone build
will produce its own numbers; you never read numbers from it on camera — only its PASS
wall.)

---

## Shot 1 · SLIDE 1 — The problem (~10s)

**Show:** deck slide 1.

**Say:** "One customer with one problem contacts support five times, in five different
systems. Together, those five records are one *case*: the full story of that problem.
But nothing in the data connects them, so every number a support leader sees is wrong."

---

## Shot 2 · The mess — INPUT (~30s)

**Show:** Cursor, with the four raw files open as tabs, word wrap on, font zoomed.
Click through a tab as you name each format, then bring up the PDF:

- `data/synthetic/unstructured/chat.ndjson`
- `data/synthetic/unstructured/email.ndjson`
- `data/synthetic/unstructured/qa_notes.ndjson`
- `data/synthetic/unstructured/csat.ndjson`

**Say:** "Five formats. A chat transcript. An email. A QA note. A CSAT survey. And this
one is a real PDF escalation form. It lives in Snowflake as a binary file. Same
customer, same problem, five different systems. And none of these records share an ID.
There is no case ID anywhere in this data."

---

## Shot 3 · The project and the tools (~30s)

**Show:** Cursor, with the repo's file tree visible. Point at folders as you name them:
`models/` for the pipeline, `coco/skills/` for the skills, `app/` for the web app.

**Say:** "Here is the project. Everything runs inside Snowflake. That is the data
platform. It holds the raw records, and it also runs the AI, so the data never leaves.
The pipeline is written in dbt. That is the tool that turns raw data into finished
tables, step by step, with tests. The AI is Snowflake Cortex. It reads the PDFs, pulls
out the fields, and compares meanings. And there are two ways in. A Streamlit web app
for the visuals. And CoCo, the Cortex Code CLI, where you just ask questions. You will
see all of these in the next few minutes."

---

## Shot 4 · SLIDE 2 — One command (~15s)

**Show:** deck slide 2.

**Say:** "Everything you are about to see is built by one command. It parses the PDFs.
It normalizes all five formats. It links the records into cases. It summarizes each
case. It joins the business data. And it indexes everything for search. That is about
fifteen hundred Cortex AI calls. At the end, four accuracy tests run. If the linking
gets worse, the build fails."

---

## Shot 5 · `dbt build`, live — PROCESSING (~40s edited; ~6 min raw)

**Show:** T1, in the demo clone.

**Type:**

```bash
dbt build --profiles-dir .
```

**Say (over the first seconds, as models start streaming):** "This is running for real,
right now. It is reading the 41 PDFs, normalizing 614 records, and linking them into
cases. I will fast-forward."

**Then:** let it run to the end. In Filmora, speed-ramp the middle; land and HOLD on the
final wall: `Done. PASS=… ERROR=0`.

**Say (over the PASS wall):** "Done. Everything built, and all four accuracy tests
passed. Those tests score the linking against a hidden answer key, and that key
includes cases designed to break the system. The full results are in the repo and the
app. Everything you see from here runs on what this build just produced."

> If the build errors on camera: stop the take, check `handoff/demo-build-runbook.md`
> §recovery, re-run. Two full builds are budgeted for takes.

---

## Shot 6 · SLIDE 3 — The six skills (~25s)

**Show:** deck slide 3.

**Say:** "Before I open the CLI, here are the six skills this repo gives CoCo. Search
finds the actual records and quotes what customers wrote. Ask answers counts and
totals. Explain shows why records were grouped into one case. Diagnose ranks what is
hurting the business most. Recommend turns the top problem into a concrete action. And
deliver sends it to the right team, or drafts the message if nothing is connected. You
will see five of these in the next two minutes."

---

## Shot 7 · Ask one question — OUTPUT begins (~45s)

**Show:** T2, CoCo.

**Say first, before typing:** "This is CoCo, Snowflake's Cortex Code CLI. It is
connected to the same account, with those six skills loaded. First question. Plain
English. The kind a support leader actually asks."

**Type:**

```
What are customers actually saying about damaged items in multi-unit orders?
```

**Expect:** `search_case_records` fires, queries the `CASE_RECORD_SEARCH` Cortex Search
service, and answers by quoting real records — PDF escalation forms, customer emails and
QA notes, each named by `record_id`, grouped into about five distinct cases, with
revenue at risk attached to the unresolved ones.

**Say:** "One question. The answer quotes a PDF, an email, and a QA note. It knows
which case each record belongs to, and how much money that case puts at risk. That
grouping does not exist in the source data. The system figured it out."

> If retrieval is slow, keep talking — it answers in seconds once warm; you warmed it in
> the checklist.

---

## Shot 8 · SLIDE 4 — How linking works (~10s)

**Show:** deck slide 4.

**Say:** "To link two records, three signals have to agree. Who the record names. When
it arrived. And what it is about. And the links are not thrown away. Every one is kept
as evidence."

---

## Shot 9 · "Why are these one case?" — the heart (~60s)

**Show:** T2, CoCo.

**Type:**

```
Why are the records in CASE_G007 one case? Show me the evidence for each link, and tell me whether it is fully keyless.
```

**Expect:** `explain_case_linkage` names Viktor Sokolov, five records across five
channels inside a ~17-hour window, all ten edges semantic, cosines from 0.712 to 0.877,
and states the case is fully keyless.

**Say:** "Look at this. Ten links, and not one of them used an ID. It connected a PDF
form, a chat, an email, a survey, and a QA note, because they name the same person,
happened around the same time, and describe the same problem. And it can show its work.
Every link is saved in a table, with the reason behind it."

**Then switch to the app tab** — it opens on CASE_G007 by default.

**Say:** "Here is the same case in the app. The five records on the left. Every link on
the right, with the reason it was made."

---

## Shot 10 · What it costs, and what to do (~50s)

**Show:** T2, CoCo. Two prompts, in order.

**Type:**

```
What is the biggest driver of revenue at risk, and why?
```

**Expect:** `diagnose_top_drivers` ranks by `root_cause_category` and names the top
driver with its case count and total.

**Type:**

```
Recommend a concrete action for that driver, and draft the message to send the owning team.
```

**Expect:** `recommend_action` then `deliver_action`. **`deliver_action` returns a
formatted, ready-to-send message rather than posting it, because no Slack or ticketing
MCP target is configured.** Say so plainly — do not discover it live:

**Say:** "Nothing is connected to Slack or a ticketing tool here. So instead of posting
the message, it hands it back, ready to send. That is on purpose. If a delivery target
exists, it posts. If not, it drafts."

---

## Shot 11 · SLIDE 5 — Close (~20s)

**Show:** deck slide 5 (the two links, big). Read them out.

**Say:** "So that is Case Intelligence. Five formats, including a real binary PDF.
Linked into cases with no shared key. Joined with the order and survey data. Measured
honestly, including where it fails. And all of it works through plain English in CoCo.
The whole pipeline is one command, and accuracy is a build gate. If the linking gets
worse, the build fails."

Live app: **https://coco-case-intelligence.streamlit.app** · Repo:
**https://github.com/jerrymartejr/coco-case-intelligence**

---

## Edit notes (Filmora)

- Only shot 4 needs surgery: keep ~10s of the build starting, speed-ramp the middle,
  hold ≥3s on the PASS wall.
- Trim dead air between shots; keep the CoCo answers readable — pause on each quoted
  record for a beat.
- Edited target: 4:30-5:00. If over, shorten shots 3 and 10 first; never shot 5 or 9.

## If something goes wrong

| Symptom | Do this |
|---|---|
| CoCo picks the wrong skill | Re-ask using the words in the skill's trigger list, e.g. "show me the evidence" for linkage. |
| Retrieval slow | Keep talking; it lands in seconds once warm. |
| Build fails in the clone | `handoff/demo-build-runbook.md` §recovery; two full builds are budgeted. |
| App tab asleep | Reload; it re-wakes. That's why the pre-flight loads it first. |
| Anything worse | Stop, breathe, redo the shot. Nobody is judging the number of takes. |
