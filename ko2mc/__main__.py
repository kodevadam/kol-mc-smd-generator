"""CLI entry point for the Knight Online to Minecraft converter."""

import argparse
import os
import sys

from .converter import convert_map


def main():
    parser = argparse.ArgumentParser(
        description="Convert Knight Online .gtd/.opd map files to Minecraft worlds.",
        epilog=(
            "Examples:\n"
            "  %(prog)s moradon.gtd moradon.opd\n"
            "  %(prog)s --scale 2 --name Moradon moradon.gtd moradon.opd\n"
            "  %(prog)s --gtd-only arena.gtd\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("gtd_file", help="Path to .gtd (Game Terrain Data) file")
    parser.add_argument("opd_file", nargs="?", default=None,
                        help="Path to .opd (Object Post Data) file (optional)")
    parser.add_argument("-o", "--output", default="./output",
                        help="Output directory (default: ./output)")
    parser.add_argument("-n", "--name", default=None,
                        help="World name (default: derived from GTD filename)")
    parser.add_argument("-s", "--scale", type=int, default=1, choices=[1, 2, 4],
                        help="Blocks per KO tile: 1=compact, 2=medium, 4=full (default: 1)")
    parser.add_argument("--gtd-only", action="store_true",
                        help="Only convert terrain from GTD (ignore OPD)")

    args = parser.parse_args()

    # Validate inputs
    if not os.path.exists(args.gtd_file):
        print(f"Error: GTD file not found: {args.gtd_file}", file=sys.stderr)
        sys.exit(1)

    opd_path = None
    if not args.gtd_only and args.opd_file:
        if not os.path.exists(args.opd_file):
            print(f"Warning: OPD file not found: {args.opd_file}", file=sys.stderr)
            print("Continuing with terrain only...", file=sys.stderr)
        else:
            opd_path = args.opd_file

    # Derive world name from filename if not specified
    world_name = args.name
    if not world_name:
        world_name = os.path.splitext(os.path.basename(args.gtd_file))[0]
        # Capitalize and clean up
        world_name = world_name.replace("_", " ").title().replace(" ", "")
        world_name = f"KO_{world_name}"

    convert_map(
        gtd_path=args.gtd_file,
        opd_path=opd_path,
        output_dir=args.output,
        world_name=world_name,
        scale=args.scale,
    )


if __name__ == "__main__":
    main()
