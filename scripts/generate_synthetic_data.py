"""
Synthetic customer-support / BPO data generator for the Case Intelligence pipeline.

Produces BOTH halves of the contract so the pipeline runs end to end without waiting
on teammates, plus the ground-truth key that proves keyless linking worked:

  data/synthetic/unstructured/{chat,email,qa_notes,csat}.ndjson   (raw records)
  seeds/raw_*.csv                                                 (what dbt actually loads)
  seeds/orders.csv, seeds/csat_scores.csv, seeds/agent_daily_metrics.csv  (structured)
  data/synthetic/ground_truth.json + seeds/ground_truth_map.csv   (answer key)

Deterministic: fixed seed + fixed base date, so reruns reproduce and ground truth is stable.
Difficulty tiers per AGENTS.md: A = entity overlap, B = semantic only (hero), C = trivial,
D = adversarial, + noise.

Realism harvested from the teammate reference datasets (see docs/realism-report.md):
  - Jim: identity noise (typo domains ~9%, four phone formats, display-name divergence at
    ~22% where the email contradicts the account first name but preserves the surname),
    recontact as a dominant volume driver, operational value ranges for agent metrics,
    bimodal CSAT, QA-score/CSAT coherence, org attributes (site/team/shift/tenure/VIP).
  - Francis: the three-part issue composition (issue / impact / ask) and the per-channel
    register shift (formal email, lowercase fragmented chat, auditor-voice QA, first-person
    CSAT), plus a wider issue catalogue.

Deliberately NOT copied: large name pools with surname collisions (Jim's 1,600 customers
share only 617 surnames), channel-stratified timestamps (Francis's every-case-41.67-days
spread), constant-per-category CSAT, verbatim text reuse across channels, and Jim's
double-voice email bodies that mix customer and agent speech in one field.

The corpus has two halves, and the split is the point.

The MAIN corpus (tiers A, B, C and noise) is built so that Stage 2's assumptions hold:

  1. Every main-pool customer has a UNIQUE first name and a UNIQUE surname; noise names
     share neither with a customer nor with each other.
  2. Two cases belonging to the same main-pool customer are separated by more than
     MIN_SAME_CUSTOMER_GAP_H, which is comfortably wider than Stage 2's link window,
     so a repeat customer never collapses into one giant case.
  3. Records inside one case are tightly clustered in time (hours, not weeks).
  4. Channel texts for one issue are genuinely reworded, never copied, so the semantic
     pass is actually exercised rather than matching on string overlap.

Those four are exactly the conditions the resolver needs, which is why a perfect score on
the main corpus alone proves very little: the benchmark would be measuring the generator.
So the ADVERSARIAL corpus (tier D) deliberately breaks 1 and 2, at rates and in shapes
harvested from the reference datasets in docs/realism-report.md, where 82% of customers
collide on surname. Its three shapes are documented at ADVERSARIAL_CUSTOMERS below.

Tier D is scored separately and is expected to be imperfect. The main tiers stay at 100%
as a regression floor; tier D is where the method's real behaviour is measured.

`validate()` checks all of this before anything is written: the main invariants above, and
that tier D's violations are exactly the ones that were planted rather than accidents.

When real data arrives it replaces these outputs at the same schemas. No model changes.
"""

import csv
import itertools
import json
import os
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
BASE_DATE = datetime(2026, 5, 4, 8, 0, 0)  # a Monday, fixed for reproducibility
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNSTRUCT_DIR = os.path.join(HERE, "data", "synthetic", "unstructured")
SEEDS_DIR = os.path.join(HERE, "seeds")
GROUND_TRUTH = os.path.join(HERE, "data", "synthetic", "ground_truth.json")
DOCUMENTS_DIR = os.path.join(HERE, "data", "synthetic", "documents")

# Demo scale. Stage 1 is one AI_COMPLETE per record and Stage 2 is an O(N^2) pair scan,
# so this is sized for a demo that rebuilds in minutes, not for volume.
TARGET_CASES = 170
NOISE_RECORDS = 55

# Share of cases that also produce a PDF escalation form. Weighted toward the keyless
# tier on purpose: a document that can only be linked by surname, meaning and time is a
# far better demonstration of multi-modal understanding than one carrying an order ref.
DOCUMENT_RATE = 0.18

# Stage 2's link window and episode-gap bound, mirrored here so tier D can be planted
# relative to them. Keep in step with TIME_WINDOW_HOURS and MAX_EPISODE_GAP_HOURS in
# models/intermediate/int_linkage_graph.py.
LINK_WINDOW_HOURS = 72
MAX_EPISODE_GAP_HOURS = 24

# Must exceed LINK_WINDOW_HOURS with margin: it is what keeps a main-pool customer's
# separate cases from merging through the deterministic email/customer pass.
MIN_SAME_CUSTOMER_GAP_H = 24 * 10

RNG = random.Random(SEED)

# --------------------------------------------------------------------------------------
# Entity pools. Small and name-controlled on purpose: unique surnames are the anchor the
# keyless (Tier B) linking leans on, and collisions there are what would produce false
# merges. Jim's 1,600-name pool has 4,359 colliding surname pairs; we take his noise
# recipes, not his pool size.
# --------------------------------------------------------------------------------------

CUSTOMER_NAMES = [
    ("Joy", "Okafor"), ("Mika", "Tanaka"), ("Luca", "Becker"), ("Sana", "Nair"),
    ("Dana", "Owens"), ("Rui", "Silva"), ("Elias", "Haddad"), ("Nadia", "Petrova"),
    ("Grace", "Chen"), ("Miguel", "Santos"), ("Priya", "Kulkarni"), ("Noah", "Lim"),
    ("Aisha", "Rahman"), ("Tomas", "Vogel"), ("Ingrid", "Halvorsen"), ("Kofi", "Mensah"),
    ("Yuki", "Watanabe"), ("Lena", "Novak"), ("Diego", "Marquez"), ("Amara", "Nwosu"),
    ("Ravi", "Chandran"), ("Signe", "Lindqvist"), ("Hassan", "Farouk"), ("Bea", "Villanueva"),
    ("Oskar", "Dvorak"), ("Thandi", "Mbeki"), ("Jonas", "Reinhardt"), ("Camila", "Duarte"),
    ("Arjun", "Sethi"), ("Freya", "Andersen"), ("Marco", "Bellini"), ("Zineb", "Ouali"),
    ("Hana", "Kobayashi"), ("Teodora", "Ionescu"), ("Ismail", "Cetin"), ("Rosa", "Alcantara"),
    ("Viktor", "Sokolov"), ("Chiara", "Moretti"), ("Femi", "Adeyemi"), ("Marta", "Kowalczyk"),
    ("Dario", "Esposito"), ("Nour", "Khalil"), ("Sunil", "Prakash"), ("Elke", "Brandt"),
    ("Paolo", "Ferraro"), ("Aya", "Fujimoto"), ("Tobias", "Lindgren"), ("Carmen", "Delgado"),
]

# Alias first names for Jim's display-name divergence. Disjoint from every customer first
# name, so an alias can never be mistaken for a different real customer's given name.
ALIAS_FIRSTS = [
    "Bertie", "Cormac", "Dolores", "Emmett", "Fionn", "Greta", "Rufus", "Ingram",
    "Jules", "Winnie", "Lorne", "Mabel", "Norris", "Odile", "Perry", "Ludo",
]

# Noise surnames: disjoint from CUSTOMER_NAMES and from each other, so an unrelated
# record has no name token in common with any real case and must stay a singleton.
NOISE_NAMES = [
    ("Alex", "Ferro"), ("Sam", "Quill"), ("Noa", "Vance"), ("Kai", "Ashby"),
    ("Remy", "Bloom"), ("Toni", "Crane"), ("Lee", "Dial"), ("Max", "Ember"),
    ("Ivy", "Frost"), ("Cy", "Gale"), ("Bo", "Holt"), ("Ada", "Iver"),
    ("Wren", "Jessop"), ("Otto", "Kemp"), ("Pia", "Larkin"), ("Rex", "Mundy"),
    ("Sol", "Nash"), ("Tess", "Orme"), ("Uma", "Pike"), ("Vic", "Rowe"),
    ("Wes", "Slade"), ("Xan", "Turnbull"), ("Yara", "Upton"), ("Zeb", "Voss"),
    ("Ana", "Whitlock", ), ("Ben", "Yardley"), ("Cleo", "Zamora"), ("Drew", "Ainsley"),
    ("Esme", "Bramble"), ("Finn", "Colton"), ("Gus", "Deveraux"), ("Hedy", "Elmore"),
    ("Iris", "Fenwick"), ("Jai", "Garrick"), ("Kit", "Hollis"), ("Lux", "Ingles"),
    ("Mo", "Jarvis"), ("Nia", "Kestrel"), ("Oz", "Lomax"), ("Pax", "Merrick"),
    ("Quin", "Norbury"), ("Rain", "Ospina"), ("Skye", "Pruitt"), ("Tao", "Quimby"),
    ("Ulla", "Ridley"), ("Vito", "Stroud"), ("Wynn", "Thackery"), ("Xia", "Ulrich"),
    ("Yves", "Verity"), ("Zoe", "Wexford"), ("Abel", "Yeats"), ("Bess", "Zeller"),
    ("Cade", "Ashford"), ("Dov", "Belmont"), ("Eve", "Carrow"),
]

