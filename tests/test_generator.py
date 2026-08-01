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
    (records, documents, orders, csat, agent_metrics, gt_cases,
     noise_ids, customers, plan) = gen.build()
    return {
        "records": records, "documents": documents, "orders": orders, "csat": csat,
        "agent_metrics": agent_metrics, "gt_cases": gt_cases, "noise_ids": noise_ids,
        "customers": customers, "plan": plan,
    }


def _tokens(text):
    return set(re.findall(r"[a-z]{3,}", text.lower()))


# --------------------------------------------------------------------------------------
# Determinism. Ground truth is only meaningful if the corpus is reproducible.
# --------------------------------------------------------------------------------------

def test_generator_is_deterministic():
    first = _load_generator().build()
    second = _load_generator().build()
    assert first[5] == second[5], "ground-truth cases differ between runs"
    assert first[6] == second[6], "noise record ids differ between runs"
    assert first[1] == second[1], "PDF documents differ between runs"
    for channel in first[0]:
        assert first[0][channel] == second[0][channel], f"{channel} records differ between runs"


# --------------------------------------------------------------------------------------
# Name pools.
#
# These no longer assert that names never collide, because a corpus in which they never
# collide is a corpus the resolver cannot fail on -- and a result measured on it says
# nothing. What they assert instead is that collisions exist exactly where they were
# planted: absent from the main pool, which is the regression floor, and present in the
# adversarial pool, which is where the method's real behaviour is measured.
# --------------------------------------------------------------------------------------

def _main_pool(built):
    return [c for c in built["customers"] if c.get("pool", "main") == "main"]


def _adversarial_pool(built):
    return [c for c in built["customers"] if c.get("pool") == "adversarial"]


def _cases_of_shape(built, shape):
    return [c for c in built["plan"] if c.get("shape") == shape]


def test_main_pool_names_are_unique(built):
    firsts = [c["first"] for c in _main_pool(built)]
    lasts = [c["last"] for c in _main_pool(built)]
    assert len(set(firsts)) == len(firsts)
    assert len(set(lasts)) == len(lasts)


def test_adversarial_pool_collides_on_surname_by_design(gen, built):
    """The point of tier D. If this ever passes trivially, the adversarial tier has
    stopped being adversarial and the headline result is self-fulfilling again."""
    collision_pool = _adversarial_pool(built)[: len(gen.ADVERSARIAL_CUSTOMERS)]
    by_surname = Counter(c["last"] for c in collision_pool)
    assert by_surname, "no adversarial customers generated"
    assert all(n == 2 for n in by_surname.values()), by_surname
    for surname, _ in by_surname.items():
        firsts = {c["first"] for c in collision_pool if c["last"] == surname}
        assert len(firsts) == 2, f"{surname} is one person, not a collision"


def test_adversarial_names_never_collide_with_the_main_pool(built):
    """Containment. Tier D may contaminate itself; it must not reach the tiers whose
    100% result is the regression floor."""
    main_tokens = set()
    for c in _main_pool(built):
        main_tokens |= _tokens(c["first"]) | _tokens(c["last"])
        if c["alias"]:
            main_tokens |= _tokens(c["alias"])

    for c in _adversarial_pool(built):
        overlap = (_tokens(c["first"]) | _tokens(c["last"])) & main_tokens
        assert not overlap, f"{c['customer_id']} leaks into the main pool through {sorted(overlap)}"


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

def test_one_main_pool_customers_cases_clear_the_link_window(gen, built):
    by_customer = {}
    for case in built["plan"]:
        if case["tier"] == "D":
            continue  # tier D breaks this on purpose; see the shape tests below
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
    everything = [r for channel in built["records"].values() for r in channel]
    everything += built["documents"]
    for record in everything:
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

def test_all_difficulty_tiers_are_present(built):
    tiers = Counter(c["tier"] for c in built["gt_cases"])
    assert tiers["A"] > 0 and tiers["B"] > 0 and tiers["C"] > 0 and tiers["D"] > 0
    assert tiers["B"] > tiers["A"], "Tier B is the hero tier and should dominate"


# --------------------------------------------------------------------------------------
# Tier D. Each shape has to break exactly one thing, or a failure in the scored results
# cannot be attributed to a cause.
# --------------------------------------------------------------------------------------

def test_every_tier_d_shape_is_planted(built):
    shapes = Counter(c["shape"] for c in built["gt_cases"] if c["tier"] == "D")
    assert shapes["collision_with_identity"] > 0
    assert shapes["collision_keyless"] > 0
    assert shapes["same_customer_in_window"] > 0


