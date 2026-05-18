from __future__ import annotations

import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from ingest import ingest_file
from paths import TO_IMPORT_DIR, ensure_project_dirs


class CsvImportHandler(FileSystemEventHandler):
    def on_created(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".csv":
            return
        wait_until_ready(path)
        result = ingest_file(path)
        if result["status"] == "processed":
            print(f"Processed {result['file']}: {result['rows_inserted']}/{result['rows_seen']} new rows.")
        else:
            print(f"Failed {result['file']}: {result.get('error', 'unknown error')}")


def wait_until_ready(path: Path, timeout_seconds: int = 30) -> None:
    last_size = -1
    stable_checks = 0
    start = time.time()
    while time.time() - start < timeout_seconds:
        if not path.exists():
            time.sleep(0.5)
            continue
        current_size = path.stat().st_size
        if current_size == last_size:
            stable_checks += 1
            if stable_checks >= 2:
                return
        else:
            stable_checks = 0
            last_size = current_size
        time.sleep(0.5)


def main() -> None:
    ensure_project_dirs()
    observer = Observer()
    observer.schedule(CsvImportHandler(), str(TO_IMPORT_DIR), recursive=False)
    observer.start()
    print(f"Watching {TO_IMPORT_DIR} for CSV files. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
