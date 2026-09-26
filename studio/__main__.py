"""Command-line interface for the Image Generation Studio.

Examples:
    python -m studio "a neon cityscape at night" --engine demo --aspect 16:9
    python -m studio "product photo of a ceramic mug" --engine stability --aspect 1:1
    python -m studio list-engines
    python -m studio list-aspects
"""
from __future__ import annotations

import argparse
import json
import sys

import studio  # noqa: F401  (loads .env)
from studio import payload, pipeline


def cmd_generate(args: argparse.Namespace) -> int:
    record = pipeline.run_generation(
        args.prompt, engine_name=args.engine, aspect=args.aspect,
        output_dir=args.out,
    )
    print(json.dumps(record, indent=2))
    print("\nStage log:")
    for s in record["stages"]:
        print(f"  [{s['status']:^9}] {s['stage']} — {s['detail']}")
    status = record.get("status")
    if status == "complete":
        print(f"\n✓ Image saved: {args.out}/{record['file']}")
        return 0
    print(f"\n! Finished with status: {status} — {record.get('error', '')}")
    if record.get("polite_message"):
        print(f"  {record['polite_message']}")
    return 1 if status in ("failed", "rejected") else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="studio",
        description="Multimodal Image Generation Studio — Project 3 pipeline CLI.",
    )
    sub = parser.add_subparsers(dest="command")

    g = sub.add_parser("generate", help="Run the 6-stage generation pipeline.")
    g.add_argument("prompt", help="Text prompt describing the image.")
    g.add_argument("--engine", default="demo",
                   choices=sorted(pipeline.ENGINES),
                   help="Generation engine (default: demo, works offline).")
    g.add_argument("--aspect", default="1:1", choices=sorted(payload.ASPECT_MAP),
                   help="Aspect ratio — mapped to exact pixel payloads.")
    g.add_argument("--out", default="outputs", help="Output directory.")

    sub.add_parser("list-engines", help="Show the engine matrix.")
    sub.add_parser("list-aspects", help="Show the aspect-ratio pixel map.")

    # Bare invocation: `python -m studio "prompt" ...` == generate
    args, unknown = parser.parse_known_args(argv)
    if args.command is None and unknown is None:
        pass
    if args.command is None:
        # Re-parse as generate for convenience.
        args = parser.parse_args((["generate"] + (argv or [])))

    if args.command == "list-engines":
        print(json.dumps(payload.list_engines(), indent=2))
        return 0
    if args.command == "list-aspects":
        print(json.dumps(payload.list_aspects(), indent=2))
        return 0
    return cmd_generate(args)


if __name__ == "__main__":
    sys.exit(main())
