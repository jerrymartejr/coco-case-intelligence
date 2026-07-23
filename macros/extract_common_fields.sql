{#
  Stage 1 normalize. One Cortex AI_COMPLETE call turns a raw support record (any
  format) into a JSON object with the common schema. Prompt-based structured output
  is more controllable than AI_AGG for multi-field extraction (per the CoCo review),
  and we defensively strip code fences before TRY_PARSE_JSON so a stray ```json wrapper
  does not null the row.

  Returns a VARIANT. Downstream models read ex:field::type.
#}
{% macro extract_common_fields(raw_col, model='mistral-large2') %}
  try_parse_json(
    regexp_replace(
      ai_complete('{{ model }}',
        'You normalize a customer-support record into structured fields. '
        || 'Return ONLY a JSON object (no prose, no markdown, no code fences) with EXACTLY these keys: '
        || 'customer_name, customer_email, order_ref, occurred_ts, agent_id, issue_text, resolution_text, sentiment. '
        || 'Rules: use null when a field is absent from the record; never invent an email or order reference; '
        || 'occurred_ts as YYYY-MM-DD HH:MM:SS if present else null; '
        || 'sentiment must be exactly one of: negative, neutral, positive; '
        || 'issue_text = a short normalized description of the underlying problem; '
        || 'resolution_text = how it was resolved, or null if unresolved/unknown. '
        || 'Record follows:' || chr(10) || {{ raw_col }}
      ),
      '```json|```', ''
    )
  )
{% endmacro %}
