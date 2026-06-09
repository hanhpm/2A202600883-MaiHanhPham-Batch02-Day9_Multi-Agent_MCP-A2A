"""Run the Supervisor-Workers Day 8 RAG assignment demo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from supervisor_workers import SupervisorAgent, save_result


DEFAULT_QUESTION = (
    "Hình phạt cho hành vi tàng trữ trái phép chất ma túy là gì? "
    "Có tin tức nghệ sĩ liên quan đến ma túy nào trong dữ liệu không?"
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Supervisor-Workers RAG demo")
    parser.add_argument("--question", "-q", default=DEFAULT_QUESTION, help="User question")
    parser.add_argument(
        "--output",
        "-o",
        default="Lab_Assignment/outputs/supervisor_workers_result.json",
        help="Path to save JSON result",
    )
    args = parser.parse_args()

    agent = SupervisorAgent()
    result = agent.run(args.question)

    print("=" * 72)
    print("SUPERVISOR - WORKERS RAG ANSWER")
    print("=" * 72)
    print(result["answer"])
    print()
    print("Trace:")
    for step in result["trace"]:
        latency = step.get("latency_ms", "-")
        print(
            f"- {step['worker']}: {step['status']} | "
            f"{step['detail']} | {latency} ms"
        )
    print()
    print("Metrics:", result["metrics"])

    output_path = Path(args.output)
    save_result(result, output_path)
    print(f"\nSaved result to: {output_path}")


if __name__ == "__main__":
    main()
