"""`python -m absrisk.cards ...` entry point."""

import sys

from . import main

sys.exit(main(sys.argv[1:]))
