"""Compatibility entry point: all schema changes now go through Alembic."""
from alembic import command
from alembic.config import Config
from pathlib import Path


def create_all_tables():
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        raise SystemExit("Use documented migration commands; --drop is no longer supported")
    create_all_tables()
