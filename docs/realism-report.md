# Realism report: Francis's and Jim's reference datasets

What realistic BPO data looks like, measured from the two teammate datasets, as raw material for
`scripts/generate_synthetic_data.py`. Neither dataset is loaded by the pipeline and neither will be.
These are patterns to copy into our generator, not inputs.

Sources: `origin/develop/fsdc-unstructured-data` (Francis, 4 NDJSON files, 40,000 records) and
`origin/faker_synthetic_data` / PR #1 (Jim, 6 CSV + 3 JSON, 11,137 interactions + 1,600 customers).
Measured 2026-07-26.

Guardrails this report is written against: our synthetic run stays the pinned proof (now 170/170 cases linked,
plus the two linkage asserts), and any entity-pool expansion stays small and name-controlled. Nothing below should
be read as a recommendation to adopt a pool at Jim's scale. See the last section.

---

## 1. Entities

### Francis

- **10 distinct customers**, each appearing in exactly 1,000 cases. Names are two-token
  `First Last`, deliberately multi-ethnic and Philippines/SEA-flavoured: Joy Okafor, Maya Tan,
  Daniel Reyes, Aisha Khan, Miguel Santos, Priya Nair, Noah Lim, Grace Chen, Sam Rivera, Lina Cruz.
- **Last-name collision rate: zero.** All 10 surnames distinct, which is the same property our
  generator relies on.
- Emails are `first-initial.lastname@example.com` (`j.okafor@example.com`). One email per customer,
  no variants, no typos.
- **6 agents**, mnemonic style: `A_ROSA`, `A_DAN`, `A_IVAN`, `A_LEO`, `A_MIKA`, `A_SARA`.
  Plus **4 QA reviewers**: `QA_NORA`, `QA_ELI`, `QA_JIN`, `QA_MAE`.
- 10,000 order refs, `ORD_1001` upward, exactly one per case.
- Identity coverage per channel: email has name + email + order_ref, chat has name + email +
  order_ref, CSAT has name + email + order_ref, QA has neither name nor email (agent and reviewer only).

**Correction to an earlier read:** chat carries `order_ref`, and 10,000 of 10,000 chat order refs
match an email order ref one-to-one. Chat is not unrecoverable, its case is fully determined by
`order_ref`. Chat is missing `case_id`, not missing a key.

### Jim

`customers.csv` (1,600): `customer_id, first_name, last_name, display_name_used, email, phone,
country, city, account_created, vip_flag, preferred_language, product_owned`

`agents.csv` (75): `agent_id, agent_name, site, team, supervisor, hire_date, tenure_months,
language, shift, employment_type`

- IDs are zero-padded: `CUST00001`, `A001`, `PROD001`.
- Emails are `first.last` + 1 to 3 trailing digits (`holly.davis915@outlook.com`). Digit count:
  3 digits 1,456, 2 digits 129, 1 digit 15.
- **Last-name collision rate is severe: 1,600 customers share only 617 surnames.** 336 surnames are
  used by more than one customer, 1,319 customers (82%) collide with at least one other, giving
  **4,359 colliding pairs**. Worst: 37 Smiths, 25 Johnsons, 23 Jones, 23 Williams, 20 Browns.
  22 pairs share an identical full name. This is why the pool cannot be adopted wholesale.
- Agents are much safer: 75 agents, only 6 surname collisions (2 each).
- Supervisors: 6 named supervisors across 75 agents (spans of 9 to 20).
- Attributes worth copying: `vip_flag` 121 true / 1,479 false (7.6%), `preferred_language` spread
  across Tagalog 415, English 413, English/Tagalog 392, Cebuano 380, `tenure_months` 1 to 60,
  `account_created` 2022-07-23 to 2026-05-21.
- Agent org attributes: sites Remote-PH 22, Manila 21, Cebu 16, Davao 16; teams Billing Support 20,
  General Care 16, Technical Support 15, Retention 15, VIP Desk 9; shifts AM/PM/Mid/Night;
  employment Contractual 31, Probationary 22, Regular 22.

---

## 2. Noise recipes (exact)

### Jim (the strongest material in either dataset)

