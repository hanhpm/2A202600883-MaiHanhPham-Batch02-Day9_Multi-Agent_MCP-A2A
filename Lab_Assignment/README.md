# Lab Assignment - Improve Day 8 Agent With Supervisor-Workers

## Objective

Improve the Day 8 RAG agent using the **Supervisor - Workers** pattern with at
least 2-3 workers. This implementation uses 4 workers.

## Architecture

```text
User Question
    |
    v
SupervisorAgent
    |
    +--> QueryPlannerWorker
    |       - Classifies intent: legal / news / mixed / general
    |       - Creates search query variants
    |
    +--> RetrievalWorker
    |       - Calls Day 8 `src.task9_retrieval_pipeline.retrieve`
    |       - Falls back to local markdown BM25-style retrieval if needed
    |
    +--> EvidenceWorker
    |       - Deduplicates and formats top evidence chunks
    |       - Assigns source labels [S1], [S2], ...
    |
    +--> AnswerWorker
            - Generates Vietnamese answer with citations
            - Uses OpenAI if `OPENAI_API_KEY` exists
            - Falls back to extractive cited answer
```

## Files

| File | Purpose |
|---|---|
| `supervisor_workers.py` | Main Supervisor-Workers implementation |
| `run_demo.py` | CLI demo runner |
| `outputs/` | Generated JSON result after running demo |

## How to Run

From the Day 9 project folder:

```powershell
cd E:\Downloads\Lab_Handson_AI_Action\2A202600883-MaiHanhPham-Batch02-Day9_Multi-Agent_MCP-A2A
python Lab_Assignment\run_demo.py
```

Run with a custom question:

```powershell
python Lab_Assignment\run_demo.py --question "Luật phòng chống ma túy quy định gì về cai nghiện?"
```

By default the assignment is stored under Day 9 but reads the sibling Day 8
cleaned markdown corpus directly for a fast local demo. To force the full
original Day 8 Task 9 pipeline, set:

```powershell
$env:ASSIGNMENT_USE_DAY8_PIPELINE="1"
python Lab_Assignment\run_demo.py
```

The script prints:

- Final answer with citations
- Worker trace
- Per-worker latency
- Total latency
- Number of retrieved/evidence chunks

It also saves the full result to:

```text
Lab_Assignment/outputs/supervisor_workers_result.json
```

## Why This Improves Day 8

The original Day 8 pipeline is mostly linear:

```text
query -> retrieval -> reranking -> generation
```

The improved assignment separates responsibilities:

- Supervisor controls the workflow and metrics.
- Planner improves query coverage.
- Retriever focuses on recall.
- Evidence worker improves grounding and citation quality.
- Answer worker focuses on final response quality.

This makes the RAG agent easier to debug, easier to extend, and closer to a
multi-agent architecture.