# --------------------------------------------------------------------------------------
# Tier D — the adversarial pool. Everything above is built so identity resolution can
# succeed; this pool is built so it can fail, in the three specific ways the main corpus
# rules out by construction.
#
#   collision_with_identity      Two DIFFERENT customers share a surname and contact
#                                support the same afternoon about the SAME issue, their
#                                records interleaved. Name, time and meaning all agree, so
#                                nothing in the unstructured text can separate them. Only
#                                the structured side can: each case carries an address and
#                                an order reference resolving to a different customer_id.
#                                This is the shape where orders stop being enrichment and
#                                start being evidence.
#   collision_identity_corrupted The same collision, except one record's address carries
#                                Jim's single-keystroke domain typo, so the email bridge
#                                misses it and that record has no identity of its own.
#                                Isolates what a corrupted identifier costs, separately
#                                from what a correct one buys.
#   collision_keyless            The same collision with NO identifier anywhere and
#                                DIFFERENT issues, so the cosine floor is the only thing
#                                left to separate two strangers who share a surname.
#   same_customer_in_window      One customer, two genuinely separate cases about
#                                different problems, opened inside the link window. Tests
#                                whether a shared email fuses two episodes that happen to
#                                be close together.
#
# Surnames and first names are disjoint from the main and noise pools at the token level,
# so tier D can only contaminate itself: the main tiers stay interpretable as a regression
# floor. That containment is a deliberate limitation, and it is stated in the README.
# --------------------------------------------------------------------------------------

# Eight surnames, two customers each: the collision pairs.
ADVERSARIAL_CUSTOMERS = [
    ("Renata", "Beltran"), ("Osvaldo", "Beltran"),
    ("Ileana", "Castellanos"), ("Bruno", "Castellanos"),
    ("Chidi", "Okonjo"), ("Ngozi", "Okonjo"),
    ("Alonso", "Vasquez"), ("Marisol", "Vasquez"),
    ("Cedric", "Hargreaves"), ("Philippa", "Hargreaves"),
    ("Rodrigo", "Pemberton"), ("Aurelie", "Pemberton"),
    ("Solveig", "Thorsdottir"), ("Magnus", "Thorsdottir"),
    ("Rafaela", "Quintero"), ("Emilio", "Quintero"),
]

# Three more with unique surnames, used for the same-customer-in-window shape. They need
# no collision: the thing under test there is the time gate, not the name gate.
ADVERSARIAL_REPEAT_CUSTOMERS = [
    ("Thibault", "Rousseau"), ("Katarina", "Milosevic"), ("Desmond", "Achterberg"),
]

# How the eight collision pairs are allocated across the three collision shapes. The rest
# after these two are keyless.
COLLISION_PAIRS_WITH_IDENTITY = 3
COLLISION_PAIRS_WITH_CORRUPTED_IDENTITY = 2

# Gaps between the two cases of a same-customer-in-window pair, in hours. Deliberately
# straddling Stage 2's episode-gap rule: the first is inside it and should fuse, the other
# two are outside it and should stay apart. Measuring both sides is the point.
SAME_CUSTOMER_WINDOW_GAPS_H = [14.0, 40.0, 70.0]

# Jim's exact domain recipe: four real providers plus one single-keystroke corruption of
# each, at roughly 9% of the pool.
GOOD_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com"]
TYPO_DOMAINS = {"gmail.com": "gmial.com", "yahoo.com": "yaho.com",
                "outlook.com": "outlok.com", "hotmail.com": "hotmial.com"}
TYPO_DOMAIN_RATE = 0.09
ALIAS_RATE = 0.22

# Jim's four phone formats, same PH mobile number underneath.
PHONE_FORMATS = ["+63{d10}", "0{d10}", "({d4}) {d3}-{d3b}", "{d10}"]

# Agents carry Jim's org attributes; ids stay mnemonic because Stage 1 has to pull them
# out of free text and A_ROSA survives that better than A047.
AGENTS = [
    {"agent_id": "A_ROSA", "name": "Rosa Delgado", "site": "Manila", "team": "Billing Support", "shift": "AM"},
    {"agent_id": "A_LIAM", "name": "Liam Doherty", "site": "Manila", "team": "General Care", "shift": "PM"},
    {"agent_id": "A_PRIYA", "name": "Priya Menon", "site": "Cebu", "team": "Technical Support", "shift": "Night"},
    {"agent_id": "A_KOJI", "name": "Koji Arai", "site": "Cebu", "team": "General Care", "shift": "Mid"},
    {"agent_id": "A_MARE", "name": "Mare Solano", "site": "Davao", "team": "Retention", "shift": "AM"},
    {"agent_id": "A_TESS", "name": "Tess Abara", "site": "Remote-PH", "team": "Billing Support", "shift": "Night"},
    {"agent_id": "A_NILS", "name": "Nils Berg", "site": "Manila", "team": "VIP Desk", "shift": "Mid"},
    {"agent_id": "A_ZARA", "name": "Zara Iqbal", "site": "Davao", "team": "Technical Support", "shift": "PM"},
    {"agent_id": "A_BENN", "name": "Benn Ocampo", "site": "Cebu", "team": "Retention", "shift": "AM"},
    {"agent_id": "A_INES", "name": "Ines Bautista", "site": "Remote-PH", "team": "General Care", "shift": "Night"},
    {"agent_id": "A_HUGO", "name": "Hugo Salcedo", "site": "Manila", "team": "Technical Support", "shift": "Mid"},
    {"agent_id": "A_MAYA", "name": "Maya Ortega", "site": "Remote-PH", "team": "VIP Desk", "shift": "PM"},
]
REVIEWERS = ["QA_NORA", "QA_ELI", "QA_JIN", "QA_MAE"]

LANGUAGES = ["English", "Tagalog", "English/Tagalog", "Cebuano"]

# Jim's recontact openers: the four most common lines in his entire chat corpus, and the
# reason 46% of his email subjects are "Following up again".
RECONTACT_OPENERS = [
    "This is the second time I'm reaching out about the same issue.",
    "I called about this already, following up again.",
    "I was told this was resolved but it clearly isn't.",
    "I chatted about this yesterday and it's still not fixed.",
]

# --------------------------------------------------------------------------------------
# Issue catalogue. Fourteen archetypes: our original six plus Francis's ten, deduplicated.
#
# Each channel text is a GENUINE rewording of the same underlying problem, not a copy:
# the chat is lowercase and fragmented, the email is formal and follows Francis's
# three-part issue / impact / ask shape, the QA note is auditor register, the CSAT
# verbatim is first-person retrospective, and `restate` is how the customer puts it when
# they come back a second time. No clause is shared verbatim between them, which is what
# forces Stage 2's embedding pass to do real work instead of matching on string overlap.
# --------------------------------------------------------------------------------------

