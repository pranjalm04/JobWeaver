from __future__ import annotations

import argparse

from physicianx.worker.tasks import crawl_seed, run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(prog="physicianx")
    sub = parser.add_subparsers(dest="command", required=True)

    enqueue = sub.add_parser("enqueue-seed", help="Enqueue a single seed crawl")
    enqueue.add_argument("--seed-url", required=True, help="Seed careers/jobs URL")

    sub.add_parser("run-pipeline", help="Run pipeline for configured seeds")

    args = parser.parse_args()
    if args.command == "enqueue-seed":
        result = crawl_seed.delay(args.seed_url)
        print(f"Enqueued crawl_seed task_id={result.id} seed={args.seed_url}")
    elif args.command == "run-pipeline":
        result = run_pipeline.delay()
        print(f"Enqueued run_pipeline task_id={result.id}")

