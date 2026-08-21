"""Enable ``python -m harness.cli``."""

import sys

from harness.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
