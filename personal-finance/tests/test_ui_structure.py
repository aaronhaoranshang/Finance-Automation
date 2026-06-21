from __future__ import annotations

import importlib


def test_streamlit_app_entrypoint_and_page_modules_import(app_modules):
    app = importlib.import_module("app")
    assert callable(app.main)

    page_modules = [
        "ui.pages.audit",
        "ui.pages.category_breakdown",
        "ui.pages.drilldown",
        "ui.pages.imports",
        "ui.pages.merchant_rules",
        "ui.pages.merchants",
        "ui.pages.monthly_detail",
        "ui.pages.overview",
        "ui.pages.recurring",
        "ui.pages.review_queue",
        "ui.pages.settings",
        "ui.pages.setup",
        "ui.pages.transactions",
    ]
    for module_name in page_modules:
        module = importlib.import_module(module_name)
        assert module

    audit = importlib.import_module("ui.pages.audit")
    assert callable(audit.connect)
