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

**Say:** "Five formats. A chat transcript, an email with headers, a QA note, a CSAT
survey, and this — a real PDF escalation form, sitting in a Snowflake stage as a binary
file. Same customer, same problem, five different systems. And not one of these records
carries an identifier that any of the others share. There is no case id in this data
anywhere."

---

## Shot 3 · SLIDE 2 — One command (~15s)

**Show:** deck slide 2.

**Say:** "Everything you're about to see is built by one command. Six stages: parse the
PDFs, normalize all five formats with AI_COMPLETE, embed and link the records,
synthesize each case, fuse the structured data, index everything for retrieval — about
fifteen hundred Cortex calls — and four accuracy gates at the end that fail the build if
the linking regresses."

---

## Shot 4 · `dbt build`, live — PROCESSING (~40s edited; ~6 min raw)

**Show:** T1, in the demo clone.

**Type:**

```bash
dbt build --profiles-dir .
```

**Say (over the first seconds, as models start streaming):** "This is running for real,
right now — parsing the 41 PDFs out of the stage, normalizing 614 records, embedding
them, linking them into cases. I'll fast-forward."

**Then:** let it run to the end. In Filmora, speed-ramp the middle; land and HOLD on the
final wall: `Done. PASS=… ERROR=0`.

**Say (over the PASS wall):** "Done. Every model built, and all four accuracy gates
passed, scored against a hidden answer key that includes an adversarial tier built to
make the method fail. The full measurement is in the repo and the app. From here on,
everything you see is queries over what this build just proved."

> If the build errors on camera: stop the take, check `handoff/demo-build-runbook.md`
> §recovery, re-run. Two full builds are budgeted for takes.

---

## Shot 5 · SLIDE 3 — The six skills (~25s)

**Show:** deck slide 3.

**Say:** "Before I open the CLI: the repo registers six agent skills with CoCo. Search
finds the actual records and quotes what customers wrote. Ask answers counts and totals.
Explain shows the evidence for why records were grouped into one case. Diagnose ranks
what is hurting most. Recommend turns the top driver into a concrete action. And deliver
routes it to the owning team, or drafts the message when no integration is wired. You
will see five of them fire in the next two minutes."

---

## Shot 6 · Ask one question — OUTPUT begins (~45s)

**Show:** T2, CoCo.

**Say first, before typing:** "Here is CoCo, Snowflake's Cortex Code CLI, connected to
the same account, with those six skills registered. First question, in plain English,
the kind a support leader actually asks."

**Type:**

```
What are customers actually saying about damaged items in multi-unit orders?
```

**Expect:** `search_case_records` fires, queries the `CASE_RECORD_SEARCH` Cortex Search
service, and answers by quoting real records — PDF escalation forms, customer emails and
QA notes, each named by `record_id`, grouped into about five distinct cases, with
revenue at risk attached to the unresolved ones.

**Say:** "One question. The answer is quoting a PDF, an email and a QA note, and it
knows which *case* each belongs to and what that case is worth. That grouping is not in
the source data. It was inferred."

> If retrieval is slow, keep talking — it answers in seconds once warm; you warmed it in
> the checklist.

---

## Shot 7 · SLIDE 4 — How linking works (~10s)

**Show:** deck slide 4.

**Say:** "Three signals have to agree — who the record names, when it arrived, and what
it means. And the links aren't thrown away after linking: every edge is kept as
evidence."

---

## Shot 8 · "Why are these one case?" — the heart (~60s)

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

## Shot 9 · What it costs, and what to do (~50s)

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

## Shot 10 · SLIDE 5 — Close (~20s)

**Show:** deck slide 5 (the two links, big). Read them out.

**Say:** "Five formats including a binary one, linked into cases with no shared key,
fused with the structured order and CSAT data, measured against ground truth including
where it breaks — and all of it queryable in plain English through CoCo. The whole
pipeline is one `dbt build`, and accuracy is a build gate — if the linking regresses,
the build fails."

Live app: **https://coco-case-intelligence.streamlit.app** · Repo:
**https://github.com/jerrymartejr/coco-case-intelligence**

---

## Edit notes (Filmora)

- Only shot 4 needs surgery: keep ~10s of the build starting, speed-ramp the middle,
  hold ≥3s on the PASS wall.
- Trim dead air between shots; keep the CoCo answers readable — pause on each quoted
  record for a beat.
- Edited target: 4:30-5:00. If over, shorten shot 9 first; never shot 4 or 8.

## If something goes wrong

| Symptom | Do this |
|---|---|
| CoCo picks the wrong skill | Re-ask using the words in the skill's trigger list, e.g. "show me the evidence" for linkage. |
| Retrieval slow | Keep talking; it lands in seconds once warm. |
| Build fails in the clone | `handoff/demo-build-runbook.md` §recovery; two full builds are budgeted. |
| App tab asleep | Reload; it re-wakes. That's why the pre-flight loads it first. |
| Anything worse | Stop, breathe, redo the shot. Nobody is judging the number of takes. |
