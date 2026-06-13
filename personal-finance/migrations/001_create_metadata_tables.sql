CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS transaction_type_master (
    transaction_type TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    affects_spend BOOLEAN NOT NULL,
    affects_income BOOLEAN NOT NULL,
    affects_cash_flow BOOLEAN NOT NULL,
    requires_category BOOLEAN NOT NULL DEFAULT FALSE,
    default_scope TEXT,
    sort_order INTEGER DEFAULT 100,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS category_master (
    category_id INTEGER PRIMARY KEY,
    category TEXT NOT NULL,
    subcategory TEXT NOT NULL,
    owner_type TEXT NOT NULL DEFAULT 'system',
    enabled BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 100,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp,
    UNIQUE(category, subcategory, owner_type)
);

CREATE TABLE IF NOT EXISTS merchant_rule (
    rule_id INTEGER PRIMARY KEY,
    owner_type TEXT NOT NULL DEFAULT 'system',
    pattern TEXT NOT NULL,
    match_type TEXT NOT NULL,
    merchant_clean TEXT,
    transaction_type TEXT,
    scope TEXT,
    category TEXT,
    subcategory TEXT,
    priority INTEGER DEFAULT 100,
    enabled BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS source_profile (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    institution TEXT,
    account_type TEXT,
    file_type TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 100,
    created_at TIMESTAMP DEFAULT current_timestamp,
    updated_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS source_detection_rule (
    rule_id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL,
    required_columns TEXT NOT NULL,
    optional_columns TEXT,
    filename_pattern TEXT,
    header_pattern TEXT,
    priority INTEGER DEFAULT 100,
    enabled BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS source_column_mapping (
    mapping_id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_column TEXT NOT NULL,
    target_column TEXT NOT NULL,
    required BOOLEAN DEFAULT TRUE,
    transform_rule TEXT,
    sort_order INTEGER DEFAULT 100,
    enabled BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS import_batch (
    import_batch_id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    file_hash TEXT,
    source_id TEXT,
    status TEXT NOT NULL,
    rows_seen INTEGER DEFAULT 0,
    rows_inserted INTEGER DEFAULT 0,
    rows_duplicate INTEGER DEFAULT 0,
    rows_failed INTEGER DEFAULT 0,
    imported_at TIMESTAMP DEFAULT current_timestamp,
    message TEXT
);

CREATE TABLE IF NOT EXISTS raw_import_row (
    import_batch_id TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    source_id TEXT,
    raw_data TEXT,
    row_hash TEXT,
    normalized_transaction_id TEXT,
    status TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY(import_batch_id, row_number)
);

CREATE TABLE IF NOT EXISTS transaction_classification_audit (
    audit_id INTEGER PRIMARY KEY,
    transaction_id TEXT,
    rule_id INTEGER,
    rule_owner_type TEXT,
    matched_pattern TEXT,
    old_transaction_type TEXT,
    new_transaction_type TEXT,
    old_category TEXT,
    new_category TEXT,
    old_subcategory TEXT,
    new_subcategory TEXT,
    reason TEXT,
    applied_at TIMESTAMP DEFAULT current_timestamp
);