def test_collision_shapes_are_genuinely_confusable(gen, built):
    """Two different people, one surname, inside the link window. If any of those three
    stops holding, the shape is no longer testing identity resolution."""
    for shape in ("collision_with_identity", "collision_keyless"):
        pairs = {}
        for case in _cases_of_shape(built, shape):
            pairs.setdefault(case["customer"]["last"], []).append(case)
        assert pairs, f"{shape} was not planted"
        for surname, group in pairs.items():
            assert len(group) == 2, f"{shape} pair {surname} has {len(group)} cases"
            first, second = sorted(group, key=lambda c: c["start_h"])
            assert first["customer"]["customer_id"] != second["customer"]["customer_id"]
            gap = second["start_h"] - first["start_h"]
            assert gap < gen.LINK_WINDOW_HOURS, f"{surname} is {gap:.1f}h apart, outside the window"


def test_the_keyless_collision_exposes_no_identifier_at_all(built):
    """This shape's whole claim is that only the cosine floor is left. An email or an
    order reference anywhere in it would quietly hand the resolver the answer."""
    cases = _cases_of_shape(built, "collision_keyless")
    assert cases
    for case in cases:
        assert not case["expose_email"]
        assert not case["expose_order"]
        assert not case["has_order"]


def test_the_identity_collision_is_separable_only_by_structured_evidence(built):
    """Same surname, same window, same issue: name, time and meaning all agree, so the
    order and the address are the only things that say these are two people."""
    cases = _cases_of_shape(built, "collision_with_identity")
    assert cases
    by_surname = {}
    for case in cases:
        by_surname.setdefault(case["customer"]["last"], []).append(case)
    for surname, group in by_surname.items():
        assert len({c["issue_key"] for c in group}) == 1, f"{surname} differs in issue"
        assert all(c["expose_email"] for c in group), f"{surname} exposes no identity"


def test_a_corrupted_address_disagrees_with_the_order(gen, built):
    """A typo domain that is written to both the record and the order never breaks
    anything. It only bites when the two disagree, which is what this asserts."""
    corrupted = [c for c in built["plan"] if c.get("corrupt_email")]
    assert corrupted, "no case carries a corrupted address, so typo domains are decorative"
    orders_by_customer = {o["customer_id"]: o["email"] for o in built["orders"]}
    for case in corrupted:
        account = case["customer"]["email"]
        assert gen.corrupt_domain(account) != account
        assert orders_by_customer.get(case["customer"]["customer_id"]) == account


def test_repeat_episodes_sit_inside_the_link_window(gen, built):
    cases = _cases_of_shape(built, "same_customer_in_window")
    assert cases
    by_customer = {}
    for case in cases:
        by_customer.setdefault(case["customer"]["customer_id"], []).append(case)
    for customer_id, group in by_customer.items():
        assert len(group) == 2
        first, second = sorted(group, key=lambda c: c["start_h"])
        gap = second["start_h"] - first["start_h"]
        assert gap < gen.LINK_WINDOW_HOURS, f"{customer_id} is {gap:.1f}h apart, outside the window"
        assert first["issue_key"] != second["issue_key"], "two episodes, two problems"


def test_the_repeat_gaps_straddle_the_episode_bound(gen):
    """Planting every gap on one side of Stage 2's episode-gap rule would measure only
    the side it was planted on."""
    gaps = gen.SAME_CUSTOMER_WINDOW_GAPS_H
    assert any(g < gen.MAX_EPISODE_GAP_HOURS for g in gaps)
    assert any(g > gen.MAX_EPISODE_GAP_HOURS for g in gaps)


def test_every_record_is_accounted_for_in_ground_truth(built):
    total = sum(len(v) for v in built["records"].values()) + len(built["documents"])
    planted = sum(len(c["record_ids"]) for c in built["gt_cases"])
    assert planted + len(built["noise_ids"]) == total


