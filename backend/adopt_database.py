"""Validate an unversioned database against the frozen baseline, then stamp it."""
import importlib.util
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
import sqlalchemy as sa


def baseline_metadata():
    metadata = sa.MetaData()

    class Recorder:
        @staticmethod
        def create_table(name, *items):
            sa.Table(name, metadata, *items)

        @staticmethod
        def create_index(name, table, columns, unique=False):
            sa.Index(name, *(metadata.tables[table].c[col] for col in columns), unique=unique)

        @staticmethod
        def f(name):
            return name

    path = Path(__file__).parent / "migrations/versions/0001_baseline.py"
    spec = importlib.util.spec_from_file_location("legacy_baseline", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = Recorder
    module.upgrade()
    return metadata


def adopt(connection):
    if "alembic_version" in sa.inspect(connection).get_table_names():
        raise RuntimeError("Database already has migration metadata; use alembic current/upgrade")
    differences = compare_metadata(MigrationContext.configure(connection), baseline_metadata())
    if differences:
        # Do not include data or connection credentials in diagnostics.
        raise RuntimeError("Schema differs from revision 0001; inspect and reconcile schema before adoption")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["connection"] = connection
    command.stamp(config, "0001")


if __name__ == "__main__":
    from backend.db.session import engine
    with engine.begin() as connection:
        adopt(connection)
    print("Validated existing schema and adopted revision 0001; run alembic upgrade head next.")
