"""
Synthetic customer-support / BPO data generator for the Case Intelligence pipeline.

Produces BOTH halves of the contract so the pipeline runs end to end without waiting
on teammates, plus the ground-truth key that proves keyless linking worked:

  data/synthetic/unstructured/{chat,email,qa_notes,csat}.ndjson   (raw records)
  seeds/orders.csv, seeds/csat_scores.csv, seeds/agent_daily_metrics.csv  (structured)
  data/synthetic/ground_truth.json                                (answer key)

Deterministic: fixed seed + fixed base date, so reruns reproduce and ground truth is stable.
Difficulty tiers per AGENTS.md: A = entity overlap, B = semantic only (hero), C = trivial, + noise.

When real data arrives it replaces these outputs at the same schemas. No model changes.
"""

import csv
import json
import os
import random
from datetime import datetime, timedelta

SEED = 42
BASE_DATE = datetime(2026, 6, 1, 9, 0, 0)  # fixed for reproducibility
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNSTRUCT_DIR = os.path.join(HERE, "data", "synthetic", "unstructured")
SEEDS_DIR = os.path.join(HERE, "seeds")
GROUND_TRUTH = os.path.join(HERE, "data", "synthetic", "ground_truth.json")

random.seed(SEED)

AGENTS = ["A_ROSA", "A_LIAM", "A_PRIYA", "A_KOJI", "A_MARE"]

# Each issue has channel-specific paraphrases so Tier B (semantic-only) linking is realistic:
# the SAME issue is described in DIFFERENT words across channels, with no shared identifier.
ISSUES = {
    "order_not_received": {
        "root_cause": "Carrier marked delivered but parcel never arrived (lost in transit).",
        "resolution": "Reshipped with express tracking; refunded shipping.",
        "chat": "hey my order still hasnt shown up, tracking says delivered but nothing here",
        "email": "I am writing because the package I was expecting was marked delivered three days ago, yet it has not arrived at my address. Please advise.",
        "qa": "Customer reports non-receipt of a parcel showing delivered status. Agent opened carrier trace.",
        "csat": "Still waiting on my parcel that never came, took ages to sort out.",
    },
    "double_charge": {
        "root_cause": "Payment retry fired twice after a gateway timeout.",
        "resolution": "Reversed the duplicate charge; confirmed single settlement.",
        "chat": "i got billed twice for the same thing?? theres two charges on my card",
        "email": "My statement shows two identical charges for one purchase. I would like the duplicate removed and a confirmation.",
        "qa": "Billing dispute: duplicate transaction from a retry after timeout. Agent raised reversal.",
        "csat": "Charged me twice and it was a hassle to get the second one back.",
    },
    "login_locked": {
        "root_cause": "Account auto-locked after failed MFA sync on a new device.",
        "resolution": "Reset MFA and unlocked the account.",
        "chat": "cant get into my account, keeps saying locked after i put the code in",
        "email": "I am unable to sign in. After entering my verification code the system reports my account is locked. Can you restore access?",
        "qa": "Access issue: MFA lockout on new device. Agent performed identity check and reset.",
        "csat": "Locked out for a whole day, frustrating but eventually fixed.",
    },
    "wrong_item": {
        "root_cause": "Warehouse pick error: adjacent SKU shipped.",
        "resolution": "Sent correct item; provided prepaid return label.",
        "chat": "you sent me the wrong item, this isnt what i ordered at all",
        "email": "The product I received does not match my order. A different item was shipped in its place. Please correct this.",
        "qa": "Fulfilment error, wrong SKU shipped. Agent arranged replacement and return.",
        "csat": "Got the wrong thing first time, sorting the swap was slow.",
    },
    "refund_delay": {
        "root_cause": "Refund stuck in manual review queue past SLA.",
        "resolution": "Escalated and released the refund same day.",
        "chat": "wheres my refund, its been like 2 weeks and nothing",
        "email": "I requested a refund some time ago and it has still not appeared. This is well beyond the stated timeframe.",
        "qa": "Refund SLA breach, stuck in review. Agent escalated to finance.",
        "csat": "Refund took forever, had to chase it myself.",
    },
    "app_sync_fail": {
        "root_cause": "Sync token expired; client failed to refresh silently.",
        "resolution": "Forced token refresh; data reconciled.",
        "chat": "the app isnt syncing, my stuff is all out of date on my phone",
        "email": "The application is not synchronising. Information shown on my device is stale and does not reflect recent changes.",
        "qa": "Sync failure due to expired token. Agent walked customer through reauth.",
        "csat": "App wouldnt sync for days, annoying.",
    },
}