def test_no_record_is_written_without_a_timestamp(built):
    """Stage 2 reads occurred_ts for both the link window and the episode bound, and a
    record without one is not held apart by either: it can bridge anything it shares an
    address with, at any distance. The resolver admits such a record deliberately rather
    than orphaning it, which is only safe while the seeds never contain one."""
    from datetime import datetime

    everything = [r for channel in built["records"].values() for r in channel]
    everything += built["documents"]
    assert everything
    for record in everything:
        assert record["received_ts"], f"{record['record_id']} has no timestamp"
        datetime.strptime(record["received_ts"], "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007


def test_record_ids_are_unique(built):
    ids = [r["record_id"] for channel in built["records"].values() for r in channel]
    ids += [d["record_id"] for d in built["documents"]]
    assert len(set(ids)) == len(ids)


def test_channel_texts_are_reworded_not_copied(gen):
    """If two channels share a string, the semantic pass is matching on string overlap
    rather than meaning, and the Tier B result would be an illusion."""
    for key, issue in gen.ISSUES.items():
        texts = [issue["chat"], issue["email"], issue["qa"], issue["csat"],
                 issue["restate"], issue["escalation"]]
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


def test_display_name_divergence_reaches_the_keyless_tier(built):
    """On a tier A record the email resolves the customer whatever name is printed, so
    a diverging display name only costs the resolver something on a keyless record."""
    aliased = {c["customer_id"] for c in built["customers"] if c["alias"]}
    keyless = {c["customer"]["customer_id"] for c in built["plan"] if c["tier"] == "B"}
    assert aliased & keyless, "display-name divergence never lands on a keyless case"


def test_validate_accepts_a_freshly_built_corpus(gen, built):
    assert gen.validate(
        built["customers"], built["plan"], built["gt_cases"],
        built["noise_ids"], built["records"], built["documents"],
    )


def test_validate_rejects_a_main_pool_surname_collision(gen, built):
    broken = [dict(c) for c in built["customers"]]
    broken[1]["last"] = broken[0]["last"]
    with pytest.raises(gen.InvariantError, match="main-pool surnames must be unique"):
        gen.validate(broken, built["plan"], built["gt_cases"], built["noise_ids"],
                     built["records"], built["documents"])


def test_validate_rejects_an_adversarial_name_leaking_into_the_main_pool(gen, built):
    """Containment is what keeps the main tiers usable as a regression floor, so it is
    guarded rather than assumed."""
    broken = [dict(c) for c in built["customers"]]
    main_surname = next(c["last"] for c in broken if c.get("pool", "main") == "main")
    leaking = next(c for c in broken if c.get("pool") == "adversarial")
    leaking["last"] = main_surname
    with pytest.raises(gen.InvariantError, match="collides with the main pool"):
        gen.validate(broken, built["plan"], built["gt_cases"], built["noise_ids"],
                     built["records"], built["documents"])


# --------------------------------------------------------------------------------------
# The fifth modality: PDF escalation forms read back with Cortex PARSE_DOCUMENT.
# --------------------------------------------------------------------------------------

def test_documents_are_produced_and_mostly_keyless(built):
    docs = built["documents"]
    assert docs, "no PDF documents generated; the fifth modality is missing"

    tier_by_case = {c["case_id"]: c["tier"] for c in built["gt_cases"]}
    case_of = {r: c["case_id"] for c in built["gt_cases"] for r in c["record_ids"]}
    tiers = Counter(tier_by_case[case_of[d["record_id"]]] for d in docs)
    assert tiers["B"] > tiers["A"], (
        "documents should sit mostly in the keyless tier, where linking them requires "
        "understanding rather than a shared identifier"
    )


def test_every_document_belongs_to_a_case(built):
    planted = {r for c in built["gt_cases"] for r in c["record_ids"]}
    for doc in built["documents"]:
        assert doc["record_id"] in planted


def test_written_pdfs_are_valid_and_deterministic(gen, built, tmp_path):
    doc = built["documents"][0]
    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
    gen.write_pdf(first, doc["lines"])
    gen.write_pdf(second, doc["lines"])

    data = first.read_bytes()
    assert data.startswith(b"%PDF-1.4"), "not a PDF"
    assert data.rstrip().endswith(b"%%EOF"), "PDF is truncated"
    assert b"/Type /Catalog" in data and b"xref" in data
    assert data == second.read_bytes(), "PDF writer is not byte-deterministic"


def test_escalation_form_states_the_date_stage_1_relies_on(gen, built):
    """stg_documents parses `Date raised:` deterministically rather than trusting the LLM
    for the timestamp Stage 2's link window depends on."""
    doc = built["documents"][0]
    dated = [line for line in doc["lines"] if line.startswith("Date raised:")]
    assert len(dated) == 1
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", dated[0])


def test_pdf_text_is_latin1_representable(gen, built):
    """The base-14 Helvetica font cannot encode typographic punctuation; the writer must
    transliterate it rather than raise or silently corrupt the page."""
    for doc in built["documents"]:
        for line in doc["lines"]:
            gen._pdf_escape(line).encode("latin-1")
