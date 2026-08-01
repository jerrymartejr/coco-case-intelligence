"""
Upload the generated PDF escalation forms to the Snowflake stage the pipeline reads.

PDFs are binary, so unlike the other four channels they cannot be dbt seeds. They live in
an internal stage with a directory table, and `models/staging/stg_documents.sql` reads
them back with Cortex PARSE_DOCUMENT. This script is the one manual step between
generating the corpus and building the pipeline:

    python scripts/generate_synthetic_data.py
    python scripts/upload_documents.py
    dbt build --profiles-dir .

Credentials come from the same environment variables as profiles.yml. See docs/SETUP.md.
"""

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCUMENTS = REPO / "data" / "synthetic" / "documents"

REQUIRED = ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PRIVATE_KEY_PATH")


def stage_name():
    """The stage to upload into, in whichever database this run is pointed at.

    This follows SNOWFLAKE_DATABASE rather than naming a database outright. It used to be
    the literal CASE_INTEL.RAW.DOCUMENTS, which meant pointing the rest of the project at
    a second database still sent the PDFs here -- and since the upload clears the stage
    first, running it against a scratch database would have emptied and rewritten the
    real one.

    The database is an SQL identifier and cannot be a bind parameter, so it is validated
    against a strict pattern instead.
    """
    database = os.environ.get("SNOWFLAKE_DATABASE", "CASE_INTEL")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", database):
        sys.exit(f"SNOWFLAKE_DATABASE is not a valid Snowflake identifier: {database!r}")
    return f"{database}.RAW.DOCUMENTS"


def _connect():
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    missing = [v for v in REQUIRED if not os.environ.get(v)]
    if missing:
        sys.exit(
            f"Missing environment variables: {', '.join(missing)}.\n"
            "Copy .env.example to .env, fill it in, and `source .env`. See docs/SETUP.md."
        )

    key_path = Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]).expanduser()
    with key_path.open("rb") as fh:
        key = serialization.load_pem_private_key(fh.read(), password=None)
    der = key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=der,
        role=os.environ.get("SNOWFLAKE_ROLE", "CASE_INTEL_ROLE"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "CASE_INTEL"),
        schema="RAW",
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
    )


def main():
    pdfs = sorted(DOCUMENTS.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"No PDFs in {DOCUMENTS}. Run scripts/generate_synthetic_data.py first.")

    stage = stage_name()
    con = _connect()
    cur = con.cursor()

    # Server-side encryption, not client-side: PARSE_DOCUMENT cannot read a stage whose
    # files are encrypted with a client-side key.
    cur.execute(
        f"create stage if not exists {stage} "
        "directory = (enable = true) encryption = (type = 'SNOWFLAKE_SSE')"
    )

    # Clear first so a regenerated corpus never leaves orphaned documents behind that
    # would show up as extra, unscored records.
    cur.execute(f"remove @{stage}")

    for pdf in pdfs:
        cur.execute(f"put file://{pdf} @{stage} auto_compress=false overwrite=true")

    cur.execute(f"alter stage {stage} refresh")
    cur.execute(f"select count(*) from directory(@{stage})")
    staged = cur.fetchone()[0]

    print(f"uploaded {len(pdfs)} PDFs to @{stage}; directory table reports {staged}")
    if staged != len(pdfs):
        sys.exit(f"stage holds {staged} files but {len(pdfs)} were uploaded")

    con.close()


if __name__ == "__main__":
    main()