ISSUES = {
    "order_not_received": {
        "area": "delivery",
        "subject": "Parcel marked delivered but never arrived",
        "escalation": "Customer states the consignment was recorded as delivered but was never received at the property. Carrier tracking shows a completed handover that the customer disputes. No goods are in the customer's possession and the order value remains unrecovered.",
        "escalation_action": "Open a formal carrier trace and authorise a replacement dispatch if the trace does not resolve within the service window.",
        "root_cause": "Carrier marked delivered but parcel never arrived (lost in transit).",
        "resolution": "Reshipped with express tracking; refunded shipping.",
        "chat": "hey my order still hasnt shown up, tracking says delivered but nothing here",
        "email": "I am writing because the package I was expecting was marked delivered three days ago, yet it has not arrived at my address. This matters because I paid for a shipment I have never seen. Please open a carrier trace and tell me whether it can be replaced.",
        "qa": "Non-receipt claim raised against a delivered scan. Case context: the parcel was marked delivered but never turned up at the address. Customer impact: paid for goods they have never received. Agent opened a carrier trace within policy.",
        "csat": "Waited in all week for something the courier swore had already turned up. Sorting it out took far longer than it should have.",
        "restate": "The parcel that supposedly arrived last week is still nowhere, and nobody has been back to me about the trace.",
    },
    "double_charge": {
        "area": "billing",
        "subject": "Duplicate debit on a single order",
        "escalation": "A single order produced two settled debits against the customer's card. The second debit has not been reversed and continues to hold funds. The customer has asked for written confirmation that only one payment will stand.",
        "escalation_action": "Authorise reversal of the duplicate settlement and issue written confirmation of the final amount charged.",
        "root_cause": "Payment retry fired twice after a gateway timeout.",
        "resolution": "Reversed the duplicate charge; confirmed single settlement.",
        "chat": "i got billed twice for the same thing?? theres two charges on my card",
        "email": "My statement shows two identical debits against a single purchase. This matters because it has taken my available balance below what I planned for this month. Please reverse the second one and confirm in writing that only one payment stands.",
        "qa": "Billing dispute logged over a repeated debit. Case context: the customer was charged twice for one order after a payment retry. Customer impact: two payments held against a single purchase. Agent raised a reversal and set clearing expectations.",
        "csat": "Money left my account twice for one order. It came back eventually but I had to push for it.",
        "restate": "That second debit I flagged is still sitting on my card and nobody has reversed anything.",
    },
    "login_locked": {
        "area": "account_access",
        "subject": "Account locked after verification",
        "escalation": "Customer is unable to authenticate. An automated lock was applied after repeated verification attempts and has not lifted. The account is entirely inaccessible while the lock remains in force.",
        "escalation_action": "Complete identity verification to the approved standard and release the account lock.",
        "root_cause": "Account auto-locked after failed MFA sync on a new device.",
        "resolution": "Reset MFA and unlocked the account.",
        "chat": "cant get into my account, keeps saying locked after i put the code in",
        "email": "I am unable to sign in. Each time I submit my verification code the system reports that my account has been locked. This matters because I cannot reach anything in my account while this stands. Please restore access and explain what triggered the lock.",
        "qa": "Access failure following repeated authentication attempts. Case context: the account locked itself once the customer entered their verification code. Customer impact: no access to the account at all while the lock stands. Agent completed identity checks before releasing it.",
        "csat": "Shut out of my own account for the best part of a day. Fixed in the end, but a frustrating way to spend an afternoon.",
        "restate": "I am locked out again after your reset, so whatever was done the first time did not hold.",
    },
    "mfa_device_change": {
        "area": "account_access",
        "subject": "Verification codes going to my old handset",
        "escalation": "One-time verification codes continue to be delivered to a handset the customer no longer possesses. The trusted-device record was not migrated when the device changed, leaving the customer unable to complete step-up authentication.",
        "escalation_action": "Re-run identity verification and rebind the trusted device to the customer's current handset.",
        "root_cause": "Trusted-device binding never migrated after the handset swap.",
        "resolution": "Re-ran identity verification and rebound the trusted device.",
        "chat": "changed phones and now the codes go to the old handset, i cant receive anything",
        "email": "Since replacing my handset the one-time codes continue to be delivered to the device I no longer own. This matters because I cannot complete verification on the phone I actually hold. Please run whatever identity checks you need and move the trusted device across.",
        "qa": "Verification routed to a device the customer no longer holds. Case context: after changing phones the one-time codes kept going to the old handset. Customer impact: unable to finish verification on the phone they actually own. Agent followed the approved identity flow before rebinding.",
        "csat": "Codes kept going to a phone I had already given away. Took two conversations before anyone moved them.",
        "restate": "The codes are still landing on the old handset even after you said the device had been switched over.",
    },
    "wrong_item": {
        "area": "returns",
        "subject": "Incorrect product shipped",
        "escalation": "The goods delivered do not correspond to the goods ordered. A different product was picked against this order. The customer retains items they cannot use and has not received what was paid for.",
        "escalation_action": "Authorise a replacement dispatch and issue a prepaid return label for the incorrect goods.",
        "root_cause": "Warehouse pick error: adjacent SKU shipped.",
        "resolution": "Sent correct item; provided prepaid return label.",
        "chat": "you sent me the wrong item, this isnt what i ordered at all",
        "email": "What arrived is not what I purchased. A different product entirely was packed against my order. This matters because I still need the item I actually paid for. Please dispatch the correct one and tell me how to send this back.",
        "qa": "Fulfilment mismatch confirmed against the pick list. Case context: the customer received a different product from the one they ordered. Customer impact: holding goods they cannot use while still needing the right item. Agent arranged a replacement and issued a prepaid return.",
        "csat": "Opened the box to find something I never ordered. The swap worked but it dragged on.",
        "restate": "The replacement you sent is wrong as well, so I now have two items I did not order.",
    },
    "return_policy_exception": {
        "area": "returns",
        "subject": "Partial return request for damaged units",
        "escalation": "Part of a multi-unit consignment arrived damaged while the remainder is already deployed on site. Standard returns handling would require the whole order back, removing equipment that is functioning correctly.",
        "escalation_action": "Grant a partial-replacement exception outside standard returns policy and issue a case reference to the customer.",
        "root_cause": "Multi-unit order arrived part-damaged; policy only handles whole-order returns.",
        "resolution": "Granted a partial replacement exception and issued a case number.",
        "chat": "two of the units came in damaged but the rest are already installed, i cant send it all back",
        "email": "Two units in my consignment arrived damaged while the remainder are already deployed on site. This matters because returning the full order would strip out equipment that is working. Please authorise a partial replacement rather than a whole-order return.",
        "qa": "Exception request falling outside standard returns handling. Case context: two units in the order arrived damaged while the rest are already installed. Customer impact: a full return would strip out equipment that is working. Agent escalated for a partial replacement.",
        "csat": "Only part of the shipment was damaged and it took some explaining before anyone would treat it that way.",
        "restate": "Still no exception number for the partial return, and the damaged units are sitting here.",
    },
    "refund_delay": {
        "area": "refunds",
        "subject": "Refund still outstanding past the stated window",
        "escalation": "A refund authorised for this customer has not reached their account and is now materially beyond the published turnaround. The customer is without both the goods, which were returned, and the money.",
        "escalation_action": "Escalate to finance for same-day release and confirm the settlement date directly with the customer.",
        "root_cause": "Refund stuck in manual review queue past SLA.",
        "resolution": "Escalated and released the refund same day.",
        "chat": "wheres my refund, its been like 2 weeks and nothing",
        "email": "A refund I was promised has still not reached my account well past the window you quoted. This matters because I am out of pocket for goods you already have back. Please confirm where the payment is and give me an escalation route if it has stalled.",
        "qa": "Refund breached the published turnaround. Case context: the refund the customer was promised has still not arrived well past the quoted window. Customer impact: out of pocket for goods already sent back. Agent escalated to finance for same-day release.",
        "csat": "Chased my own refund for a fortnight. Nobody volunteered an update until I asked.",
        "restate": "Two weeks on from your escalation and the refund still has not landed.",
    },
    "payment_auth_mismatch": {
        "area": "payments",
        "subject": "Card charged but order shows payment failed",
        "escalation": "The payment processor recorded a successful authorisation while the order service recorded a failure. The customer has been charged and has no order. The two systems remain in disagreement on this transaction.",
        "escalation_action": "Establish the authoritative transaction state, then either release the held funds or complete the order at the original price.",
        "root_cause": "Authorisation captured while the order service recorded a failure.",
        "resolution": "Released the stale hold and re-placed the order at the original price.",
        "chat": "card got charged but the site says payment failed, so which is it",
        "email": "My card shows a completed charge while your order page insists the payment did not go through. This matters because I have neither the order nor the money. Please establish which state is authoritative and either release the hold or complete the order.",
        "qa": "Authorisation and order state diverged on one transaction. Case context: the card was charged while the order page reported the payment as failed. Customer impact: the customer has neither the money nor the order. Agent verified authorisation status before releasing the hold.",
        "csat": "Your website said the payment failed while my bank said otherwise. Confusing and slow to untangle.",
        "restate": "The hold you said you would release is still showing against my card and the order never went through.",
    },
    "address_update_failed": {
        "area": "delivery",
        "subject": "Delivery address change not applied",
        "escalation": "A delivery address amended by the customer at checkout did not propagate to the open order, which is still routed to a superseded address. Dispatch is imminent and would deliver to a property the customer has left.",
        "escalation_action": "Place an immediate hold on dispatch and correct the delivery address on the open order before release.",
        "root_cause": "Address edit saved to the profile but not propagated to the open order.",
        "resolution": "Intercepted the shipment and corrected the delivery address before dispatch.",
        "chat": "i changed my address at checkout but the confirmation still shows the old one",
        "email": "I amended my delivery address during checkout, yet the confirmation I received still lists my previous one. This matters because the order will otherwise ship somewhere I no longer live. Please hold the dispatch and correct the address before it leaves you.",
        "qa": "Address amendment failed to reach an open order. Case context: the customer changed their delivery address at checkout but the confirmation still showed the old one. Customer impact: the parcel was about to ship to an address they have left. Agent requested a dispatch hold and corrected the record.",
        "csat": "Changed my address and the order nearly went to the old one anyway. Caught it just in time, no thanks to the confirmation email.",
        "restate": "The confirmation still shows the old address, so the correction you logged has not taken effect.",
    },
    "app_sync_fail": {
        "area": "mobile_app",
        "subject": "Application no longer synchronising",
        "escalation": "The customer's application has stopped synchronising and is presenting stale information without surfacing any error. The customer has been acting on out-of-date figures without knowing they were out of date.",
        "escalation_action": "Force a session refresh, confirm the data has reconciled, and advise the customer once current.",
        "root_cause": "Sync token expired; client failed to refresh silently.",
        "resolution": "Forced token refresh; data reconciled.",
        "chat": "the app isnt syncing, my stuff is all out of date on my phone",
        "email": "The application has stopped synchronising and what it displays no longer reflects recent activity on my account. This matters because I am making decisions from stale figures. Please force whatever refresh is needed and confirm the data has reconciled.",
        "qa": "Client synchronisation stopped without surfacing an error. Case context: the app stopped updating and kept showing the customer stale information. Customer impact: decisions being made on out-of-date figures. Agent walked the customer through reauthentication.",
        "csat": "The app quietly stopped updating for days and never said so. Took a while to work out it wasn't just me.",
        "restate": "The app has drifted out of date again, so the refresh you ran has not held.",
    },
    "app_crash_order_history": {
        "area": "mobile_app",
        "subject": "App closes when opening order history",
        "escalation": "The application terminates whenever the order-history view is opened. The fault is reproducible and began after the most recent release. The customer cannot retrieve any record of past purchases in the app.",
        "escalation_action": "Raise a defect with engineering against the order-history view and supply the customer's history by email in the interim.",
        "root_cause": "Regression in the order-history view introduced by the latest release.",
        "resolution": "Logged a defect with engineering; supplied history by email in the interim.",
        "chat": "app dies every time i open order history since the update",
        "email": "Since the most recent update the application closes itself whenever I open my order history. This matters because that screen is the only place I can check what I have purchased. Please raise this with your engineers rather than sending me through another reinstall.",
        "qa": "Reproducible crash isolated to a single screen after a release. Case context: the app closes itself every time the customer opens order history. Customer impact: no way to check past purchases in the app. Agent logged a defect rather than repeating reinstall steps.",
        "csat": "Every time I tried to look at what I'd ordered the app shut itself down. At least someone finally logged it properly.",
        "restate": "The order history screen is still killing the app, and the latest update changed nothing.",
    },
    "handoff_repetition": {
        "area": "technical_support",
        "subject": "Repeating the same history after every transfer",
        "escalation": "The customer has restated the same diagnostic history at each transfer because prior notes did not travel with the case. Effort has been duplicated repeatedly and the underlying matter has not advanced.",
        "escalation_action": "Consolidate the case history onto a single record and continue from the existing engineering notes without further transfer.",
        "root_cause": "Prior troubleshooting notes not carried across the transfer.",
        "resolution": "Consolidated the history onto one case and continued from existing logs.",
        "chat": "ive explained this three times now to three different people",
        "email": "Each transfer has required me to repeat the same diagnostic history from the beginning. This matters because the effort is entirely avoidable and nothing has moved forward. Please read the notes already on file and continue from the engineering logs that exist.",
        "qa": "Context lost across an internal transfer. Case context: the customer had to repeat the same troubleshooting history to each new agent. Customer impact: wasted effort on a case that has not moved forward. Agent consolidated the notes before continuing.",
        "csat": "Told the same story to three people in a row. Nobody had read anything before me.",
        "restate": "I have now repeated this to a fourth person, so the notes still are not travelling with the case.",
    },
    "warranty_misstatement": {
        "area": "warranty",
        "subject": "Conflicting warranty terms quoted",
        "escalation": "The customer has been given conflicting warranty terms for the same accessory across separate contacts. The recorded coverage period on file is inconsistent with guidance given verbally, creating a repair-or-replace decision the customer cannot make.",
        "escalation_action": "Verify the correct warranty term against policy, correct the customer record, and confirm the position in writing.",
        "root_cause": "Conflicting coverage guidance given on the accessory warranty period.",
        "resolution": "Verified the correct term and corrected the case note.",
        "chat": "one of your people said 12 months and another said 24, which is right",
        "email": "I have been given two different answers about how long my accessory is covered for. This matters because I am deciding whether to repair or replace on the strength of that answer. Please confirm the correct term and correct whatever is recorded on my file.",
        "qa": "Contradictory coverage guidance issued across two contacts. Case context: the customer was quoted two different warranty lengths for the same accessory. Customer impact: cannot decide whether to repair or replace. Agent verified the correct term and amended the file.",
        "csat": "Got two different warranty answers from two different people. Someone eventually checked properly.",
        "restate": "I have had a third different warranty length quoted, so the file still has not been corrected.",
    },
    "cancellation_not_confirmed": {
        "area": "subscription",
        "subject": "No confirmation received for my cancellation",
        "escalation": "A subscription cancellation was processed but no confirmation was ever issued to the customer. Without written confirmation the customer has no assurance that the next billing cycle will not proceed.",
        "escalation_action": "Confirm the cancellation status on the account and reissue written confirmation before the next renewal date.",
        "root_cause": "Cancellation processed but the confirmation email never generated.",
        "resolution": "Confirmed the cancellation status and resent written confirmation.",
        "chat": "i cancelled but never got anything confirming it, is it actually cancelled",
        "email": "I cancelled my subscription but no confirmation has ever reached me. This matters because without it I have no way of knowing whether I will be billed again next cycle. Please confirm the current status and send written confirmation.",
        "qa": "Cancellation completed without customer-facing confirmation. Case context: the subscription was cancelled but no confirmation ever reached the customer. Customer impact: expecting to be billed again next cycle. Agent verified status and reissued confirmation.",
        "csat": "Cancelled and then heard nothing at all, so I spent a fortnight assuming I'd be charged again.",
        "restate": "Still nothing in writing about the cancellation, and the renewal date is coming up.",
    },
}

