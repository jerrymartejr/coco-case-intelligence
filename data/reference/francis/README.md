# Unstructured Customer Support Dataset

Synthetic dataset for prototyping ingestion, text analytics, retrieval, and quality review workflows.

The dataset contains 40,000 total source records:

- `chat.ndjson`: 10,000 chat transcript records
- `csat.ndjson`: 10,000 customer satisfaction records
- `email.ndjson`: 10,000 email support records
- `qa_notes.ndjson`: 10,000 quality assurance audit records

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

## Suggested Use Cases

- Load unstructured text into Snowflake for search, classification, or summarization.
- Build a retrieval augmented generation prototype over mixed support content.
- Detect recurring friction points across chat, survey, JSON, and QA notes.
- Parse `raw_content` later using `PARSE_JSON` or equivalent warehouse logic.

## Data Note

All examples are synthetic and contain no real customer information.

## Regeneration

Run this from the project root:

```powershell
python scripts\generate_unstructured_customer_support_dataset.py --records-per-source 10000
```
