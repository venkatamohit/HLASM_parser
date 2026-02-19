"""Allow ``python -m hlasm_parser`` invocation."""
import sys
from .cli import main

sys.exit(main())
