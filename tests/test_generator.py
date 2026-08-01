"""
Unit tests for the synthetic data generator.

These run with no Snowflake connection and no credentials, so CI can execute them on
every push. They guard the properties Stage 2's measured accuracy depends on: if the
corpus stops being deterministic, or a name pool starts colliding, the linkage result
stops meaning anything and these fail before a build ever reaches the warehouse.

The pipeline's accuracy itself is tested separately, in dbt, by
tests/assert_cases_fully_linked.sql and tests/assert_no_case_contamination.sql.
"""

import importlib.util
import itertools
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load_generator():
    """Import the generator by path: scripts/ is not a package."""
    spec = importlib.util.spec_from_file_location(
        "generate_synthetic_data", REPO / "scripts" / "generate_synthetic_data.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen():
    return _load_generator()


@pytest.fixture(scope="module")
def built(gen):
    """build() returns everything the generator would write, without touching disk."""
    records, orders, csat, agent_metrics, gt_cases, noise_ids, customers, plan = gen.build()
    return {
        "records": records, "orders": orders, "csat": csat, "agent_metrics": agent_metrics,
        "gt_cases": gt_cases, "noise_ids": noise_ids, "customers": customers, "plan": plan,
    }


def _tokens(text):
    return set(re.findall(r"[a-z]{3,}", text.lower()))


# --------------------------------------------------------------------------------------
# Determinism. Ground truth is only meaningful if the corpus is reproducible.
# --------------------------------------------------------------------------------------

def test_generator_is_deterministic():
    first = _load_generator().build()
    second = _load_generator().build()
    assert first[4] == second[4], "ground-truth cases differ between runs"
    assert first[5] == second[5], "noise record ids differ between runs"
    for channel in first[0]:
        assert first[0][channel] == second[0][channel], f"{channel} records differ between runs"


# --------------------------------------------------------------------------------------
# Name pools. Collisions here are what would produce false merges in Stage 2.
# --------------------------------------------------------------------------------------

def test_customer_names_are_unique(built):
    firsts = [c["first"] for c in built["customers"]]
    lasts = [c["last"] for c in built["customers"]]
    assert len(set(firsts)) == len(firsts)
    assert len(set(lasts)) == len(lasts)


def test_noise_names_share_no_token_with_customers(gen, built):
    customer_tokens = set()
    for c in built["customers"]:
        customer_tokens |= _tokens(c["first"]) | _tokens(c["last"])
        if c["alias"]:
            customer_tokens |= _tokens(c["alias"])

    noise_tokens = set()
    for first, last in gen.NOISE_NAMES[: gen.NOISE_RECORDS]:
        noise_tokens |= _tokens(first) | _tokens(last)

    overlap = noise_tokens & customer_tokens
    assert not overlap, f"noise would link to real cases through {sorted(overlap)}"


def test_no_two_noise_records_share_a_name_token(gen):
    seen = Counter()
    for first, last in gen.NOISE_NAMES[: gen.NOISE_RECORDS]:
        for token in _tokens(first) | _tokens(last):
            seen[token] += 1
    repeated = [t for t, n in seen.items() if n > 1]
    assert not repeated, f"noise records would merge with each other through {repeated}"


def test_aliases_never_impersonate_another_customer(gen, built):
    firsts = {c["first"] for c in built["customers"]}
    assert not (set(gen.ALIAS_FIRSTS) & firsts)


# --------------------------------------------------------------------------------------
# Case layout. A customer's separate cases must not fuse through the deterministic pass.
# --------------------------------------------------------------------------------------

def test_one_customers_cases_clear_the_link_window(gen, built):
    by_customer = {}
    for case in built["plan"]:
        by_customer.setdefault(case["customer"]["customer_id"], []).append(case["start_h"])

    for customer_id, starts in by_customer.items():
        ordered = sorted(starts)
        for earlier, later in itertools.pairwise(ordered):
            gap = later - earlier
            assert gap >= gen.MIN_SAME_CUSTOMER_GAP_H, (
                f"{customer_id} has cases {gap:.1f}h apart, inside Stage 2's "
                f"{gen.TIME_WINDOW_HOURS if hasattr(gen, 'TIME_WINDOW_HOURS') else 72}h window"
            )


def test_records_within_a_case_are_tightly_clustered(built):
    """Francis's data spread every case over 41 days; ours must stay inside hours."""
    from datetime import UTC, datetime

    by_case = {c["case_id"]: c["record_ids"] for c in built["gt_cases"]}
    stamps = {}
    for channel_records in built["records"].values():
        for record in channel_records:
            stamps[record["record_id"]] = datetime.strptime(
                record["received_ts"], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=UTC)

    for case_id, record_ids in by_case.items():
        times = [stamps[r] for r in record_ids]
        spread_hours = (max(times) - min(times)).total_seconds() / 3600
        assert spread_hours <= 72, f"{case_id} spans {spread_hours:.1f}h"


# --------------------------------------------------------------------------------------
# Corpus shape and the answer key.
# --------------------------------------------------------------------------------------

def test_all_three_difficulty_tiers_are_present(built):
    tiers = Counter(c["tier"] for c in built["gt_cases"])
    assert tiers["A"] > 0 and tiers["B"] > 0 and tiers["C"] > 0
    assert tiers["B"] > tiers["A"], "Tier B is the hero tier and should dominate"


def test_every_record_is_accounted_for_in_ground_truth(built):
    total = sum(len(v) for v in built["records"].values())
    planted = sum(len(c["record_ids"]) for c in built["gt_cases"])
    assert planted + len(built["noise_ids"]) == total


def test_record_ids_are_unique(built):
    ids = [r["record_id"] for channel in built["records"].values() for r in channel]
    assert len(set(ids)) == len(ids)


def test_channel_texts_are_reworded_not_copied(gen):
    """If two channels share a string, the semantic pass is matching on string overlap
    rather than meaning, and the Tier B result would be an illusion."""
    for key, issue in gen.ISSUES.items():
        texts = [issue["chat"], issue["email"], issue["qa"], issue["csat"], issue["restate"]]
        assert len(set(texts)) == len(texts), f"{key} reuses a channel text verbatim"


def test_every_issue_has_a_subject_and_a_category(gen):
    for key, issue in gen.ISSUES.items():
        assert issue.get("subject"), f"{key} has no email subject"
        assert issue.get("area"), f"{key} has no product area"


# --------------------------------------------------------------------------------------
# Identity noise harvested from the teammate datasets (see docs/realism-report.md).
# --------------------------------------------------------------------------------------

def test_typo_domains_appear_but_stay_a_minority(gen, built):
    typo = [c for c in built["customers"] if c["email"].split("@")[1] in gen.TYPO_DOMAINS.values()]
    assert typo, "no typo domains generated; identity resolution is not being exercised"
    assert len(typo) / len(built["customers"]) < 0.25


def test_display_name_divergence_keeps_the_surname(built):
    """The email may contradict the account's first name, but the surname has to survive:
    it is the anchor the keyless linking depends on."""
    aliased = [c for c in built["customers"] if c["alias"]]
    assert aliased, "no aliased customers generated"
    for customer in aliased:
        local_part = customer["email"].split("@")[0]
        assert customer["last"].lower() in local_part


def test_validate_accepts_a_freshly_built_corpus(gen, built):
    assert gen.validate(
        built["customers"], built["plan"], built["gt_cases"],
        built["noise_ids"], built["records"],
    )


def test_validate_rejects_a_corpus_with_colliding_surnames(gen, built):
    broken = [dict(c) for c in built["customers"]]
    broken[1]["last"] = broken[0]["last"]
    with pytest.raises(gen.InvariantError, match="surnames must be unique"):
        gen.validate(broken, built["plan"], built["gt_cases"], built["noise_ids"], built["records"])