ISSUE_KEYS = list(ISSUES.keys())

_counter = {"chat": 0, "email": 0, "qa": 0, "csat": 0, "esc": 0}


def rid(kind):
    _counter[kind] += 1
    return f"{kind}_{_counter[kind]:04d}"


def _name_tokens(text):
    """The tokens Stage 2's name gate sees: lowercase runs of three or more letters."""
    return set(re.findall(r"[a-z]{3,}", str(text or "").lower()))


# --------------------------------------------------------------------------------------
# PDF escalation forms — the fifth modality.
#
# The other four channels are text or JSON that dbt can seed directly. A real support
# estate also contains documents: forms, letters, scanned attachments. These are written
# as actual PDFs, uploaded to a Snowflake stage, and read back with Cortex PARSE_DOCUMENT,
# so the pipeline genuinely spans a binary format rather than claiming to.
#
# Written by hand rather than with a PDF library: text-only single-page documents are a
# small, well-specified subset of the format, and the alternative is a heavyweight
# dependency for something the generator uses in one place. Output is byte-deterministic,
# which the reproducibility check in CI depends on.
# --------------------------------------------------------------------------------------

# The base-14 Helvetica font used below is Latin-1. Map the typographic characters that
# realistic prose picks up to their ASCII equivalents, then encode strictly, so anything
# genuinely unrepresentable fails loudly instead of silently corrupting the document.
_PDF_TRANSLITERATE = str.maketrans({
    "\u2014": "-", "\u2013": "-", "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u00a0": " ",
})


def _pdf_escape(text):
    text = text.translate(_PDF_TRANSLITERATE)
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def write_pdf(path, lines):
    """Write a single-page, text-only PDF. `lines` are laid out top-down."""
    content = "BT /F1 11 Tf 54 760 Td 15 TL\n"
    for line in lines:
        content += f"({_pdf_escape(line)}) Tj T*\n"
    content += "ET"

    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
    ]

    out = "%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n"
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"

    with open(path, "wb") as fh:
        fh.write(out.encode("latin-1"))  # strict: unrepresentable text must not slip through


def escalation_form_lines(ref, occurred, name, issue, agent, order_ref, ticket):
    """An internal escalation form: field-and-value register, unlike any other channel.

    `Date raised` is parsed deterministically downstream, so a case's document lands in
    the same time window as its other records without depending on the LLM for a date.
    """
    lines = [
        "CUSTOMER ESCALATION FORM",
        "Support Operations - internal use only",
        "",
        f"Reference: {ref}",
        f"Date raised: {occurred}",
        f"Raised by: {agent['agent_id']} ({agent['team']}, {agent['site']})",
        "",
        f"Customer name: {name}",
        f"Product area: {issue['area']}",
    ]
    if order_ref:
        lines.append(f"Order reference: {order_ref}")
    if ticket:
        lines.append(f"Related ticket: {ticket}")
    lines += [
        "",
        "Summary of complaint",
        "--------------------",
    ]
    # Wrap the prose so the page reads like a form rather than one long line.
    words, line = issue["escalation"].split(), ""
    for word in words:
        if len(line) + len(word) + 1 > 78:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    lines += [
        "",
        "Requested action",
        "----------------",
        issue["escalation_action"],
        "",
        "Authorised by: Support Operations Lead",
    ]
    return lines


def ts(offset_hours):
    return BASE_DATE + timedelta(hours=offset_hours)


def isofmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------------------

def make_phone():
    """Jim's four formats over the same PH mobile number space."""
    d10 = "9" + "".join(str(RNG.randint(0, 9)) for _ in range(9))
    fmt = RNG.choice(PHONE_FORMATS)
    return (fmt.replace("{d10}", d10)
               .replace("{d4}", "0" + d10[:3])
               .replace("{d3b}", d10[6:9])
               .replace("{d3}", d10[3:6]))


def corrupt_domain(email):
    """Swap a good domain for its single-keystroke corruption, or back the other way.

    Used only where a plan entry asks for it, to make an address in a record disagree
    with the address on the order -- the thing a typo domain actually does in the wild,
    and the thing the main corpus never does because it writes the same address to both.
    """
    local, _, domain = email.partition("@")
    inverse = {typo: good for good, typo in TYPO_DOMAINS.items()}
    return f"{local}@{TYPO_DOMAINS.get(domain) or inverse.get(domain, domain)}"


