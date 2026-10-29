"""Alembic CLI with safe error output for a credential-bearing connection."""
import sys
from alembic.config import main

if __name__ == "__main__":
    try:
        main(argv=sys.argv[1:])
    except Exception as exc:
        import os
        if os.getenv('GREENCITY_ISOLATED_SECURITY_TESTS') == '1':
            original = getattr(exc, 'orig', None)
            diagnostic = getattr(original, 'diag', None)
            # PostgreSQL identifiers and SQLSTATE only; never connection/parameters.
            print('Migration diagnostic:', type(exc).__name__, getattr(original, 'sqlstate', None), getattr(diagnostic, 'constraint_name', None), getattr(diagnostic, 'table_name', None))
        print("Migration failed; connection/error details suppressed. Check configuration and database availability.")
        sys.exit(1)
