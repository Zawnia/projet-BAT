from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .individual_validation import (
        DEFAULT_SEEDS,
        evaluate_dataset,
        generate_validation_dataset,
        profile_runtime,
        write_generation_outputs,
    )
except ImportError:
    from individual_validation import (
        DEFAULT_SEEDS,
        evaluate_dataset,
        generate_validation_dataset,
        profile_runtime,
        write_generation_outputs,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and evaluate synthetic individual-counting validation datasets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate DATA_DUMMY_<dataset>.TXT and truth CSV")
    add_common_generation_args(generate)

    evaluate = subparsers.add_parser("evaluate", help="Evaluate an existing DATA_DUMMY_<dataset>.TXT against its truth CSV")
    add_common_eval_args(evaluate)

    run = subparsers.add_parser("run", help="Generate then evaluate a validation dataset")
    add_common_generation_args(run)
    add_common_eval_args(run, include_dataset=False)

    profile = subparsers.add_parser("profile", help="Estimate runtime from a small generated sample")
    profile.add_argument("--dataset", choices=["dev", "test"], default="dev")
    profile.add_argument("--n-replicates", type=int, default=5)
    profile.add_argument("--tracker-module", default="src.individual_counting")

    args = parser.parse_args()
    if args.command == "generate":
        run_generate(args)
    elif args.command == "evaluate":
        run_evaluate(args)
    elif args.command == "run":
        txt_path, truth_path = run_generate(args)
        if args.input is None:
            args.input = str(txt_path)
        if args.truth is None:
            args.truth = str(truth_path)
        run_evaluate(args)
    elif args.command == "profile":
        stats = profile_runtime(args.dataset, args.n_replicates, args.tracker_module)
        print("Validation runtime profile")
        for key, value in stats.items():
            print(f"  {key}: {value:.3f}")


def add_common_generation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset", choices=["dev", "test"], default="dev")
    parser.add_argument("--n-replicates", type=int, default=100, help="Replicates per discrete case")
    parser.add_argument("--sweep-replicates", type=int, default=None, help="Replicates per sweep point; default n_replicates / 5")
    parser.add_argument("--seed", type=int, default=None, help="Override the default dev/test seed")
    parser.add_argument("--output-dir", default="data/simulated", help="Directory for DATA_DUMMY files")


def add_common_eval_args(parser: argparse.ArgumentParser, include_dataset: bool = True) -> None:
    if include_dataset:
        parser.add_argument("--dataset", choices=["dev", "test"], default="dev")
    parser.add_argument("--input", default=None, help="Input DATA_DUMMY TXT path")
    parser.add_argument("--truth", default=None, help="Truth CSV path")
    parser.add_argument("--tracker-module", default="src.individual_counting", help="Module exposing count_individuals")
    parser.add_argument("--processed-dir", default="data/processed", help="Directory for metrics CSV files")
    parser.add_argument("--plot-dir", default="plots/counting", help="Directory for validation plots")


def run_generate(args: argparse.Namespace) -> tuple[Path, Path]:
    seed = DEFAULT_SEEDS[args.dataset] if args.seed is None else args.seed
    result = generate_validation_dataset(
        dataset=args.dataset,
        n_replicates=args.n_replicates,
        seed=seed,
        sweep_replicates=args.sweep_replicates,
    )
    txt_path, truth_path = write_generation_outputs(result, args.output_dir)
    print(f"Generated dataset      : {args.dataset}")
    print(f"Seed                   : {result.seed}")
    print(f"Scenarios              : {len(result.scenarios)}")
    print(f"Sensor rows            : {len(result.rows)}")
    print(f"DATA TXT saved         : {txt_path}")
    print(f"Truth CSV saved        : {truth_path}")
    return txt_path, truth_path


def run_evaluate(args: argparse.Namespace) -> None:
    txt_path = Path(args.input) if args.input else Path("data/simulated") / f"DATA_DUMMY_{args.dataset}.TXT"
    truth_path = Path(args.truth) if args.truth else Path("data/simulated") / f"DATA_DUMMY_{args.dataset}_truth.csv"
    metrics, summary, assignments = evaluate_dataset(
        txt_path=txt_path,
        truth_path=truth_path,
        tracker_module=args.tracker_module,
        output_dir=args.processed_dir,
        plot_dir=args.plot_dir,
        dataset=args.dataset,
    )
    global_summary = next((row for row in summary if row.group == "global"), None)
    print(f"Evaluated dataset      : {args.dataset}")
    print(f"Scenario metrics       : {len(metrics)}")
    print(f"Track assignments      : {len(assignments)}")
    if global_summary:
        print(f"Global MAE             : {global_summary.mae:.3f}")
        print(f"Global exact rate      : {global_summary.exact_rate:.3f}")
        print(f"Global bias            : {global_summary.bias_mean:.3f}")
    print(f"Metrics directory      : {args.processed_dir}")
    print(f"Plots directory        : {args.plot_dir}")


if __name__ == "__main__":
    main()