def build_customers():
    """48 customers with unique first names and unique surnames, wearing Jim's noise."""
    customers = []
    aliases = ALIAS_FIRSTS[:]
    RNG.shuffle(aliases)
    for i, (first, last) in enumerate(CUSTOMER_NAMES, 1):
        domain = RNG.choice(GOOD_DOMAINS)
        if RNG.random() < TYPO_DOMAIN_RATE:
            domain = TYPO_DOMAINS[domain]

        # Jim's display-name divergence: the address is built from a name the account
        # holder actually goes by, which is NOT their legal first name. The surname always
        # survives in the local part, so a surname-anchored bridge still resolves it while
        # a first-name match would not.
        alias = None
        if RNG.random() < ALIAS_RATE and aliases:
            alias = aliases.pop()
        email_first = (alias or first).lower()

        customers.append({
            "customer_id": f"CUST_{i:03d}",
            "first": first,
            "last": last,
            "alias": alias,
            "email": f"{email_first}.{last.lower()}{RNG.randint(10, 999)}@{domain}",
            "phone": make_phone(),
            "vip": RNG.random() < 0.08,
            "language": RNG.choice(LANGUAGES),
            "pool": "main",
        })
    return customers


def build_adversarial_customers(start_index):
    """The tier D pool. Surnames collide by design; see ADVERSARIAL_CUSTOMERS.

    Domains are always clean here. These customers carry their identity noise as the
    collision itself, plus -- where a plan entry asks for it -- a corrupted address on
    one record rather than on the account, which is what makes an email bridge miss.
    """
    customers = []
    pool = ADVERSARIAL_CUSTOMERS + ADVERSARIAL_REPEAT_CUSTOMERS
    for i, (first, last) in enumerate(pool, start_index + 1):
        customers.append({
            "customer_id": f"CUST_{i:03d}",
            "first": first,
            "last": last,
            "alias": None,
            "email": f"{first.lower()}.{last.lower()}{RNG.randint(10, 999)}@{RNG.choice(GOOD_DOMAINS)}",
            "phone": make_phone(),
            "vip": False,
            "language": RNG.choice(LANGUAGES),
            "pool": "adversarial",
        })
    return customers


def name_variants(c):
    """How this customer's name shows up in raw text. Always keeps the FULL surname."""
    variants = [
        f"{c['first']} {c['last']}",
        f"{c['first'][0]}. {c['last']}",
        f"{c['last']}, {c['first']}",
    ]
    if c["alias"]:
        # The name they actually give support, which disagrees with the account record.
        variants += [f"{c['alias']} {c['last']}", f"{c['alias']} {c['last']}"]
    return variants


# --------------------------------------------------------------------------------------
# Case plan
# --------------------------------------------------------------------------------------

def build_case_plan(customers):
    """
    Lay out TARGET_CASES cases across the customer pool and across time.

    Two hard constraints, both there to protect Stage 2's precision:
      - a customer's cases are at least MIN_SAME_CUSTOMER_GAP_H apart, so the
        deterministic email/customer pass cannot fuse two of their separate cases;
      - a customer never gets the same issue twice, so even if the time gate were
        widened the semantic pass would still have distinct meaning to work with.
    """
    plan = []
    per_customer_slots = {c["customer_id"]: [] for c in customers}
    per_customer_issues = {c["customer_id"]: set() for c in customers}

    # Cases are spread over roughly ten weeks of business time.
    span_hours = 24 * 70
    cursor = 0.0
    step = span_hours / TARGET_CASES

    order_of_customers = []
    while len(order_of_customers) < TARGET_CASES:
        pool = customers[:]
        RNG.shuffle(pool)
        order_of_customers.extend(pool)
    order_of_customers = order_of_customers[:TARGET_CASES]

    for case_idx, cust in enumerate(order_of_customers, 1):
        cursor += step
        start = cursor + RNG.uniform(-step * 0.3, step * 0.3)

        # Push the case out until it clears this customer's previous cases.
        slots = per_customer_slots[cust["customer_id"]]
        while any(abs(start - s) < MIN_SAME_CUSTOMER_GAP_H for s in slots):
            start += MIN_SAME_CUSTOMER_GAP_H
        slots.append(start)

        used = per_customer_issues[cust["customer_id"]]
        available = [k for k in ISSUE_KEYS if k not in used] or ISSUE_KEYS[:]
        issue_key = RNG.choice(available)
        used.add(issue_key)

        # Tier mix: B is the hero and gets the largest share; C stays deliberately small.
        roll = RNG.random()
        tier = "A" if roll < 0.34 else ("B" if roll < 0.80 else ("C" if roll < 0.90 else "B"))

        n_records = RNG.choices([2, 3, 4], weights=[0.42, 0.40, 0.18])[0]
        channels = RNG.sample(["chat", "email", "qa", "csat"], n_records)

        resolved = RNG.random() < 0.72
        has_order = RNG.random() < 0.78
        # Order values: long tail, most small, a few large enough to dominate revenue at risk.
        order_value = round(RNG.choice([
            RNG.uniform(12, 90), RNG.uniform(60, 220), RNG.uniform(180, 520), RNG.uniform(400, 900),
        ]), 2) if has_order else None

        plan.append({
            "case_id": f"CASE_{case_idx:03d}",
            "customer": cust,
            "issue_key": issue_key,
            "tier": tier,
            "channels": channels,
            "resolved": resolved,
            "has_order": has_order,
            "order_value": order_value,
            "start_h": start,
        })
    return plan


def build_adversarial_plan(adversarial, main_plan):
    """Lay out tier D.

    Each shape breaks exactly one main-corpus invariant, so a failure in the scored
    results traces back to a named cause instead of to "the adversarial tier" as a whole.
    Cases are placed inside the main corpus's own time span, so they are interleaved with
    ordinary traffic rather than sitting in a quiet block of their own.
    """
    span = max(c["start_h"] for c in main_plan)
    collision = adversarial[:len(ADVERSARIAL_CUSTOMERS)]
    repeats = adversarial[len(ADVERSARIAL_CUSTOMERS):]
    pairs = len(collision) // 2
    plan = []

    def add(cust, issue_key, start_h, shape, expose_email, expose_order, has_order,
            corrupt_email=False):
        plan.append({
            "case_id": f"CASE_D{len(plan) + 1:03d}",
            "customer": cust,
            "issue_key": issue_key,
            "tier": "D",
            "shape": shape,
            "channels": RNG.sample(["chat", "email", "qa", "csat"],
                                   RNG.choices([2, 3], weights=[0.55, 0.45])[0]),
            "resolved": RNG.random() < 0.72,
            "has_order": has_order,
            "order_value": round(RNG.uniform(60, 520), 2) if has_order else None,
            "start_h": start_h,
            "expose_email": expose_email,
            "expose_order": expose_order,
            "corrupt_email": corrupt_email,
        })

    for p in range(pairs):
        left, right = collision[2 * p], collision[2 * p + 1]
        base = span * (p + 1) / (pairs + 2)
        # Small enough that the two cases INTERLEAVE. A gap of a day or two would leave a
        # silence between them and the episode bound would separate the pair for free,
        # which would make the shape look hard while testing nothing. Two people with the
        # same surname contacting support the same afternoon is both realistic and the
        # only version of this that the resolver cannot get for free.
        gap = RNG.uniform(2.0, 10.0)
        identity_pairs = COLLISION_PAIRS_WITH_IDENTITY + COLLISION_PAIRS_WITH_CORRUPTED_IDENTITY
        if p < identity_pairs:
            # Same surname, same afternoon, SAME issue, records interleaved. Name, time
            # and meaning all agree, so nothing in the unstructured text tells these two
            # people apart. What does is the structured side: each case resolves to a
            # different customer_id.
            #
            # The corrupted variant is its own shape rather than a coin flip inside this
            # one, because it tests the opposite thing: what a BROKEN identifier costs.
            # Its first record carries a typo domain, so the email bridge misses it and
            # that record arrives with no identity of its own, in a window where the only
            # other candidate is a different person with the same surname and the same
            # complaint. It is not given an order reference either, or the order would
            # simply stand in for the address and the shape would test nothing.
            issue_key = ISSUE_KEYS[p % len(ISSUE_KEYS)]
            corrupt = p >= COLLISION_PAIRS_WITH_IDENTITY
            shape = "collision_identity_corrupted" if corrupt else "collision_with_identity"
            add(left, issue_key, base, shape,
                expose_email=True, expose_order=not corrupt, has_order=True,
                corrupt_email=corrupt)
            add(right, issue_key, base + gap, shape,
                expose_email=True, expose_order=True, has_order=True)
        else:
            # No identifier anywhere, and different problems. Everything the resolver has
            # is a shared surname inside the window, which leaves the cosine floor on its
            # own -- and the measured distributions say it cannot do this alone.
            add(left, ISSUE_KEYS[p % len(ISSUE_KEYS)], base, "collision_keyless",
                expose_email=False, expose_order=False, has_order=False)
            add(right, ISSUE_KEYS[(p + 5) % len(ISSUE_KEYS)], base + gap, "collision_keyless",
                expose_email=False, expose_order=False, has_order=False)

    for k, cust in enumerate(repeats):
        # One customer, two unrelated problems, opened close together. A shared email is
        # exposed on both, so the deterministic pass will bridge them unless something
        # bounds the episode. The gaps straddle that bound deliberately.
        base = span * (k + 1) / (len(repeats) + 2)
        add(cust, ISSUE_KEYS[k], base, "same_customer_in_window",
            expose_email=True, expose_order=True, has_order=True)
        add(cust, ISSUE_KEYS[(k + 7) % len(ISSUE_KEYS)], base + SAME_CUSTOMER_WINDOW_GAPS_H[k],
            "same_customer_in_window", expose_email=True, expose_order=True, has_order=True)

    return plan


# --------------------------------------------------------------------------------------
# Record emitters
# --------------------------------------------------------------------------------------

