INSERT INTO source_profile (
    source_id,
    source_name,
    institution,
    account_type,
    file_type,
    account_name,
    account_name_template,
    processed_file_label,
    processed_file_label_template,
    currency,
    amount_multiplier,
    default_scope,
    account_aliases,
    priority
)
VALUES
    ('triangle_pdf', 'Triangle PDF Statement', 'Triangle', 'credit_card', 'pdf', 'Triangle Mastercard', '', 'Triangle', '', 'CAD', 1, 'personal', '{}', 10),
    ('triangle_accountactivity', 'Triangle Account Activity', 'Triangle', 'credit_card', 'csv', 'Triangle Mastercard', '', 'Triangle', '', 'CAD', 1, 'personal', '{}', 20),
    ('mbna_9426', 'MBNA Credit Card', 'MBNA', 'credit_card', 'csv', 'MBNA Credit Card', '', 'MBNA', '', 'CAD', -1, 'personal', '{}', 30),
    ('rbc_chequing', 'RBC Chequing', 'RBC', 'chequing', 'csv', '', '{account_alias}', '', '{account_alias}', 'CAD', -1, 'personal', '{}', 40),
    ('rbc_credit_card', 'RBC Credit Card', 'RBC', 'credit_card', 'csv', '', '{account_alias}', '', '{account_alias}', 'CAD', -1, 'personal', '{}', 50),
    ('scotia_3128', 'Scotia Credit Card', 'Scotiabank', 'credit_card', 'csv', 'Scotia Credit Card', '', 'Scotiabank', '', 'CAD', 1, 'personal', '{}', 60),
    ('scotia_preferred_package', 'Scotia Preferred Package', 'Scotiabank', 'bank_account', 'csv', 'Scotiabank Bank Account', '', 'Scotiabank Preferred Package', '', 'CAD', -1, 'personal', '{}', 70),
    ('amex', 'Amex', 'Amex', 'credit_card', 'csv', '', '', '', '', 'CAD', 1, 'personal', '{}', 80),
    ('rbc', 'RBC Generic', 'RBC', 'account', 'csv', '', '{account_alias}', '', '{account_alias}', 'CAD', -1, 'personal', '{}', 900),
    ('pc_financial', 'PC Financial', 'PC Financial', 'account', 'csv', 'PC Financial', '', '', '', 'CAD', 1, 'personal', '{}', 100),
    ('triangle', 'Triangle Generic', 'Triangle', 'credit_card', 'csv', 'Triangle Mastercard', '', '', '', 'CAD', 1, 'personal', '{}', 950)
ON CONFLICT (source_id) DO NOTHING;

WITH detection(source_id, required_columns, optional_columns, filename_pattern, header_pattern, column_value_rules, priority, sort_key) AS (
    VALUES
        ('triangle_pdf', '["Transaction Date","Posting Date","Transaction Description","Amount"]', '', 'triangle', '', '{}', 10, 1),
        ('triangle_accountactivity', '["Transaction Date","Description","Debit","Credit"]', '', '', '', '{}', 20, 2),
        ('mbna_9426', '["Posted Date","Payee","Amount"]', '', '', '', '{}', 30, 3),
        ('rbc_chequing', '["Account Type","Account Number","Transaction Date","Description 1","CAD$"]', '', '', '', '{"Account Type":["Chequing"]}', 40, 4),
        ('rbc_credit_card', '["Account Type","Account Number","Transaction Date","Description 1","CAD$"]', '', '', '', '{"Account Type":["Visa"]}', 50, 5),
        ('scotia_3128', '["Filter","Date","Description","Type of Transaction","Amount"]', '', 'scotia', '', '{}', 60, 6),
        ('scotia_preferred_package', '["Filter","Date","Description","Type of Transaction","Amount","Balance"]', '', 'preferred[ _]?package|preferred package', '', '{}', 55, 7),
        ('amex', '["Transaction Date","Cardmember"]', '', '', '', '{}', 80, 8),
        ('rbc', '["Account Type","Transaction Date"]', '["Description","Description 1"]', '', '', '{}', 900, 9),
        ('pc_financial', '["Transaction Description"]', '', '', '', '{}', 100, 10),
        ('triangle', '', '["Transaction Description","Description"]', 'triangle|canadian_tire|ctfs', '', '{}', 950, 11)
),
new_detection AS (
    SELECT
        (SELECT COALESCE(max(rule_id), 0) FROM source_detection_rule)
            + row_number() OVER (ORDER BY sort_key) AS rule_id,
        *
    FROM detection
    WHERE NOT EXISTS (
        SELECT 1
        FROM source_detection_rule
        WHERE source_id = detection.source_id
    )
)
INSERT INTO source_detection_rule (
    rule_id,
    source_id,
    required_columns,
    optional_columns,
    filename_pattern,
    header_pattern,
    column_value_rules,
    priority
)
SELECT
    rule_id,
    source_id,
    required_columns,
    optional_columns,
    filename_pattern,
    header_pattern,
    column_value_rules,
    priority
