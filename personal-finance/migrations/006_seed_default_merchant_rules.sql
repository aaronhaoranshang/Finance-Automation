WITH seed_rules(pattern, match_type, merchant_clean, transaction_type, scope, category, subcategory, priority, notes, sort_key) AS (
    VALUES
        ('COSTCO', 'contains', 'Costco', 'expense', 'personal', 'Shopping', 'Warehouse', 100, 'Default system rule', 1),
        ('STARBUCKS', 'contains', 'Starbucks', 'expense', 'personal', 'Food', 'Coffee', 100, 'Default system rule', 2),
        ('TIM HORTONS', 'contains', 'Tim Hortons', 'expense', 'personal', 'Food', 'Coffee', 100, 'Default system rule', 3),
        ('UBER EATS', 'contains', 'Uber Eats', 'expense', 'personal', 'Food', 'Delivery', 100, 'Default system rule', 4),
        ('DOORDASH', 'contains', 'DoorDash', 'expense', 'personal', 'Food', 'Delivery', 100, 'Default system rule', 5),
        ('AIR CANADA', 'contains', 'Air Canada', 'expense', 'personal', 'Travel', 'Flights', 100, 'Default system rule', 6),
        ('UBER TRIP', 'contains', 'Uber', 'expense', 'personal', 'Transportation', 'Ride Share', 100, 'Default system rule', 7),
        ('SHELL', 'contains', 'Shell', 'expense', 'personal', 'Transportation', 'Fuel', 100, 'Default system rule', 8),
        ('NETFLIX', 'contains', 'Netflix', 'expense', 'personal', 'Subscriptions', 'Streaming', 100, 'Default system rule', 9),
        ('SPOTIFY', 'contains', 'Spotify', 'expense', 'personal', 'Subscriptions', 'Streaming', 100, 'Default system rule', 10),
        ('AMAZON', 'contains', 'Amazon', 'expense', 'personal', 'Shopping', 'Online Shopping', 100, 'Default system rule', 11),
        ('WALMART', 'contains', 'Walmart', 'expense', 'personal', 'Shopping', 'General', 100, 'Default system rule', 12),
        ('SOBEYS', 'contains', 'Sobeys', 'expense', 'personal', 'Food', 'Groceries', 100, 'Default system rule', 13),
        ('FOOD BASICS', 'contains', 'Food Basics', 'expense', 'personal', 'Food', 'Groceries', 100, 'Default system rule', 14)
),
new_rules AS (
    SELECT
        (SELECT COALESCE(max(rule_id), 0) FROM merchant_rule)
            + row_number() OVER (ORDER BY sort_key) AS rule_id,
        *
    FROM seed_rules
    WHERE NOT EXISTS (
        SELECT 1
        FROM merchant_rule
        WHERE owner_type = 'system'
          AND pattern = seed_rules.pattern
          AND match_type = seed_rules.match_type
    )
)
INSERT INTO merchant_rule (
    rule_id,
    owner_type,
    pattern,
    match_type,
    merchant_clean,
    transaction_type,
    scope,
    category,
    subcategory,
    priority,
    enabled,
    notes
)
SELECT
    rule_id,
    'system',
    pattern,
    match_type,
    merchant_clean,
    transaction_type,
    scope,
    category,
    subcategory,
    priority,
    TRUE,
    notes
FROM new_rules;