def csat_score_for(resolved):
    """Bimodal like Jim's real distribution (peaks at 1-2 and 4-5), coherent with outcome."""
    if resolved:
        return RNG.choices([5, 4, 3], weights=[0.5, 0.35, 0.15])[0]
    return RNG.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]


def qa_score_for(csat_like, resolved):
    """
    QA score on Jim's 0-100 scale, deliberately correlated with the customer's own
    verdict (he ran r = 0.62) rather than drawn independently.
    """
    base = 58 + (csat_like - 1) * 9 + (6 if resolved else 0)
    return max(50, min(100, int(base + RNG.uniform(-6, 6))))


def emit_case(case, records, documents, orders, csat_scores, agent_load, seq):
    """Write every raw record for one planned case and return their record ids.

    Shared by the main corpus and the adversarial tier so the two are generated by
    identical code: a tier D case differs only in what its plan entry asks for, never in
    how it is written. `seq` carries the order and survey counters across cases.
    """
    cust = case["customer"]
    issue = ISSUES[case["issue_key"]]
    agent = RNG.choice(AGENTS)
    tier = case["tier"]
    order_ref = None

    if case["has_order"]:
        seq["order"] += 1
        order_ref = f"ORD_{seq['order']}"
        placed = ts(case["start_h"] - RNG.uniform(48, 240))
        if case["issue_key"] == "order_not_received":
            status = "lost"
        elif case["issue_key"] in ("wrong_item", "return_policy_exception"):
            status = "returned"
        elif case["issue_key"] == "payment_auth_mismatch":
            status = "payment_failed"
        else:
            status = "completed"
        orders.append({
            "order_id": order_ref,
            "customer_id": cust["customer_id"],
            # Orders carry the LEGAL name. Records may carry the alias. The surname
            # is what bridges them, which is exactly the harder path we want tested.
            "customer_name": f"{cust['first']} {cust['last']}",
            "email": cust["email"],
            "value": case["order_value"],
            "placed_ts": isofmt(placed),
            "status": status,
        })

    # Tier controls which identifiers are exposed in the raw text:
    #   A: email and/or order_ref present and shared across the case's records.
    #   B: neither; only a name variant + the same issue in different words + proximity.
    #   C: a shared ticket id token.
    #   D: set explicitly on the plan entry, because the whole point of the tier is to
    #      choose which evidence is present.
    ticket = f"TK{RNG.randint(10000, 99999)}" if tier == "C" else None
    expose_email = case.get("expose_email", tier == "A")
    expose_order = case.get("expose_order", tier == "A") and case["has_order"]

    # Jim's typo domains only bite when the address in the record disagrees with the
    # address on the order, which the main corpus never does. Where a plan entry asks
    # for it, the first record carries a single-keystroke corruption of the real domain,
    # so the email bridge misses that record and the case has to hold together some
    # other way while still resolving to the right customer overall.
    corrupt_first_email = case.get("corrupt_email", False)

    case_record_ids = []
    case_csat_value = None

    for ci, ch in enumerate(case["channels"]):
        record_email = (corrupt_domain(cust["email"])
                        if (corrupt_first_email and ci == 0) else cust["email"])
        # Tight per-case clustering: hours apart, never the multi-week channel
        # stratification Francis's data has.
        occurred = ts(case["start_h"] + ci * RNG.uniform(1.5, 6.0))
        name = RNG.choice(name_variants(cust))

        # Recontact: from the second record onward the customer often restates the
        # problem in fresh words behind one of Jim's recontact openers. It is the
        # dominant volume driver in his corpus, and it keeps the case linkable
        # because the restatement still carries the issue.
        recontact = ci > 0 and RNG.random() < 0.45
        opener = RNG.choice(RECONTACT_OPENERS) if recontact else None

        if ch == "chat":
            r = rid("chat")
            lines = [opener.lower(), issue["restate"].lower()] if recontact else [issue["chat"]]
            transcript = [{"role": "customer", "text": lines[0]}]
            transcript.append({"role": "agent",
                               "text": "Thanks for reaching out, let me take a look into this for you."})
            if len(lines) > 1:
                transcript.append({"role": "customer", "text": lines[1]})
                transcript.append({"role": "agent",
                                   "text": "I can see the history on the account, let me pick this up from there."})
            blob = {"session_id": r, "channel": "chat", "started_at": isofmt(occurred),
                    "agent_id": agent["agent_id"], "customer_name": name, "transcript": transcript}
            if expose_email:
                blob["customer_email"] = record_email
            if expose_order:
                blob["order_ref"] = order_ref
            if ticket:
                blob["ticket"] = ticket
            records["chat"].append({"record_id": r, "received_ts": isofmt(occurred),
                                    "raw_content": json.dumps(blob)})
            case_record_ids.append(r)

        elif ch == "email":
            r = rid("email")
            # Tier A shows the real address. For B and C the header still needs *an*
            # address, so it gets a throwaway one that is unique per record: a stable
            # personal address would itself be the shared entity those tiers must not
            # have. (It also avoids malformed locals from "Surname, First" variants.)
            from_email = (record_email if expose_email
                          else f"{re.sub(r'[^a-z]', '', cust['last'].lower())}.{r[-4:]}@mailbox.example.com")
            subject = "Following up again" if recontact else issue["subject"]
            if ticket:
                subject = f"Re: {ticket} {subject}"
            body = f"{opener} {issue['restate']}" if recontact else issue["email"]
            if expose_order:
                body += f"\n\nOrder reference: {order_ref}"
            lines = [f"From: {name} <{from_email}>",
                     "To: support@company.example.com",
                     f"Subject: {subject}",
                     f"Date: {isofmt(occurred)}",
                     "", body]
            records["email"].append({"record_id": r, "received_ts": isofmt(occurred),
                                     "raw_content": "\n".join(lines)})
            case_record_ids.append(r)

        elif ch == "qa":
            r = rid("qa")
            provisional = case_csat_value if case_csat_value else (4 if case["resolved"] else 2)
            score = qa_score_for(provisional, case["resolved"])
            reviewer = RNG.choice(REVIEWERS)
            note = (f"QA review {reviewer} — agent {agent['agent_id']} ({agent['team']}, {agent['site']}). "
                    f"Customer {name}. Product area: {issue['area']}. Score {score}/100. {issue['qa']}")
            if recontact:
                note += " Repeat contact on an existing issue; prior notes were not carried across."
            if expose_email:
                note += f" Email {record_email}."
            if expose_order:
                note += f" Ref {order_ref}."
            if ticket:
                note += f" Ticket {ticket}."
            note += (" Required action: coach on expectation setting and confirm resolution with the customer."
                     if score < 75 else " Required action: none, handling met standard.")
            records["qa"].append({"record_id": r, "received_ts": isofmt(occurred),
                                  "raw_content": note})
            case_record_ids.append(r)

        elif ch == "csat":
            r = rid("csat")
            seq["survey"] += 1
            score = csat_score_for(case["resolved"])
            case_csat_value = score
            comment = issue["csat"]
            if recontact:
                comment = f"{issue['csat']} Having to come back a second time made it worse."
            blob = {"survey_id": f"SV_{seq['survey']}", "score": score, "comment": comment,
                    "submitted_at": isofmt(occurred + timedelta(hours=1)), "customer_name": name}
            if expose_order:
                blob["order_ref"] = order_ref
            records["csat"].append({"record_id": r, "received_ts": isofmt(occurred),
                                    "raw_content": json.dumps(blob)})
            case_record_ids.append(r)
            csat_scores.append({
                "survey_id": f"SV_{seq['survey']}",
                "order_ref": order_ref or "",
                "customer_id": cust["customer_id"],
                "score": score,
                "submitted_ts": isofmt(occurred + timedelta(hours=1)),
            })

        d = occurred.date().isoformat()
        agent_load[(agent["agent_id"], d)] = agent_load.get((agent["agent_id"], d), 0) + 1

    # A PDF escalation form for a share of cases. It is a full member of the case:
    # it must be linked like any other record, and it is scored the same way.
    if RNG.random() < (DOCUMENT_RATE * (1.6 if tier == "B" else 0.6)):
        r = rid("esc")
        occurred = ts(case["start_h"] + RNG.uniform(2.0, 8.0))
        name = RNG.choice(name_variants(cust))
        documents.append({
            "record_id": r,
            "filename": f"{r}.pdf",
            "received_ts": isofmt(occurred),
            "lines": escalation_form_lines(
                r.upper().replace("ESC_", "ESC-"), isofmt(occurred), name, issue, agent,
                order_ref if expose_order else None, ticket,
            ),
        })
        case_record_ids.append(r)
        agent_load[(agent["agent_id"], occurred.date().isoformat())] = (
            agent_load.get((agent["agent_id"], occurred.date().isoformat()), 0) + 1
        )

    return case_record_ids


def ground_truth_entry(case, record_ids):
    issue = ISSUES[case["issue_key"]]
    return {
        "case_id": case["case_id"], "tier": case["tier"],
        # Tier D's three shapes fail for different reasons, so they are reported
        # separately rather than averaged into one adversarial number.
        "shape": case.get("shape", "standard"),
        "customer_id": case["customer"]["customer_id"],
        "issue": case["issue_key"], "root_cause": issue["root_cause"],
        "resolution": issue["resolution"], "resolved": case["resolved"],
        "record_ids": record_ids,
        "revenue_at_risk": case["order_value"] if (case["has_order"] and not case["resolved"]) else 0.0,
    }


