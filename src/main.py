# src/main.py
"""CLI entry point for the Multi-Agent Orchestration Framework."""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.core.pipeline import discover_pipelines, create_pipeline


def main():
    load_dotenv()

    # Discover available pipelines for help text
    available = discover_pipelines()
    pipeline_ids = list(available.keys())
    pipeline_list = "\n".join(
        f"  {pid:20s} {defn.name} — {defn.description[:60]}"
        for pid, defn in available.items()
    )

    parser = argparse.ArgumentParser(
        description="Multi-Agent Orchestration Framework — run any pipeline from the CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available pipelines:\n{pipeline_list}" if pipeline_list else None,
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="",
        help="Input text for the pipeline (e.g. a brief, topic, or idea)",
    )
    parser.add_argument(
        "--pipeline", "-p",
        default=None,
        choices=pipeline_ids or None,
        help="Pipeline to run (default: interactive selection)",
    )
    parser.add_argument(
        "--config", default="config.yaml", help="Path to global config file",
    )
    parser.add_argument(
        "--output", "-o", default=None, help="Output directory for results",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_pipelines",
        help="List all available pipelines and exit",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode with fixture data (TV Production only, no API calls)",
    )
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("MULTI-AGENT ORCHESTRATION FRAMEWORK")
    print(f"{'='*60}")

    # -- List mode --
    if args.list_pipelines:
        print(f"\nAvailable pipelines ({len(available)}):\n")
        for pid, defn in available.items():
            print(f"  {pid}")
            print(f"    {defn.name} ({defn.category})")
            print(f"    {defn.description}")
            print(f"    Agents: {', '.join(a.get('role', k) for k, a in defn.agents.items())}")
            print(f"    Steps: {len(defn.steps)}")
            print()
        return

    # -- Demo mode (TV Production only, backward compat) --
    if args.demo:
        print("\n[DEMO MODE] Using fixture data — no API calls.\n")
        from src.demo_data import get_demo_result
        from src.pptx_exporter import export_pitch_deck
        demo = get_demo_result()
        print(json.dumps(demo["pitch_deck"], indent=2))

        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "pitch_deck.json").write_text(
                json.dumps(demo["pitch_deck"], indent=2)
            )
            (out_dir / "evidence.json").write_text(
                json.dumps(demo["evidence"], indent=2)
            )
            if demo["pitch_deck"]:
                pptx_path = export_pitch_deck(
                    demo["pitch_deck"],
                    str(out_dir / "pitch_deck.pptx"),
                )
                print(f"PowerPoint saved to {pptx_path}")
            print(f"\nResults saved to {out_dir}/")
        return

    # -- Pipeline selection --
    if not available:
        print("\nNo pipelines found. Check src/pipelines/ directory.", file=sys.stderr)
        sys.exit(1)

    pipeline_id = args.pipeline
    if not pipeline_id:
        # Interactive selection
        print(f"\nSelect a pipeline:\n")
        for i, (pid, defn) in enumerate(available.items(), 1):
            print(f"  [{i}] {defn.name} — {defn.description[:60]}")
        print()
        try:
            choice = input("Enter number or pipeline ID: ").strip()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(pipeline_ids):
                    pipeline_id = pipeline_ids[idx]
                else:
                    print("Invalid selection.", file=sys.stderr)
                    sys.exit(1)
            elif choice in available:
                pipeline_id = choice
            else:
                print(f"Unknown pipeline: {choice}", file=sys.stderr)
                sys.exit(1)
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(0)

    defn = available[pipeline_id]
    print(f"\nPipeline: {defn.name}")
    print(f"Category: {defn.category}")
    print(f"Steps: {len(defn.steps)}\n")

    # -- Input --
    input_text = args.input
    if not input_text:
        try:
            input_text = input(f"{defn.input_config.label}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(0)
    if not input_text:
        print("No input provided.", file=sys.stderr)
        sys.exit(1)

    print(f"\nInput: {input_text}\n")

    # -- Run pipeline --
    pipeline = create_pipeline(pipeline_id, global_config_path=args.config)
    result = pipeline.run(input_text)

    if result.success:
        print(f"\n{'='*60}")
        print(f"{defn.name.upper()} COMPLETE")
        print(f"{'='*60}\n")

        # Strip binary data before JSON serialization
        output_for_json = {
            k: v for k, v in (result.output or {}).items()
            if k != "rendered_imagery"
        } if result.output else None

        print(json.dumps(output_for_json, indent=2))

        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "output.json").write_text(
                json.dumps(output_for_json, indent=2)
            )
            if result.evidence:
                (out_dir / "evidence.json").write_text(
                    json.dumps(result.evidence, indent=2)
                )
            (out_dir / "log.json").write_text(
                json.dumps(result.log, indent=2, default=str)
            )
            # TV Production: generate PPTX if available
            if pipeline_id == "tv_production" and result.output:
                try:
                    from src.pptx_exporter import export_pitch_deck
                    pptx_path = export_pitch_deck(
                        result.output, str(out_dir / "pitch_deck.pptx")
                    )
                    print(f"PowerPoint saved to {pptx_path}")
                except Exception:
                    pass
            print(f"\nResults saved to {out_dir}/")
    else:
        print(f"\nPipeline failed: {result.error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
