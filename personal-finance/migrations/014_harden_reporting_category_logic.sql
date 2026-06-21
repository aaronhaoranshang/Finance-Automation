UPDATE transaction_type_master
SET
    affects_spend = FALSE,
    affects_income = TRUE,
    affects_cash_flow = TRUE,
    requires_category = TRUE,
    updated_at = now()
WHERE transaction_type = 'income';

INSERT INTO transaction_type_master (
    transaction_type,
    display_name,
    affects_spend,
    affects_income,
    affects_cash_flow,
    requires_category,
    default_scope,
    sort_order,
    enabled
)
VALUES (
    'ignored',
    'Excluded',
    FALSE,
    FALSE,
    FALSE,
    FALSE,
    'personal',
    120,
    TRUE
)
ON CONFLICT (transaction_type) DO UPDATE
SET
    display_name = excluded.display_name,
    affects_spend = excluded.affects_spend,
    affects_income = excluded.affects_income,
    affects_cash_flow = excluded.affects_cash_flow,
    requires_category = excluded.requires_category,
    default_scope = excluded.default_scope,
    sort_order = excluded.sort_order,
    enabled = TRUE,
    updated_at = now();

UPDATE category_master
SET
    enabled = FALSE,
    updated_at = now()
WHERE owner_type = 'system'
  AND category = 'Entertainment'
  AND subcategory = 'Games / Hobbies';

INSERT INTO category_master (
    category_id,
    category,
    subcategory,
    owner_type,
    enabled,
    sort_order
)
VALUES (
    (SELECT COALESCE(max(category_id), 0) + 1 FROM category_master),
    'Entertainment',
    'Games & Hobbies',
    'system',
    TRUE,
    63
)
ON CONFLICT (category, subcategory, owner_type) DO UPDATE
SET
    enabled = TRUE,
    sort_order = excluded.sort_order,
    updated_at = now();

UPDATE merchant_rule
SET
    subcategory = 'Games & Hobbies',
    updated_at = now()
WHERE owner_type = 'system'
  AND category = 'Entertainment'
  AND subcategory = 'Games / Hobbies';