def build():
    customers = build_customers()
    plan = build_case_plan(customers)

    records = {"chat": [], "email": [], "qa": [], "csat": []}
    documents = []
    orders, csat_scores = [], []
    agent_load = {}
    gt_cases, noise_ids = [], []
    seq = {"order": 1000, "survey": 5000}

    for case in plan:
        case_record_ids = emit_case(case, records, documents, orders, csat_scores, agent_load, seq)
        gt_cases.append(ground_truth_entry(case, case_record_ids))

    # ----------------------------------------------------------------------------------
    # Noise: unrelated single records that must NOT merge into any case. Each carries a
    # surname shared with nobody, sits in its own time window, and deliberately reuses the
    # issue catalogue so it is semantically close to real cases. The name anchor is the
    # only thing keeping it out, which is precisely the property worth testing.
    # ----------------------------------------------------------------------------------
    noise_start = max(c["start_h"] for c in plan) + 48
    for k in range(NOISE_RECORDS):
        issue = ISSUES[ISSUE_KEYS[k % len(ISSUE_KEYS)]]
        ch = ["chat", "email", "qa", "csat"][k % 4]
        occurred = ts(noise_start + k * RNG.uniform(6, 20))
        first, last = NOISE_NAMES[k]
        name = f"{first} {last}"
        agent = RNG.choice(AGENTS)

        if ch == "chat":
            r = rid("chat")
            records["chat"].append({"record_id": r, "received_ts": isofmt(occurred),
                                    "raw_content": json.dumps({
                                        "session_id": r, "channel": "chat", "started_at": isofmt(occurred),
                                        "agent_id": agent["agent_id"], "customer_name": name,
                                        "transcript": [{"role": "customer", "text": issue["chat"]}]})})
        elif ch == "email":
            r = rid("email")
            records["email"].append({"record_id": r, "received_ts": isofmt(occurred),
                                     "raw_content": (f"From: {name} <{first.lower()}.{last.lower()}"
                                                     f"{RNG.randint(10, 999)}@{RNG.choice(GOOD_DOMAINS)}>\n"
                                                     f"To: support@company.example.com\nSubject: help needed\n"
                                                     f"Date: {isofmt(occurred)}\n\n{issue['email']}")})
        elif ch == "qa":
            r = rid("qa")
            records["qa"].append({"record_id": r, "received_ts": isofmt(occurred),
                                  "raw_content": (f"QA review {RNG.choice(REVIEWERS)} — agent {agent['agent_id']}. "
                                                  f"Customer {name}. Product area: {issue['area']}. "
                                                  f"Score {RNG.randint(60, 98)}/100. {issue['qa']}")})
        else:
            r = rid("csat")
            records["csat"].append({"record_id": r, "received_ts": isofmt(occurred),
                                    "raw_content": json.dumps({
                                        "survey_id": f"SV_noise_{r}", "score": RNG.randint(1, 5),
                                        "comment": issue["csat"], "submitted_at": isofmt(occurred),
                                        "customer_name": name})})
        noise_ids.append(r)
        agent_load[(agent["agent_id"], occurred.date().isoformat())] = \
            agent_load.get((agent["agent_id"], occurred.date().isoformat()), 0) + 1

    # ----------------------------------------------------------------------------------
    # Tier D: the adversarial corpus, generated last on purpose. Every record id above is
    # unchanged by it, so regenerating shows tier D as additions rather than rewriting the
    # tiers whose 100% result is the regression floor.
    # ----------------------------------------------------------------------------------
    adversarial = build_adversarial_customers(len(customers))
    adversarial_plan = build_adversarial_plan(adversarial, plan)
    for case in adversarial_plan:
        gt_cases.append(ground_truth_entry(
            case, emit_case(case, records, documents, orders, csat_scores, agent_load, seq)))
    customers = customers + adversarial
    plan = plan + adversarial_plan

    # ----------------------------------------------------------------------------------
    # agent_daily_metrics on Jim's measured operational ranges (aht 180-720s, fcr
    # 0.55-0.92, occupancy 0.60-0.95, csat 3.2-4.8), with values that still move with the
    # day's load rather than being drawn independently the way his are.
    # ----------------------------------------------------------------------------------
    agent_metrics = []
    for (agent_id, d), n in sorted(agent_load.items()):
        pressure = min(1.0, n / 6.0)
        agent_metrics.append({
            "agent_id": agent_id,
            "metric_date": d,
            "aht": round(180 + pressure * 420 + RNG.uniform(-40, 90), 1),
            "fcr": round(max(0.55, min(0.92, 0.90 - pressure * 0.28 + RNG.uniform(-0.04, 0.04))), 3),
            "occupancy": round(max(0.60, min(0.95, 0.63 + pressure * 0.27 + RNG.uniform(-0.03, 0.03))), 3),
            "avg_csat": round(max(3.2, min(4.8, 4.6 - pressure * 1.1 + RNG.uniform(-0.15, 0.15))), 2),
        })

    return (records, documents, orders, csat_scores, agent_metrics, gt_cases,
            noise_ids, customers, plan)


# --------------------------------------------------------------------------------------
# Invariants. These are the properties Stage 2's measured precision depends on, so they
# are checked here rather than discovered later in a failing dbt test.
# --------------------------------------------------------------------------------------

class InvariantError(ValueError):
    """A generated corpus violated a property Stage 2's measured accuracy depends on."""


def _require(condition, message):
    """Raise rather than assert: these guards must hold even under `python -O`, where
    assert statements are stripped out entirely."""
    if not condition:
        raise InvariantError(message)


def _validate_adversarial(main, adversarial, plan):
    """Tier D violates the main invariants on purpose, so what has to be checked is that
    it violates exactly the ones that were planted and nothing else. An accidental
    collision with the main pool would quietly corrupt the regression floor."""
    if not adversarial:
        return

    main_tokens = set()
    for c in main:
        main_tokens |= _name_tokens(c["first"]) | _name_tokens(c["last"])
        if c["alias"]:
            main_tokens |= _name_tokens(c["alias"])
    for c in adversarial:
        overlap = (_name_tokens(c["first"]) | _name_tokens(c["last"])) & main_tokens
        _require(not overlap, f"adversarial customer {c['customer_id']} collides with the main pool: {sorted(overlap)}")

    # The collisions themselves: each surname in the collision pool is shared by exactly
    # two customers, and those two are different people.
    collision_ids = {c["customer_id"] for c in adversarial[:len(ADVERSARIAL_CUSTOMERS)]}
    by_surname = {}
    for c in adversarial:
        if c["customer_id"] in collision_ids:
            by_surname.setdefault(c["last"], []).append(c)
    for last, group in by_surname.items():
        _require(len(group) == 2, f"collision surname {last} is shared by {len(group)} customers, expected 2")
        _require(group[0]["first"] != group[1]["first"], f"collision pair {last} has one first name")

    d_cases = [c for c in plan if c["tier"] == "D"]
    _require(d_cases, "tier D is empty")
    shapes = {}
    for c in d_cases:
        shapes.setdefault(c["shape"], []).append(c)
    for shape in ("collision_with_identity", "collision_identity_corrupted",
                  "collision_keyless", "same_customer_in_window"):
        _require(shapes.get(shape), f"tier D shape {shape} was not planted")

    # Colliding pairs must actually be confusable: same surname, inside the link window.
    for shape in ("collision_with_identity", "collision_identity_corrupted", "collision_keyless"):
        by_pair = {}
        for c in shapes[shape]:
            by_pair.setdefault(c["customer"]["last"], []).append(c)
        for last, group in by_pair.items():
            _require(len(group) == 2, f"{shape} pair {last} has {len(group)} cases, expected 2")
            a, b = sorted(group, key=lambda c: c["start_h"])
            _require(a["customer"]["customer_id"] != b["customer"]["customer_id"],
                     f"{shape} pair {last} is one customer, so it is not a collision")
            _require(b["start_h"] - a["start_h"] < LINK_WINDOW_HOURS,
                     f"{shape} pair {last} is {b['start_h'] - a['start_h']:.1f}h apart, outside the link window")
            if shape != "collision_keyless":
                _require(a["issue_key"] == b["issue_key"],
                         f"{shape} pair {last} has different issues, so meaning could separate them")
                _require(a["expose_email"] and b["expose_email"],
                         f"{shape} pair {last} exposes no identity, so nothing can separate them")
                corrupted = [c for c in group if c["corrupt_email"]]
                if shape == "collision_identity_corrupted":
                    _require(len(corrupted) == 1,
                             f"{shape} pair {last} has {len(corrupted)} corrupted cases, expected 1")
                    _require(not corrupted[0]["expose_order"],
                             f"{shape} pair {last} leaves an order reference standing in for the "
                             "broken address, so it tests nothing")
                else:
                    _require(not corrupted, f"{shape} pair {last} carries a corrupted address")
            else:
                _require(a["issue_key"] != b["issue_key"],
                         f"{shape} pair {last} has one issue, which makes it unresolvable rather than hard")
                _require(not (a["expose_email"] or b["expose_email"] or a["expose_order"] or b["expose_order"]),
                         f"{shape} pair {last} exposes an identifier and is therefore not keyless")

    # Repeat episodes: one customer, two problems, inside the window.
    by_customer = {}
    for c in shapes["same_customer_in_window"]:
        by_customer.setdefault(c["customer"]["customer_id"], []).append(c)
    for cid, group in by_customer.items():
        _require(len(group) == 2, f"same_customer_in_window {cid} has {len(group)} cases, expected 2")
        a, b = sorted(group, key=lambda c: c["start_h"])
        _require(a["issue_key"] != b["issue_key"], f"{cid}'s two episodes are the same problem")
        _require(b["start_h"] - a["start_h"] < LINK_WINDOW_HOURS,
                 f"{cid}'s episodes are outside the link window, so the shape tests nothing")