FROM new_detection;

WITH mapping(source_id, source_column, target_column, required, transform_rule, sort_order, sort_key) AS (
    VALUES
        ('triangle_pdf', 'Transaction Date', 'transaction_date', TRUE, 'parse_date', 10, 1),
        ('triangle_pdf', 'Posting Date', 'posted_date', TRUE, 'parse_date', 20, 2),
        ('triangle_pdf', 'Transaction Description', 'merchant_raw', TRUE, 'clean_text', 30, 3),
        ('triangle_pdf', 'Amount', 'amount', TRUE, 'parse_amount', 40, 4),

        ('triangle_accountactivity', 'Transaction Date', 'transaction_date', TRUE, 'parse_date', 10, 5),
        ('triangle_accountactivity', 'Transaction Date', 'posted_date', TRUE, 'parse_date', 20, 6),
        ('triangle_accountactivity', 'Description', 'merchant_raw', TRUE, 'clean_text', 30, 7),
        ('triangle_accountactivity', 'Debit', 'debit_amount', FALSE, 'parse_amount', 40, 8),
        ('triangle_accountactivity', 'Credit', 'credit_amount', FALSE, 'parse_amount', 50, 9),

        ('mbna_9426', 'Posted Date', 'transaction_date', TRUE, 'parse_date', 10, 10),
        ('mbna_9426', 'Posted Date', 'posted_date', TRUE, 'parse_date', 20, 11),
        ('mbna_9426', 'Payee', 'merchant_raw', TRUE, 'clean_text', 30, 12),
        ('mbna_9426', 'Amount', 'amount', TRUE, 'parse_amount', 40, 13),

        ('rbc_chequing', 'Transaction Date', 'transaction_date', TRUE, 'parse_date', 10, 14),
        ('rbc_chequing', 'Transaction Date', 'posted_date', TRUE, 'parse_date', 20, 15),
        ('rbc_chequing', 'Description 1', 'merchant_raw', TRUE, 'clean_text', 30, 16),
        ('rbc_chequing', 'Description 2', 'merchant_raw', FALSE, 'clean_text', 40, 17),
        ('rbc_chequing', 'CAD$', 'amount', TRUE, 'parse_amount', 50, 18),
        ('rbc_chequing', 'USD$', 'amount', FALSE, 'parse_amount', 60, 19),
        ('rbc_chequing', 'Account Type', 'account_type', TRUE, 'clean_text', 70, 20),
        ('rbc_chequing', 'Account Number', 'account_number', TRUE, 'clean_text', 80, 21),

        ('rbc_credit_card', 'Transaction Date', 'transaction_date', TRUE, 'parse_date', 10, 22),
        ('rbc_credit_card', 'Transaction Date', 'posted_date', TRUE, 'parse_date', 20, 23),
        ('rbc_credit_card', 'Description 1', 'merchant_raw', TRUE, 'clean_text', 30, 24),
        ('rbc_credit_card', 'Description 2', 'merchant_raw', FALSE, 'clean_text', 40, 25),
        ('rbc_credit_card', 'CAD$', 'amount', TRUE, 'parse_amount', 50, 26),
        ('rbc_credit_card', 'USD$', 'amount', FALSE, 'parse_amount', 60, 27),
        ('rbc_credit_card', 'Account Type', 'account_type', TRUE, 'clean_text', 70, 28),
        ('rbc_credit_card', 'Account Number', 'account_number', TRUE, 'clean_text', 80, 29),

        ('scotia_3128', 'Date', 'transaction_date', TRUE, 'parse_date', 10, 30),
        ('scotia_3128', 'Date', 'posted_date', TRUE, 'parse_date', 20, 31),
        ('scotia_3128', 'Description', 'merchant_raw', TRUE, 'clean_text', 30, 32),
        ('scotia_3128', 'Sub-description', 'merchant_raw', FALSE, 'clean_text', 40, 33),
        ('scotia_3128', 'Amount', 'amount', TRUE, 'parse_amount', 50, 34),

        ('scotia_preferred_package', 'Date', 'transaction_date', TRUE, 'parse_date', 10, 35),
        ('scotia_preferred_package', 'Date', 'posted_date', TRUE, 'parse_date', 20, 36),
        ('scotia_preferred_package', 'Description', 'merchant_raw', TRUE, 'clean_text', 30, 37),
        ('scotia_preferred_package', 'Sub-description', 'merchant_raw', FALSE, 'clean_text', 40, 38),
        ('scotia_preferred_package', 'Amount', 'amount', TRUE, 'parse_amount', 50, 39),

        ('amex', 'Transaction Date', 'transaction_date', TRUE, 'parse_date', 10, 40),
        ('amex', 'Date Processed', 'posted_date', FALSE, 'parse_date', 20, 41),
        ('amex', 'Description', 'merchant_raw', TRUE, 'clean_text', 30, 42),
        ('amex', 'Amount', 'amount', TRUE, 'parse_amount', 40, 43),
        ('amex', 'Cardmember', 'account_name', TRUE, 'clean_text', 50, 44),

        ('rbc', 'Transaction Date', 'transaction_date', TRUE, 'parse_date', 10, 45),
        ('rbc', 'Posted Date', 'posted_date', FALSE, 'parse_date', 20, 46),
        ('rbc', 'Transaction Date', 'posted_date', FALSE, 'parse_date', 30, 47),
        ('rbc', 'Description', 'merchant_raw', FALSE, 'clean_text', 40, 48),
        ('rbc', 'Description 1', 'merchant_raw', FALSE, 'clean_text', 50, 49),
        ('rbc', 'Description 2', 'merchant_raw', FALSE, 'clean_text', 60, 50),
        ('rbc', 'Amount', 'amount', FALSE, 'parse_amount', 70, 51),
        ('rbc', 'CAD$', 'amount', FALSE, 'parse_amount', 80, 52),
        ('rbc', 'USD$', 'amount', FALSE, 'parse_amount', 90, 53),
        ('rbc', 'Account Type', 'account_type', FALSE, 'clean_text', 100, 54),
        ('rbc', 'Account Number', 'account_number', FALSE, 'clean_text', 110, 55),

        ('pc_financial', 'Transaction Date', 'transaction_date', TRUE, 'parse_date', 10, 56),
        ('pc_financial', 'Posting Date', 'posted_date', FALSE, 'parse_date', 20, 57),
        ('pc_financial', 'Transaction Description', 'merchant_raw', TRUE, 'clean_text', 30, 58),
        ('pc_financial', 'Amount', 'amount', TRUE, 'parse_amount', 40, 59),

        ('triangle', 'Transaction Date', 'transaction_date', TRUE, 'parse_date', 10, 60),
        ('triangle', 'Posted Date', 'posted_date', FALSE, 'parse_date', 20, 61),
        ('triangle', 'Transaction Description', 'merchant_raw', FALSE, 'clean_text', 30, 62),
        ('triangle', 'Description', 'merchant_raw', FALSE, 'clean_text', 40, 63),
        ('triangle', 'Amount', 'amount', TRUE, 'parse_amount', 50, 64)
),
new_mapping AS (
    SELECT
        (SELECT COALESCE(max(mapping_id), 0) FROM source_column_mapping)
            + row_number() OVER (ORDER BY sort_key) AS mapping_id,
        *
    FROM mapping
    WHERE NOT EXISTS (
        SELECT 1
        FROM source_column_mapping
        WHERE source_id = mapping.source_id
          AND source_column = mapping.source_column
          AND target_column = mapping.target_column
    )
)
INSERT INTO source_column_mapping (
    mapping_id,
    source_id,
    source_column,
    target_column,
    required,
    transform_rule,
    sort_order
)
SELECT
    mapping_id,
    source_id,
    source_column,
    target_column,
    required,
    transform_rule,
    sort_order
FROM new_mapping;