**Typo email domains.** 150 of 1,600 customers (9.4%) sit on a misspelled domain, each a realistic
single-keystroke error of a real one:

| domain | count | corrupts |
|---|---|---|
| `hotmial.com` | 44 | hotmail.com (357) |
| `yaho.com` | 39 | yahoo.com (373) |
| `outlok.com` | 37 | outlook.com (377) |
| `gmial.com` | 30 | gmail.com (343) |

**Phone format variants.** Four formats, evenly split across the pool, all the same PH mobile number
underneath:

| format | count | example |
|---|---|---|
| `(9999) 999-9999` | 409 | `(0917) 670-6562` |
| `+999999999999` | 398 | `+639178122362` |
| `999999999999` | 397 | `009177080531` |
| `9999999999` | 396 | `9179096705` |

**Display-name divergence (the best one).** For 351 of 1,600 customers (22%) `display_name_used` is a
completely different first name from `first_name`, and the email is built from the display name, so
the address contradicts the account holder:

- `Christopher Powell` uses display name `Stacy`, email `stacy.powell757@yahoo.com`
- `Tammy Wilson` uses display name `Douglas`, email `douglas.wilson610@yahoo.com`
- `Logan Ramos` uses display name `Olivia`, email `olivia.ramos760@outlok.com` (also a typo domain)

Note the surname survives in the local part in every case, so a surname-anchored bridge still works
where a first-name match would fail.

**Unplanted noise (Faker leakage, do not copy).** 476 of 1,600 customers have a non-Philippines
country across 199 distinct countries (Suriname 7, Saint Helena 6, Western Sahara 6), and cities are
Faker placeholders (`East Ethan`, `New Mary`, `Michaelburgh`) rather than PH cities.

### Francis

No entity-level noise at all: one clean email per customer, no typos, no format variance, no aliases.

Text is the opposite of noisy, it is **fully templated**. Each channel has exactly **10 distinct
texts across 10,000 records**, one per issue archetype, repeated 1,000 times verbatim:

| channel | records | distinct texts | mean chars |
|---|---|---|---|
| email body | 10,000 | 10 | 248 |
| chat transcript | 10,000 | 10 | 358 |
| QA note | 10,000 | 10 | 235 |
| CSAT verbatim | 10,000 | 10 | 249 |

So unrelated records are not near-duplicates, they are exact duplicates. Any two records of the same
archetype are character-identical.

---

## 3. Taxonomies

### Francis: 10 issue archetypes, perfectly uniform at 1,000 each

Email subject / QA + CSAT `product_area` pair up one to one:

| subject | product_area |
|---|---|
| Refund Delay | refunds |
| Multi Factor Authentication | account_access |
| Duplicate Charge | billing |
| Address Update Failed | delivery |
| Payment Failure | payments |
| Handoff Repetition | technical_support |
| Return Policy Exception | returns |
| App Crash | mobile_app |
| Misleading Warranty Statement | warranty |
| Cancellation Confirmation | subscription |

QA also carries `risk_level` (high 5,000 / medium 5,000, no low) and 10 distinct `required_action`
strings, one per archetype.

### Jim: 11 email subjects, skewed toward repeat contact

`Following up again` 1,392, `Billing inquiry` 354, `Refund inquiry` 220, `Shipping Delay inquiry` 205,
`Technical Bug inquiry` 201, `Subscription Cancellation inquiry` 153, `Wrong Item inquiry` 120,
`Feature Request inquiry` 118, `Warranty inquiry` 85, `Missing Order inquiry` 82, `Other inquiry` 77.

That `Following up again` is 46% of email traffic is the single most interesting taxonomy fact in
either dataset: it models recontact as the dominant volume driver, which matches real BPO behaviour.

Jim's chat/call topics come from a pool of **58 distinct customer opening lines**, clustering into
billing (`My bill doesn't look right` 131, `There's an extra charge I don't recognize` 124,
`I was charged twice this month` 114), account access (`My account seems locked` 106,
`It keeps saying invalid credentials` 105, `I can't log into my account` 99,
`I never got the password reset email` 96, `I need help resetting my password` 93,
`The reset link isn't working` 75), refunds (`I was told my refund was processed but I don't see it`
81, `Where is my refund?` 76, `I requested a refund and it still hasn't arrived` 70), app/technical
(`The app keeps crashing` 79, `I found a bug after the last update` 69), delivery
(`My package is really late` 67, `My order hasn't arrived yet` 65).

