from __future__ import annotations

from pathlib import Path

from backup import export_backup, restore_backup
from paths import DB_PATH


def create_database_backup() -> Path:
    return export_backup(DB_PATH)


def restore_database_backup(buffer: bytes) -> None:
    restore_backup(bytes(buffer), DB_PATH)


def database_exists() -> bool:
    return DB_PATH.exists()

