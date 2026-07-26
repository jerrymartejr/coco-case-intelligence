# Unstructured Customer Support Dataset

Synthetic dataset for prototyping ingestion, text analytics, retrieval, and quality review workflows.

The dataset contains 500 total source records:

- `chat.ndjson`: 125 chat transcript records
- `csat.ndjson`: 125 customer satisfaction records
- `email.ndjson`: 125 email support records
- `qa_notes.ndjson`: 125 quality assurance audit records

## Files

- `chat.ndjson`
- `csat.ndjson`
- `email.ndjson`
- `qa_notes.ndjson`

## Row Format

Each line follows this format:

```json
{"record_id": "chat_00001", "received_ts": "2026-08-04 06:21:00", "raw_content": "{\"session_id\": \"chat_00001\", \"channel\": \"chat\", \"started_at\": \"2026-08-04 06:21:00\"}"}
```

The `raw_content` value is a JSON string. This mirrors raw ingestion patterns where the first load captures the source payload as text before downstream parsing.

## Link Ground Truth

Every `raw_content` payload includes `case_id`. This is the true case label for scoring linkage quality. It should be stripped from model or matching inputs before Stage 2 record linking, otherwise linking becomes a direct keyed join.

The visible linkage clues are intentionally limited to fields such as customer name, customer email, order reference, timestamps, product area, and issue text. QA notes include customer name, customer email, and order reference so they remain linkable after `case_id` is hidden.

## Suggested Use Cases

- Load unstructured text into Snowflake for search, classification, or summarization.
- Build a retrieval augmented generation prototype over mixed support content.
- Detect recurring friction points across chat, survey, JSON, and QA notes.
- Parse `raw_content` later using `PARSE_JSON` or equivalent warehouse logic.
- Score Stage 2 record linking against the hidden `case_id` labels.

## Data Note

All examples are synthetic and contain no real customer information.

## Regeneration

Run this from the project root:

```powershell
python scripts\generate_unstructured_customer_support_dataset.py --records-per-source 125 --output-dir data\unstructured_customer_support_demo
```

For a 500-record demo set, use 125 records per source:

```powershell
python scripts\generate_unstructured_customer_support_dataset.py --records-per-source 125 --output-dir data\unstructured_customer_support_demo
```
