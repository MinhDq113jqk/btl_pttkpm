"""Alembic CLI with safe error output for a credential-bearing connection."""
import sys
from alembic.config import main

if __name__ == "__main__":
    try:
        main(argv=sys.argv[1:])
    except Exception:
        print("Migration failed; connection/error details suppressed. Check configuration and database availability.")
        sys.exit(1)
