# src/main.py
"""CLI entry point for the Agentic Production Company pipeline."""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.orchestrator import Orchestrator
from src.pptx_exporter import export_pitch_deck


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="The Agentic Production Company — turn a one-line idea into a pitch deck"
    )
    parser.add_argument("brief", help="One-line show idea (e.g. 'A 3x60 doc about...')")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--output", default=None, help="Output directory for results")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("THE AGENTIC PRODUCTION COMPANY")
    print(f"{'='*60}")
    print(f"\nBrief: {args.brief}\n")

    orchestrator = Orchestrator(config_path=args.config)
    result = orchestrator.run(args.brief)

    if result.success:
        print(f"\n{'='*60}")
        print("PITCH DECK COMPLETE")
        print(f"{'='*60}\n")

        # Strip binary rendered_imagery before JSON serialization
        deck_for_json = {
            k: v for k, v in (result.pitch_deck or {}).items()
            if k != "rendered_imagery"
        }
        print(json.dumps(deck_for_json, indent=2))

        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "pitch_deck.json").write_text(
                json.dumps(deck_for_json, indent=2)
            )
            (out_dir / "evidence.json").write_text(
                json.dumps(result.evidence, indent=2)
            )
            (out_dir / "log.json").write_text(
                json.dumps(
                    [
                        entry.model_dump() if hasattr(entry, "model_dump")
                        else entry
                        for entry in result.log
                    ],
                    indent=2, default=str,
                )
            )
            # Generate PPTX
            if result.pitch_deck:
                pptx_path = export_pitch_deck(
                    result.pitch_deck, str(out_dir / "pitch_deck.pptx")
                )
                print(f"PowerPoint saved to {pptx_path}")
            print(f"\nResults saved to {out_dir}/")
    else:
        print(f"\nPipeline failed: {result.error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
