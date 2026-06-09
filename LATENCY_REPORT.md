# Stage 5 Latency Report

## Demo artifact

- HTML demo file: `agent_stage5_demo.html`
- Served by UI app at: `http://localhost:8000/agent_stage5_demo.html`
- Flow shown: UI -> Customer Agent -> Law Agent -> Tax/Compliance Agents -> Law aggregate -> Customer response

## Baseline measurement

Command:

```powershell
Measure-Command { uv run python test_client.py } | Select-Object TotalSeconds
```

Result:

```text
81.88 seconds
```

## Optimization applied

The original Customer Agent used a ReAct agent loop before delegating to the Law
Agent. For this demo, every user input is intended to be a legal question, so the
Customer Agent can skip that extra LLM planning step and delegate directly to the
Law Agent through Registry discovery + A2A.

Environment switch:

```env
CUSTOMER_FAST_DELEGATE=1
```

What remains unchanged:

- Stage 5 still uses separate HTTP services.
- Registry discovery is still used.
- Law Agent still orchestrates Tax and Compliance through A2A.
- Tax and Compliance still run as specialist agents.

## Optimized measurement

Command:

```powershell
Measure-Command { uv run python test_client.py } | Select-Object TotalSeconds
```

Result:

```text
61.42 seconds
```

## Improvement

```text
Time saved: 20.46 seconds
Latency reduction: ~25.0%
```

## Further latency reduction ideas

- Cache Agent Cards after the first request instead of fetching `/.well-known/agent.json` on every A2A call.
- Cache Registry discovery results for known task names.
- Use a faster model for routing and aggregation, while keeping stronger models for final legal synthesis.
- Stream partial events and partial answer text to the UI so users see progress earlier.
- Add short-circuit routing rules for obvious tax/compliance keywords before asking the router LLM.
