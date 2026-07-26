"""
Synthetic customer-support / BPO data generator for the Case Intelligence pipeline.

Produces BOTH halves of the contract so the pipeline runs end to end without waiting
on teammates, plus the ground-truth key that proves keyless linking worked:

  data/synthetic/unstructured/{chat,email,qa_notes,csat}.ndjson   (raw records)
  seeds/raw_*.csv                                                 (what dbt actually loads)
  seeds/orders.csv, seeds/csat_scores.csv, seeds/agent_daily_metrics.csv  (structured)
  data/synthetic/ground_truth.json + seeds/ground_truth_map.csv   (answer key)

Deterministic: fixed seed + fixed base date, so reruns reproduce and ground truth is stable.
Difficulty tiers per AGENTS.md: A = entity overlap, B = semantic only (hero), C = trivial, + noise.

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

Invariants this generator guarantees, because Stage 2's precision depends on them:
  1. Every customer has a UNIQUE first name and a UNIQUE surname; noise names share
     neither with a customer nor with each other.
  2. Two cases belonging to the same customer are separated by more than
     MIN_SAME_CUSTOMER_GAP_H, which is comfortably wider than Stage 2's link window,
     so a repeat customer never collapses into one giant case.
  3. Records inside one case are tightly clustered in time (hours, not weeks).
  4. Channel texts for one issue are genuinely reworded, never copied, so the semantic
     pass is actually exercised rather than matching on string overlap.
`validate()` asserts all of these before anything is written.

When real data arrives it replaces these outputs at the same schemas. No model changes.
"""

import csv
import json
import os
import random
import re
from datetime import datetime, timedelta

SEED = 42
BASE_DATE = datetime(2026, 5, 4, 8, 0, 0)  # a Monday, fixed for reproducibility
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNSTRUCT_DIR = os.path.join(HERE, "data", "synthetic", "unstructured")
SEEDS_DIR = os.path.join(HERE, "seeds")
GROUND_TRUTH = os.path.join(HERE, "data", "synthetic", "ground_truth.json")

# Demo scale. Stage 1 is one AI_COMPLETE per record and Stage 2 is an O(N^2) pair scan,
# so this is sized for a demo that rebuilds in minutes, not for volume.
TARGET_CASES = 170
NOISE_RECORDS = 55

# Must exceed int_case_assignments.TIME_WINDOW_HOURS (72) with margin: it is what keeps
# a customer's separate cases from merging through the deterministic email/customer pass.
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

_counter = {"chat": 0, "email": 0, "qa": 0, "csat": 0}


def rid(kind):
    _counter[kind] += 1
    return f"{kind}_{_counter[kind]:04d}"


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


