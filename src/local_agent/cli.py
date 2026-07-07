from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_env_files
from .model import make_provider
from .runtime import AgentRuntime
from .token_budget import TokenBudget


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent", description="Run a small local CLI agent.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run an agent task")
    run.add_argument("--task", required=True, help="task for the agent")
    run.add_argument("--workspace", required=True, help="workspace directory")
    run.add_argument("--trace", required=True, help="trace JSON output path")
    run.add_argument("--model-provider", default="mock", choices=["mock", "openai-compatible", "deepseek"])
    run.add_argument("--max-steps", type=int, default=10)
    run.add_argument("--token-budget", type=int, default=8000)
    run.add_argument("--compression-threshold", type=float, default=0.70)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        load_env_files()
        provider = make_provider(args.model_provider)
        runtime = AgentRuntime(
            provider,
            Path(args.workspace),
            Path(args.trace),
            max_steps=args.max_steps,
            budget=TokenBudget(args.token_budget, args.compression_threshold),
        )
        state = runtime.run(args.task)
        print(f"terminal_reason={state.terminal_reason}")
        if state.final_answer:
            print(state.final_answer)
        print(f"trace={Path(args.trace).resolve()}")
        return 0 if state.terminal_reason == "final_response" else 1
    return 2