Above those sit 4 explicit **recontact openers** which are the four most common lines overall:
`This is the second time I'm reaching out about the same issue` 489, `I called about this already,
following up again` 460, `I was told this was resolved but it clearly isn't` 433,
`I chatted about this yesterday and it's still not fixed` 423.

---

## 4. Value distributions

### Jim: products

15 products, 5 brands (Northgate 5, Vela Home 4, Kindred Goods 3, Cascade Media 2, BrightPath 1).
Names are `<brand> <word> <Plan|Suite>`, for example `Kindred Goods Get Plan`, `Vela Home National Suite`.
Subscription types: Monthly 4, Annual 4, Trial 4, Lifetime 3.
`monthly_price` min 7.69, max 88.73, mean 50.94, median 56.31, roughly uniform.
Each product is owned by 84 to 123 customers.

### Jim: workforce_metrics

3,379 rows, 75 agents, 60 distinct dates, **2026-01-26 to 2026-07-22**, about 45 rows per agent
(sparse, not every agent every day).

| column | min | max | mean | median | sd |
|---|---|---|---|---|---|
| calls | 15 | 60 | 37.49 | 37.0 | 13.20 |
| aht (sec) | 180.1 | 719.7 | 450.50 | 450.2 | 155.69 |
| fcr | 0.55 | 0.92 | 0.736 | 0.739 | 0.108 |
| occupancy | 0.60 | 0.95 | 0.775 | 0.774 | 0.101 |
| adherence | 0.80 | 0.99 | 0.896 | 0.897 | 0.055 |
| csat | 3.2 | 4.8 | 4.016 | 4.02 | 0.46 |

All six are flat uniform draws inside plausible BPO bounds. Realistic ranges, no distribution shape,
no correlation between columns, no weekday effect.

### Jim: QA and CSAT scales

- QA `score` is **0 to 100** in practice 50 to 100, mean 83.0.
- CSAT `rating` is **1 to 5**, distribution 1:405, 2:220, 3:173, 4:435, 5:415, mean 3.14. Bimodal,
  which is realistic for support surveys.
- **QA score and CSAT rating correlate at r = 0.62** on the 164 interactions carrying both. This is
  the one deliberate cross-table coherence in the dataset and it is worth reproducing.
- The coherence does not extend up a level: `workforce_metrics.csat` is **uncorrelated with the same
  agent's own interaction CSAT (r = -0.05)**, and the levels disagree (4.02 versus 3.14).
- CSAT comment is one of exactly 3 strings, keyed loosely to rating: `Quick and easy, thanks!` 644,
  `The issue wasn't fixed.` 625, `Took a while but got sorted eventually.` 379.
- QA `notes` is one of exactly 2 strings: `Agent followed protocol correctly and confirmed resolution
  with customer.` 849, `Agent closed interaction prematurely; customer issue was not fully addressed.` 292.

### Francis: scales and time

- CSAT `score` is 1 to 5 but **constant per product_area**: refunds always 2, account_access 2,
  billing 3, delivery 2, payments 2, technical_support 1, returns 5, mobile_app 1, warranty 1,
  subscription 3. Distribution 1:3,000, 2:4,000, 3:2,000, 5:1,000, **no 4s**, mean 2.20. Zero
  within-category variance.
- QA has **no numeric score**, only `risk_level` high/medium.
- Timestamps are **stratified by channel, not interleaved by case**:

| channel | window |
|---|---|
| email | 2026-07-21 to 2026-07-28 |
| chat | 2026-08-04 to 2026-08-11 |
| QA note | 2026-08-18 to 2026-08-25 |
| CSAT | 2026-09-01 to 2026-09-07 |

