CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions (transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions (account_name);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions (transaction_type);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions (category, subcategory);
CREATE INDEX IF NOT EXISTS idx_transactions_source_file ON transactions (source_file);

CREATE INDEX IF NOT EXISTS idx_merchant_rule_pattern ON merchant_rule (pattern);
CREATE INDEX IF NOT EXISTS idx_merchant_rule_enabled_priority ON merchant_rule (enabled, priority);
CREATE INDEX IF NOT EXISTS idx_merchant_rule_owner ON merchant_rule (owner_type);

CREATE INDEX IF NOT EXISTS idx_category_master_category ON category_master (category);
CREATE INDEX IF NOT EXISTS idx_category_master_enabled ON category_master (enabled);
CREATE INDEX IF NOT EXISTS idx_category_master_owner ON category_master (owner_type);

CREATE INDEX IF NOT EXISTS idx_import_batch_source_file ON import_batch (source_file);
CREATE INDEX IF NOT EXISTS idx_import_batch_status ON import_batch (status);
CREATE INDEX IF NOT EXISTS idx_import_batch_imported_at ON import_batch (imported_at);

CREATE INDEX IF NOT EXISTS idx_raw_import_row_batch ON raw_import_row (import_batch_id);
CREATE INDEX IF NOT EXISTS idx_raw_import_row_hash ON raw_import_row (row_hash);
CREATE INDEX IF NOT EXISTS idx_raw_import_row_transaction ON raw_import_row (normalized_transaction_id);
