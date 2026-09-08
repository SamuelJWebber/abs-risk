"""Command line entry point.

    absrisk version
    absrisk autos fetch|build ...        (src/absrisk/autos, tasks B1 and B2)
    absrisk cards fetch|parse|composition (src/absrisk/cards, tasks A1 and A2)
    absrisk analyze autos [...]          (src/absrisk/estimate/run_autos.py)
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "version":
        from . import __version__

        print(__version__)
        return 0
    if cmd == "autos":
        from .autos import main as autos_main

        return autos_main(rest)
    if cmd == "cards":
        from .cards import main as cards_main

        return cards_main(rest)
    if cmd == "analyze":
        if rest and rest[0] == "autos":
            from .estimate.run_autos import main as run_autos

            return run_autos(rest[1:])
        if rest and rest[0] == "cards":
            from .estimate.run_cards import main as run_cards

            return run_cards(rest[1:])
        print("analyze: expected 'autos' or 'cards'", file=sys.stderr)
        return 2
    if cmd == "report":
        if rest and rest[0] == "autos":
            from .report.autos_page import main as report_autos

            return report_autos(rest[1:])
        if rest and rest[0] == "cards":
            from .report.cards_page import main as report_cards

            return report_cards(rest[1:])
        print("report: expected 'autos' or 'cards'", file=sys.stderr)
        return 2
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