def build():
    customers = build_customers()
    plan = build_case_plan(customers)

    records = {"chat": [], "email": [], "qa": [], "csat": []}
    orders, csat_scores = [], []
    agent_load = {}
    gt_cases, noise_ids = [], []

    order_seq = 1000
    survey_seq = 5000

    for case in plan:
        cust = case["customer"]
        issue = ISSUES[case["issue_key"]]
        agent = RNG.choice(AGENTS)
        tier = case["tier"]
        order_ref = None

        if case["has_order"]:
            order_seq += 1
            order_ref = f"ORD_{order_seq}"
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
        ticket = f"TK{RNG.randint(10000, 99999)}" if tier == "C" else None
        expose_email = (tier == "A")
        expose_order = (tier == "A" and case["has_order"])

        case_record_ids = []
        case_csat_value = None

        for ci, ch in enumerate(case["channels"]):
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
                if recontact:
                    lines = [opener.lower(), issue["restate"].lower()]
                else:
                    lines = [issue["chat"]]
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
                    blob["customer_email"] = cust["email"]
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
                from_email = (cust["email"] if expose_email
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
                    note += f" Email {cust['email']}."
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
                survey_seq += 1
                score = csat_score_for(case["resolved"])
                case_csat_value = score
                comment = issue["csat"]
                if recontact:
                    comment = f"{issue['csat']} Having to come back a second time made it worse."
                blob = {"survey_id": f"SV_{survey_seq}", "score": score, "comment": comment,
                        "submitted_at": isofmt(occurred + timedelta(hours=1)), "customer_name": name}
                if expose_order:
                    blob["order_ref"] = order_ref
                records["csat"].append({"record_id": r, "received_ts": isofmt(occurred),
                                        "raw_content": json.dumps(blob)})
                case_record_ids.append(r)
                csat_scores.append({
                    "survey_id": f"SV_{survey_seq}",
                    "order_ref": order_ref or "",
                    "customer_id": cust["customer_id"],
                    "score": score,
                    "submitted_ts": isofmt(occurred + timedelta(hours=1)),
                })

            d = occurred.date().isoformat()
            agent_load[(agent["agent_id"], d)] = agent_load.get((agent["agent_id"], d), 0) + 1

        gt_cases.append({
            "case_id": case["case_id"], "tier": tier, "customer_id": cust["customer_id"],
            "issue": case["issue_key"], "root_cause": issue["root_cause"],
            "resolution": issue["resolution"], "resolved": case["resolved"],
            "record_ids": case_record_ids,
            "revenue_at_risk": case["order_value"] if (case["has_order"] and not case["resolved"]) else 0.0,
        })

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

    return records, orders, csat_scores, agent_metrics, gt_cases, noise_ids, customers, plan


# --------------------------------------------------------------------------------------
# Invariants. These are the properties Stage 2's measured precision depends on, so they
# are checked here rather than discovered later in a failing dbt test.
# --------------------------------------------------------------------------------------

def validate(customers, plan, gt_cases, noise_ids, records):
    firsts = [c["first"] for c in customers]
    lasts = [c["last"] for c in customers]
    assert len(set(firsts)) == len(firsts), "customer first names must be unique"
    assert len(set(lasts)) == len(lasts), "customer surnames must be unique"

    noise_lasts = [n[1] for n in NOISE_NAMES[:NOISE_RECORDS]]
    assert len(set(noise_lasts)) == len(noise_lasts), "noise surnames must be unique"
    assert not (set(noise_lasts) & set(lasts)), "noise surnames must not collide with customers"

    alias_firsts = {c["alias"] for c in customers if c["alias"]}
    assert not (alias_firsts & set(firsts)), "aliases must not collide with real first names"

    # Stage 2's semantic pass gates on shared name tokens of 3+ characters, so token
    # overlap between pools is what would let a noise record drift into a real case, or
    # two unrelated noise records merge with each other. Check at the token level, not
    # just the surname level: an alias colliding with somebody's noise surname is enough.
    def toks(s):
        return {t for t in re.findall(r"[a-z]{3,}", s.lower())}

    customer_tokens = set()
    for c in customers:
        customer_tokens |= toks(c["first"]) | toks(c["last"])
        if c["alias"]:
            customer_tokens |= toks(c["alias"])
    noise_tokens, seen_noise = set(), {}
    for first, last in NOISE_NAMES[:NOISE_RECORDS]:
        these = toks(first) | toks(last)
        for t in these:
            assert t not in seen_noise, f"noise name token '{t}' reused by two noise records"
            seen_noise[t] = True
        noise_tokens |= these
    assert not (noise_tokens & customer_tokens), \
        f"noise names share tokens with customers: {sorted(noise_tokens & customer_tokens)}"

    # A customer's separate cases must clear Stage 2's link window by a wide margin,
    # otherwise the deterministic email pass would fuse them into one predicted case.
    by_customer = {}
    for c in plan:
        by_customer.setdefault(c["customer"]["customer_id"], []).append(c["start_h"])
    for cid, starts in by_customer.items():
        starts = sorted(starts)
        for a, b in zip(starts, starts[1:]):
            assert b - a >= MIN_SAME_CUSTOMER_GAP_H, f"{cid} has two cases {b - a:.1f}h apart"

    # Channel texts for one issue must be genuinely different from each other.
    for key, issue in ISSUES.items():
        texts = [issue["chat"], issue["email"], issue["qa"], issue["csat"], issue["restate"]]
        assert len(set(texts)) == len(texts), f"{key} reuses a channel text verbatim"

    total = sum(len(v) for v in records.values())
    planted = sum(len(c["record_ids"]) for c in gt_cases)
    assert planted + len(noise_ids) == total, "record accounting mismatch"
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
    records, orders, csat_scores, agent_metrics, gt_cases, noise_ids, customers, plan = build()
    validate(customers, plan, gt_cases, noise_ids, records)

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
            gt_map.append({"record_id": r, "true_case_id": c["case_id"], "tier": c["tier"], "is_noise": "false"})
    for r in noise_ids:
        gt_map.append({"record_id": r, "true_case_id": "NOISE_" + r, "tier": "noise", "is_noise": "true"})
    write_csv(os.path.join(SEEDS_DIR, "ground_truth_map.csv"), gt_map,
              ["record_id", "true_case_id", "tier", "is_noise"])

    total = sum(len(v) for v in records.values())
    print(f"unstructured records: {total} (chat={len(records['chat'])}, email={len(records['email'])}, "
          f"qa={len(records['qa'])}, csat={len(records['csat'])})")
    print(f"planted cases: {len(gt_cases)}  noise: {len(noise_ids)}  customers: {len(customers)}")
    print(f"orders: {len(orders)}  csat_scores: {len(csat_scores)}  agent_days: {len(agent_metrics)}")
    tiers = {}
    for c in gt_cases:
        tiers[c["tier"]] = tiers.get(c["tier"], 0) + 1
    print(f"tiers: {tiers}")
    aliased = sum(1 for c in customers if c["alias"])
    typo = sum(1 for c in customers if c["email"].split("@")[1] in TYPO_DOMAINS.values())
    print(f"identity noise: {aliased} aliased names, {typo} typo domains")
    print("invariants: OK")


if __name__ == "__main__":
    main()
