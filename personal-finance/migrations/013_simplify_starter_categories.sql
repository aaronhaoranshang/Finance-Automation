UPDATE category_master
SET
    enabled = FALSE,
    updated_at = now()
WHERE owner_type = 'system';

WITH starter_categories(category, subcategory, sort_order, sort_key) AS (
    VALUES
        ('Food', '', 10, 1),
        ('Food', 'Dining', 11, 2),
        ('Food', 'Coffee', 12, 3),
        ('Food', 'Delivery', 13, 4),
        ('Grocery', '', 20, 5),
        ('Shopping', '', 30, 6),
        ('Transportation', '', 40, 7),
        ('Transportation', 'Transit', 41, 8),
        ('Transportation', 'Gas / EV Charging', 42, 9),
        ('Transportation', 'Parking', 43, 10),
        ('Transportation', 'Ride Share', 44, 11),
        ('Bills & Utilities', '', 50, 12),
        ('Bills & Utilities', 'Rent / Mortgage', 51, 13),
        ('Bills & Utilities', 'Phone / Internet', 52, 14),
        ('Bills & Utilities', 'Utilities', 53, 15),
        ('Entertainment', '', 60, 16),
        ('Entertainment', 'Subscriptions', 61, 17),
        ('Entertainment', 'Events', 62, 18),
        ('Entertainment', 'Games / Hobbies', 63, 19),
        ('Travel', '', 70, 20),
        ('Fees', '', 80, 21),
        ('Other', '', 90, 22),
        ('Excluded', '', 100, 23),
        ('Income', '', 110, 24),
        ('Income', 'Salary', 111, 25),
        ('Income', 'Interest', 112, 26),
        ('Income', 'Tax Refund', 113, 27),
        ('Income', 'Bonus', 114, 28),
        ('Income', 'Other Income', 115, 29)
),
seed_rows AS (
    SELECT
        (SELECT COALESCE(max(category_id), 0) FROM category_master)
            + row_number() OVER (ORDER BY sort_key) AS category_id,
        category,
        subcategory,
        sort_order
    FROM starter_categories
)
INSERT INTO category_master (
    category_id,
    category,
    subcategory,
    owner_type,
    enabled,
    sort_order
)
SELECT
    category_id,
    category,
    subcategory,
    'system',
    TRUE,
    sort_order
FROM seed_rows
ON CONFLICT (category, subcategory, owner_type) DO UPDATE
SET
    enabled = TRUE,
    sort_order = excluded.sort_order,
    updated_at = now();

UPDATE transaction_type_master
SET
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

UPDATE merchant_rule
SET
    category = 'Grocery',
    subcategory = '',
    updated_at = now()
WHERE owner_type = 'system'
  AND pattern IN ('COSTCO', 'SOBEYS', 'FOOD BASICS');

UPDATE merchant_rule
SET
    category = 'Travel',
    subcategory = '',
    updated_at = now()
WHERE owner_type = 'system'
  AND pattern = 'AIR CANADA';

UPDATE merchant_rule
SET
    category = 'Transportation',
    subcategory = 'Gas / EV Charging',
    updated_at = now()
WHERE owner_type = 'system'
  AND pattern = 'SHELL';

UPDATE merchant_rule
SET
    category = 'Entertainment',
    subcategory = 'Subscriptions',
    updated_at = now()
WHERE owner_type = 'system'
  AND pattern IN ('NETFLIX', 'SPOTIFY');

UPDATE merchant_rule
SET
    category = 'Shopping',
    subcategory = '',
    updated_at = now()
WHERE owner_type = 'system'
  AND pattern IN ('AMAZON', 'WALMART');