- Consequence: **every case has an intra-case spread of exactly 41.67 days**, min = median = max.
  Temporal proximity carries no information in this dataset, and the channel ordering is rigid
  (email, then chat, then QA, then CSAT, always). Our generator's tight per-case time clustering is
  the more useful pattern, and it is the one Stage 2 actually depends on.
- Top-level `received_ts` duplicates the inner channel timestamp exactly.

---

## 5. Text realism

### Francis

| channel | structure | mean chars | turns |
|---|---|---|---|
| email | single `body` blob, formal register | 248 | n/a |
| chat | `transcript` array of `{role, text}` | 358 | always 5 |
| QA note | single `notes` blob + `required_action` | 235 | n/a |
| CSAT | single `verbatim` blob | 249 | n/a |

The archetype prose is genuinely good, and it is composed in a **three-part structure** worth copying
directly: *issue* ("I need help because X"), *impact* ("This matters because Y"), *ask* ("Please Z").

Sample, email, Refund Delay:

> Hi support, I need help because the refund still shows as pending after the returned item was
> received. This matters because the customer needs the money before the billing cycle closes.
> Please confirm the refund status and provide an escalation path.

Sample, email, Payment Failure:

> Hi support, I need help because the card was charged but the order page says payment failed. This
> matters because the customer needs either a released hold or a completed order. Please confirm
> authorization status and resolve the payment mismatch.

The same case is then **re-voiced per channel**, which is exactly the paraphrase behaviour our
semantic pass has to survive. Chat lowercases and fragments the identical content:

> customer: hey, I need help because the refund still shows as pending after the returned item was received
> agent: Thanks for reaching out, let me take a look into this for you.
> customer: this matters because the customer needs the money before the billing cycle closes
> agent: I am reviewing the account history and case details now.
> customer: please confirm the refund status and provide an escalation path

QA re-voices it in auditor register with an explicit `Case context:` / `Customer impact:` frame:

> Agent acknowledged the delay but did not explain the processing window. Case context: the refund
> still shows as pending after the returned item was received. Customer impact: the customer needs
> the money before the billing cycle closes.
> action: Coach on expectation setting and refund escalation criteria.

CSAT re-voices it in first person:

> The agent was polite, but I still do not know when the refund will arrive. The main issue was that
> the refund still shows as pending after the returned item was received. I wanted support to confirm
> the refund status and provide an escalation path.

Weakness: the re-voicing is a lexical transform, not a genuine paraphrase. The issue clause is
copied word for word into all four channels, so string overlap alone would link them. The two useful
parts are the **channel register shift** and the **three-part composition**, not the sameness.

### Jim

| channel | structure | mean chars | turns |
|---|---|---|---|
| call | single `transcript` string with `Customer:` / `Agent:` inline | 162 | always 3 |
| chat | `messages` array of `{speaker, text}` | 135 | always 3, always customer/agent/agent |
| email | `subject` + `body` blob | 94 | n/a |

Composition is a sentence pool: one of 58 customer lines plus one or two of 11 agent lines, drawn
independently. Agent line pool in full: `I'll need to escalate this to get it fully resolved.`,
`I can see your account here, let me take a look.`, `Let me pull up the details on this.`,
`I found the record you're referring to.`, `Thanks for reaching out, I can help with this.`,
`I've gone ahead and resolved this for you.`, `This has been processed on our end now.`,
`I've corrected the issue, it should reflect shortly.`

Sample, call (`duration_seconds` 90 to 900, mean 501, uncorrelated with transcript length):

> Customer: My bill doesn't look right. Agent: I can see your account here, let me take a look.
> Agent: I'll need to escalate this to get it fully resolved.

Sample, chat:

> customer: I need help resetting my password.
> agent: I can see your account here, let me take a look.
> agent: I'll need to escalate this to get it fully resolved.

**Flag: email double-voice concatenation.** Jim's calls and chats keep speaker turns separate, but
the email `body` concatenates a customer line and an agent line into a single field with no
attribution, so the ticket reads as a customer writing in the support agent's voice:

> subject: Subscription Cancellation inquiry
> body: "I cancelled last month but got charged again. **I've gone ahead and resolved this for you.**"

