from __future__ import annotations

import pandas as pd
import streamlit as st

from ingest import ingest_file, preview_file, supported_import_files, unique_destination
from paths import TO_IMPORT_DIR, ensure_project_dirs
from ui.components import display_import_preview, display_table


def render_imports(import_log: pd.DataFrame) -> None:
    st.title("Imports")
    st.caption("Add CSV/PDF statements, preview totals, then import into the local DuckDB file.")
    ensure_project_dirs()

    uploaded_files = st.file_uploader(
        "Statement Files",
        type=["csv", "pdf"],
        accept_multiple_files=True,
        help="Files are saved locally to imports/to_import before import.",
    )
    if st.button("Add Files", disabled=not uploaded_files):
        saved_names = []
        for uploaded_file in uploaded_files:
            destination = unique_destination(TO_IMPORT_DIR, uploaded_file.name)
            destination.write_bytes(uploaded_file.getbuffer())
            saved_names.append(destination.name)
        st.success(f"Added {len(saved_names)} file(s) to imports/to_import.")
        st.rerun()

    pending_files = supported_import_files(TO_IMPORT_DIR)
    st.subheader("Pending Files")
    if pending_files:
        display_table(
            pd.DataFrame(
                [
                    {
                        "file": path.name,
                        "type": path.suffix.lower().lstrip("."),
                        "size_kb": round(path.stat().st_size / 1024, 1),
                    }
                    for path in pending_files
                ]
            )
        )

        col1, col2 = st.columns(2)
        if col1.button("Preview Pending Files"):
            previews = []
            errors = []
            for path in pending_files:
                try:
                    previews.append(preview_file(path).__dict__)
                except Exception as exc:
                    errors.append({"file": path.name, "error": str(exc)})
            if previews:
                display_table(pd.DataFrame([display_import_preview(preview) for preview in previews]))
            if errors:
                st.error("Some files could not be previewed.")
                display_table(pd.DataFrame(errors))

        if col2.button("Import Pending Files"):
            results = [ingest_file(path) for path in pending_files]
            display_table(pd.DataFrame(results))
            st.cache_data.clear()
            st.success("Import finished.")
    else:
        st.info("No pending files. Upload statements above or place them in imports/to_import.")

    st.subheader("Import History")
    if import_log.empty:
        st.info("No imports yet on this local install.")
    else:
        display_table(import_log)

