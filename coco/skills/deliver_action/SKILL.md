---
name: deliver_action
description: Take a recommended action and deliver it — post to Slack or open a ticket via MCP — closing the loop from unstructured data to a real action.
---

# deliver_action

Close the loop: a recommendation becomes a real, delivered action.

## Input
A recommendation from `recommend_action`.

## Steps
1. Format the recommendation as a short, self-contained message: problem, impact (dollars +
   case count), owning team, the ask, and the affected `case_id`s.
2. Deliver it via an available MCP tool:
   - **Slack** — post to the owning team's channel.
   - **Ticketing** (Jira / Linear / etc.) — open a ticket assigned to the owning team, with the
     evidence in the body.
3. Confirm what was delivered and where (channel / ticket id).

## Notes
- This is the "actionable output" requirement, closed: unstructured records -> linked cases
  -> diagnosed driver -> recommendation -> a delivered action.
- If no MCP delivery target is configured, fall back to returning the formatted message and the
  Streamlit app surfaces it inline as the recommended action (same content, zero integration risk).