> subject: Warranty inquiry
> body: "Is this still under warranty? **I'll need to escalate this to get it fully resolved.**"

Stage 1 would extract a garbled issue/resolution pair from these. Do not copy this pattern. If we
want agent voice in an email record, it belongs in a reply block or a separate field.

---

## 6. Schemas

### Francis (NDJSON, top level identical on all four: `record_id, received_ts, raw_content`)

| file | records | inner keys of `raw_content` |
|---|---|---|
| `email.ndjson` | 10,000 | message_id, channel, received_at, agent_id, customer_name, customer_email, from_email, to_email, subject, body, order_ref, case_id |
| `chat.ndjson` | 10,000 | session_id, channel, started_at, agent_id, customer_name, customer_email, order_ref, transcript[] |
| `qa_notes.ndjson` | 10,000 | audit_id, channel, reviewed_at, reviewer_id, agent_id, case_id, product_area, notes, required_action, risk_level |
| `csat.ndjson` | 10,000 | survey_id, channel, submitted_at, case_id, customer_name, customer_email, order_ref, product_area, score, verbatim |

### Jim

| file | rows | columns |
|---|---|---|
| `customers.csv` | 1,600 | customer_id, first_name, last_name, display_name_used, email, phone, country, city, account_created, vip_flag, preferred_language, product_owned |
| `agents.csv` | 75 | agent_id, agent_name, site, team, supervisor, hire_date, tenure_months, language, shift, employment_type |
| `products.csv` | 15 | product_id, brand, product_name, subscription_type, monthly_price |
| `csat_responses.csv` | 1,648 | survey_id, interaction_id, rating, comment |
| `qa_notes.csv` | 1,141 | qa_id, agent_id, interaction_id, score, notes |
| `workforce_metrics.csv` | 3,379 | date, agent_id, calls, aht, fcr, occupancy, adherence, csat |
| `call_transcripts.json` | 3,518 | call_id, interaction_id, caller, agent_id, duration_seconds, transcript |
| `chat_logs.json` | 4,612 | chat_id, interaction_id, customer_email, customer_phone, agent_id, messages[] |
| `email_tickets.json` | 3,007 | ticket, interaction_id, customer_email, agent_id, subject, body |

Neither dataset has anything resembling `orders`. Jim has no timestamp on any interaction. Jim's
`interaction_id` is strictly one record (zero overlap across his three channels, multiplicity 1 for
all 11,137), so his data contains no multi-record cases.

---

## 7. Harvest shortlist

Ranked by value to our generator, with the constraint that the entity pool stays small and
name-controlled.

1. **Jim's identity-noise recipes.** Typo domains at ~9%, four phone formats, and the 22%
   display-name divergence where the email contradicts the account first name but preserves the
   surname. Highest-value item in either dataset, and it hardens Stage 2 rather than threatening it.
2. **Francis's three-part issue composition** (issue / impact / ask) and his 10 archetypes, as
   additions to our issue catalog.
3. **Francis's per-channel register shift** (formal email, lowercase fragmented chat, auditor-voice
   QA, first-person CSAT) as the paraphrase model, but with genuinely reworded issue clauses rather
   than copied ones.
4. **Jim's recontact taxonomy.** Recontact as 46% of email volume, plus the four explicit recontact
   opener lines, which is a natural fit for our multi-record cases.
5. **Jim's operational value ranges** for agent metrics (aht 180 to 720s, fcr 0.55 to 0.92,
   occupancy 0.60 to 0.95, adherence 0.80 to 0.99, csat 3.2 to 4.8, calls 15 to 60) and the
   QA-to-CSAT r = 0.62 coherence.
6. **Jim's org and customer attributes** for texture: vip_flag at 7.6%, language mix, site/team/shift,
   tenure 1 to 60 months, product price band 7.69 to 88.73.

Explicitly do not copy: Jim's 1,600-name pool (4,359 surname collisions), Jim's email double-voice
concatenation, Jim's Faker country and city leakage, Francis's channel-stratified timestamps (the
constant 41.67-day intra-case spread), Francis's constant-per-category CSAT scores, and the exact
text duplication in both.