def validate(customers, plan, gt_cases, noise_ids, records, documents=()):
    main = [c for c in customers if c.get("pool", "main") == "main"]
    adversarial = [c for c in customers if c.get("pool") == "adversarial"]

    firsts = [c["first"] for c in main]
    lasts = [c["last"] for c in main]
    _require(len(set(firsts)) == len(firsts), "main-pool first names must be unique")
    _require(len(set(lasts)) == len(lasts), "main-pool surnames must be unique")

    noise_lasts = [n[1] for n in NOISE_NAMES[:NOISE_RECORDS]]
    _require(len(set(noise_lasts)) == len(noise_lasts), "noise surnames must be unique")
    _require(not (set(noise_lasts) & set(lasts)), "noise surnames must not collide with customers")

    alias_firsts = {c["alias"] for c in customers if c["alias"]}
    _require(not (alias_firsts & set(firsts)), "aliases must not collide with real first names")

    # Stage 2's semantic pass gates on shared name tokens of 3+ characters, so token
    # overlap between pools is what would let a noise record drift into a real case, or
    # two unrelated noise records merge with each other. Check at the token level, not
    # just the surname level: an alias colliding with somebody's noise surname is enough.
    toks = _name_tokens

    customer_tokens = set()
    for c in customers:
        customer_tokens |= toks(c["first"]) | toks(c["last"])
        if c["alias"]:
            customer_tokens |= toks(c["alias"])
    noise_tokens, seen_noise = set(), {}
    for first, last in NOISE_NAMES[:NOISE_RECORDS]:
        these = toks(first) | toks(last)
        for t in these:
            _require(t not in seen_noise, f"noise name token '{t}' reused by two noise records")
            seen_noise[t] = True
        noise_tokens |= these
    _require(
        not (noise_tokens & customer_tokens),
        f"noise names share tokens with customers: {sorted(noise_tokens & customer_tokens)}",
    )

    # A MAIN-pool customer's separate cases must clear Stage 2's link window by a wide
    # margin, otherwise the deterministic email pass would fuse them into one predicted
    # case. Tier D breaks this on purpose and is checked separately below.
    by_customer = {}
    for c in plan:
        if c["tier"] == "D":
            continue
        by_customer.setdefault(c["customer"]["customer_id"], []).append(c["start_h"])
    for cid, starts in by_customer.items():
        starts = sorted(starts)
        for a, b in itertools.pairwise(starts):
            _require(b - a >= MIN_SAME_CUSTOMER_GAP_H, f"{cid} has two cases {b - a:.1f}h apart")

    # Display-name divergence has to reach the keyless tier to be worth anything: on a
    # tier A record the email resolves the customer regardless of what name is printed.
    aliased_ids = {c["customer_id"] for c in customers if c["alias"]}
    keyless_aliased = {c["customer"]["customer_id"] for c in plan
                       if c["tier"] == "B" and c["customer"]["customer_id"] in aliased_ids}
    _require(keyless_aliased, "no aliased customer has a keyless (tier B) case")

    _validate_adversarial(main, adversarial, plan)

    # Channel texts for one issue must be genuinely different from each other.
    for key, issue in ISSUES.items():
        texts = [issue["chat"], issue["email"], issue["qa"], issue["csat"],
                 issue["restate"], issue["escalation"]]
        _require(len(set(texts)) == len(texts), f"{key} reuses a channel text verbatim")

    total = sum(len(v) for v in records.values()) + len(documents)
    planted = sum(len(c["record_ids"]) for c in gt_cases)
    _require(planted + len(noise_ids) == total, "record accounting mismatch")
    return True


def write_ndjson(path, rows):
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    os.makedirs(UNSTRUCT_DIR, exist_ok=True)
    os.makedirs(SEEDS_DIR, exist_ok=True)
    (records, documents, orders, csat_scores, agent_metrics, gt_cases,
     noise_ids, customers, plan) = build()
    validate(customers, plan, gt_cases, noise_ids, records, documents)

    # PDFs are binary, so they are not seeds. They land in a Snowflake stage and are read
    # back with Cortex PARSE_DOCUMENT: see scripts/upload_documents.py and stg_documents.
    documents_dir = Path(DOCUMENTS_DIR)
    documents_dir.mkdir(parents=True, exist_ok=True)
    for stale in documents_dir.glob("*.pdf"):
        stale.unlink()
    for doc in documents:
        write_pdf(os.path.join(DOCUMENTS_DIR, doc["filename"]), doc["lines"])
    write_csv(os.path.join(DOCUMENTS_DIR, "manifest.csv"),
              [{"record_id": d["record_id"], "filename": d["filename"],
                "received_ts": d["received_ts"]} for d in documents],
              ["record_id", "filename", "received_ts"])

    # NDJSON kept in data/ as a reference for the "raw files that land" story.
    write_ndjson(os.path.join(UNSTRUCT_DIR, "chat.ndjson"), records["chat"])
    write_ndjson(os.path.join(UNSTRUCT_DIR, "email.ndjson"), records["email"])
    write_ndjson(os.path.join(UNSTRUCT_DIR, "qa_notes.ndjson"), records["qa"])
    write_ndjson(os.path.join(UNSTRUCT_DIR, "csat.ndjson"), records["csat"])

    # Raw records as seed CSVs so the whole pipeline loads with one `dbt seed`.
    # csv quoting round-trips the embedded JSON / multiline email bodies safely.
    raw_fields = ["record_id", "raw_content", "received_ts"]
    write_csv(os.path.join(SEEDS_DIR, "raw_chat.csv"), records["chat"], raw_fields)
    write_csv(os.path.join(SEEDS_DIR, "raw_email.csv"), records["email"], raw_fields)
    write_csv(os.path.join(SEEDS_DIR, "raw_qa_notes.csv"), records["qa"], raw_fields)
    write_csv(os.path.join(SEEDS_DIR, "raw_csat.csv"), records["csat"], raw_fields)

    write_csv(os.path.join(SEEDS_DIR, "orders.csv"), orders,
              ["order_id", "customer_id", "customer_name", "email", "value", "placed_ts", "status"])
    write_csv(os.path.join(SEEDS_DIR, "csat_scores.csv"), csat_scores,
              ["survey_id", "order_ref", "customer_id", "score", "submitted_ts"])
    write_csv(os.path.join(SEEDS_DIR, "agent_daily_metrics.csv"), agent_metrics,
              ["agent_id", "metric_date", "aht", "fcr", "occupancy", "avg_csat"])

    with open(GROUND_TRUTH, "w") as f:
        json.dump({"cases": gt_cases, "noise_record_ids": noise_ids}, f, indent=2)

    # Ground-truth map as a seed so linkage accuracy is a first-class, tested artifact.
    gt_map = []
    for c in gt_cases:
        for r in c["record_ids"]:
            gt_map.append({"record_id": r, "true_case_id": c["case_id"], "tier": c["tier"],
                           "shape": c["shape"], "is_noise": "false"})
    for r in noise_ids:
        gt_map.append({"record_id": r, "true_case_id": "NOISE_" + r, "tier": "noise",
                       "shape": "noise", "is_noise": "true"})
    write_csv(os.path.join(SEEDS_DIR, "ground_truth_map.csv"), gt_map,
              ["record_id", "true_case_id", "tier", "shape", "is_noise"])

    total = sum(len(v) for v in records.values()) + len(documents)
    print(f"unstructured records: {total} (chat={len(records['chat'])}, email={len(records['email'])}, "
          f"qa={len(records['qa'])}, csat={len(records['csat'])}, pdf={len(documents)})")
    print(f"planted cases: {len(gt_cases)}  noise: {len(noise_ids)}  customers: {len(customers)}")
    print(f"orders: {len(orders)}  csat_scores: {len(csat_scores)}  agent_days: {len(agent_metrics)}")
    tiers, shapes = {}, {}
    for c in gt_cases:
        tiers[c["tier"]] = tiers.get(c["tier"], 0) + 1
        if c["tier"] == "D":
            shapes[c["shape"]] = shapes.get(c["shape"], 0) + 1
    print(f"tiers: {tiers}")
    print(f"tier D shapes: {shapes}")
    aliased = sum(1 for c in customers if c["alias"])
    typo = sum(1 for c in customers if c["email"].split("@")[1] in TYPO_DOMAINS.values())
    print(f"identity noise: {aliased} aliased names, {typo} typo domains, "
          f"{len(ADVERSARIAL_CUSTOMERS)} adversarial customers on "
          f"{len(ADVERSARIAL_CUSTOMERS) // 2} colliding surnames")
    print("invariants: OK")


if __name__ == "__main__":
    main()