# Customers. Name variants always keep the FULL last name so a Tier B (keyless)
# case is solvably hard: no shared email/order, but the last-name token plus issue
# semantics + temporal proximity is enough to link. Different customers have
# different last names, so this signal does not merge unrelated cases.
CUSTOMERS = [
    {"customer_id": "CUST_001", "email": "j.okafor@example.com", "first": "Joy", "last": "Okafor"},
    {"customer_id": "CUST_002", "email": "m.tanaka@example.com", "first": "Mika", "last": "Tanaka"},
    {"customer_id": "CUST_003", "email": "l.becker@example.com", "first": "Luca", "last": "Becker"},
    {"customer_id": "CUST_004", "email": "s.nair@example.com", "first": "Sana", "last": "Nair"},
    {"customer_id": "CUST_005", "email": "d.owens@example.com", "first": "Dana", "last": "Owens"},
    {"customer_id": "CUST_006", "email": "r.silva@example.com", "first": "Rui", "last": "Silva"},
    {"customer_id": "CUST_007", "email": "e.haddad@example.com", "first": "Elias", "last": "Haddad"},
    {"customer_id": "CUST_008", "email": "n.petrova@example.com", "first": "Nadia", "last": "Petrova"},
]


def name_variants(c):
    return [f"{c['first']} {c['last']}", f"{c['first'][0]}. {c['last']}", f"{c['last']}, {c['first']}"]

# Planted cases: (customer_idx, issue_key, tier, channels, resolved, has_order, order_value)
CASE_PLAN = [
    (0, "order_not_received", "A", ["chat", "email", "csat"], True, True, 240.00),
    (1, "double_charge", "A", ["chat", "qa"], True, True, 89.50),
    (2, "login_locked", "B", ["chat", "email"], True, False, None),
    (3, "refund_delay", "B", ["email", "qa", "csat"], True, True, 156.00),
    (4, "wrong_item", "B", ["chat", "email"], False, True, 312.75),
    (5, "app_sync_fail", "A", ["chat", "qa"], True, False, None),
    (6, "order_not_received", "C", ["email", "csat"], True, True, 74.20),
    (7, "double_charge", "B", ["chat", "email", "csat"], False, True, 420.00),
]

_counter = {"chat": 0, "email": 0, "qa": 0, "csat": 0}


def rid(kind):
    _counter[kind] += 1
    return f"{kind}_{_counter[kind]:03d}"


def ts(offset_hours):
    return BASE_DATE + timedelta(hours=offset_hours)


def isofmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def build():
    records = {"chat": [], "email": [], "qa": [], "csat": []}
    orders, csat_scores = [], []
    agent_days = {}  # (agent, date) -> counts
    gt_cases, noise_ids = [], []

    order_seq = 1000
    survey_seq = 5000
    global_offset = 0

    for case_idx, (cust_i, issue_key, tier, channels, resolved, has_order, order_value) in enumerate(CASE_PLAN, 1):
        cust = CUSTOMERS[cust_i]
        issue = ISSUES[issue_key]
        case_id = f"CASE_{case_idx:03d}"
        agent = random.choice(AGENTS)
        order_ref = None

        if has_order:
            order_seq += 1
            order_ref = f"ORD_{order_seq}"
            placed = ts(global_offset - 72)
            status = "delivered" if issue_key == "order_not_received" else "completed"
            orders.append({
                "order_id": order_ref, "customer_id": cust["customer_id"],
                "customer_name": f"{cust['first']} {cust['last']}", "email": cust["email"],
                "value": order_value, "placed_ts": isofmt(placed),
                "status": "lost" if issue_key == "order_not_received" else status,
            })

        # Tier controls which identifiers are exposed in the raw text.
        #  A: email and/or order_ref present and shared across records.
        #  B: no email, no order_ref; only name variants + same issue + close timestamps.
        #  C: a shared ticket id token.
        ticket = f"TK{random.randint(10000, 99999)}" if tier == "C" else None
        case_record_ids = []

        for ci, ch in enumerate(channels):
            offset = global_offset + ci * 2  # records close in time within a case
            occurred = ts(offset)
            name = random.choice(name_variants(cust))
            expose_email = (tier == "A")
            expose_order = (tier == "A" and has_order)

            if ch == "chat":
                r = rid("chat")
                transcript = [
                    {"role": "customer", "text": issue["chat"]},
                    {"role": "agent", "text": "Thanks for reaching out, let me take a look into this for you."},
                ]
                blob = {
                    "session_id": r, "channel": "chat", "started_at": isofmt(occurred), "agent_id": agent,
                    "customer_name": name, "transcript": transcript,
                }
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
                from_email = cust["email"] if expose_email else f"{name.split()[0].lower()}@mailbox.example.com"
                lines = [f"From: {name} <{from_email}>", "To: support@company.example.com",
                         f"Subject: {'Re: ' + ticket + ' ' if ticket else ''}{issue_key.replace('_', ' ').title()}",
                         f"Date: {isofmt(occurred)}", ""]
                body = issue["email"]
                if expose_order:
                    body += f"\n\nOrder reference: {order_ref}"
                lines.append(body)
                records["email"].append({"record_id": r, "received_ts": isofmt(occurred),
                                         "raw_content": "\n".join(lines)})
                case_record_ids.append(r)

            elif ch == "qa":
                r = rid("qa")
                note = f"QA review — agent {agent}. Customer {name}. {issue['qa']}"
                if expose_email:
                    note += f" Email {cust['email']}."
                if expose_order:
                    note += f" Ref {order_ref}."
                if ticket:
                    note += f" Ticket {ticket}."
                records["qa"].append({"record_id": r, "received_ts": isofmt(occurred),
                                      "raw_content": note})
                case_record_ids.append(r)

            elif ch == "csat":
                r = rid("csat")
                survey_seq += 1
                score = 5 if resolved and tier != "C" else (2 if not resolved else 3)
                blob = {"survey_id": f"SV_{survey_seq}", "score": score, "comment": issue["csat"],
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
            agent_days.setdefault((agent, d), 0)
            agent_days[(agent, d)] += 1

        gt_cases.append({
            "case_id": case_id, "tier": tier, "customer_id": cust["customer_id"],
            "issue": issue_key, "root_cause": issue["root_cause"], "resolution": issue["resolution"],
            "resolved": resolved, "record_ids": case_record_ids,
            "revenue_at_risk": order_value if (has_order and not resolved) else 0.0,
        })
        global_offset += 12  # separate cases in time

    # Noise: unrelated single records that must NOT merge into any case. Each gets a
    # UNIQUE last name (no overlap with planted customers or each other) and its own
    # far-apart time window, so identity resolution correctly leaves them as singletons.
    noise_names = ["Alex Ferro", "Sam Quill", "Noa Vance", "Kai Ash", "Remy Bloom", "Toni Crane",
                   "Lee Dial", "Max Ember", "Ivy Frost", "Cy Gale", "Bo Holt", "Ada Iver"]
    for k in range(12):
        issue = ISSUES[list(ISSUES.keys())[k % len(ISSUES)]]
        ch = ["chat", "email", "qa", "csat"][k % 4]
        offset = global_offset + 24 + k * 96  # ~4 days apart, well outside the link window
        occurred = ts(offset)
        name = noise_names[k]
        if ch == "chat":
            r = rid("chat")
            records["chat"].append({"record_id": r, "received_ts": isofmt(occurred),
                                    "raw_content": json.dumps({"session_id": r, "channel": "chat",
                                    "started_at": isofmt(occurred), "agent_id": random.choice(AGENTS),
                                    "customer_name": name, "transcript": [{"role": "customer", "text": issue["chat"]}]})})
        elif ch == "email":
            r = rid("email")
            records["email"].append({"record_id": r, "received_ts": isofmt(occurred),
                                     "raw_content": f"From: {name} <noise{k}@mailbox.example.com>\nTo: support@company.example.com\nSubject: help\nDate: {isofmt(occurred)}\n\n{issue['email']}"})
        elif ch == "qa":
            r = rid("qa")
            records["qa"].append({"record_id": r, "received_ts": isofmt(occurred),
                                  "raw_content": f"QA review. Customer {name}. {issue['qa']}"})
        else:
            r = rid("csat")
            records["csat"].append({"record_id": r, "received_ts": isofmt(occurred),
                                    "raw_content": json.dumps({"survey_id": f"SV_noise_{r}", "score": random.randint(1, 5),
                                    "comment": issue["csat"], "submitted_at": isofmt(occurred), "customer_name": name})})
        noise_ids.append(r)

    # agent_daily_metrics: values that move with load.
    agent_metrics = []
    for (agent, d), n in sorted(agent_days.items()):
        agent_metrics.append({
            "agent_id": agent, "metric_date": d,
            "aht": round(6.0 + n * 1.5 + random.uniform(-0.5, 0.5), 1),
            "fcr": round(max(0.5, 0.9 - n * 0.05), 2),
            "occupancy": round(min(0.98, 0.7 + n * 0.03), 2),
            "avg_csat": round(random.uniform(3.5, 4.8), 1),
        })

    return records, orders, csat_scores, agent_metrics, gt_cases, noise_ids


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
    records, orders, csat_scores, agent_metrics, gt_cases, noise_ids = build()

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

    total = sum(len(v) for v in records.values())
    print(f"unstructured records: {total} (chat={len(records['chat'])}, email={len(records['email'])}, "
          f"qa={len(records['qa'])}, csat={len(records['csat'])})")
    print(f"planted cases: {len(gt_cases)}  noise: {len(noise_ids)}")
    print(f"orders: {len(orders)}  csat_scores: {len(csat_scores)}  agent_days: {len(agent_metrics)}")
    tiers = {}
    for c in gt_cases:
        tiers[c["tier"]] = tiers.get(c["tier"], 0) + 1
    print(f"tiers: {tiers}")


if __name__ == "__main__":
    main()
