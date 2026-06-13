INSERT INTO transaction_type_master (
    transaction_type,
    display_name,
    affects_spend,
    affects_income,
    affects_cash_flow,
    requires_category,
    default_scope,
    sort_order
)
VALUES
    ('expense', 'Expense', TRUE, FALSE, TRUE, TRUE, 'personal', 10),
    ('refund', 'Refund', TRUE, FALSE, TRUE, TRUE, 'personal', 20),
    ('credit', 'Merchant Credit', TRUE, FALSE, TRUE, TRUE, 'personal', 30),
    ('reimbursement', 'Reimbursement', TRUE, FALSE, TRUE, FALSE, 'personal', 40),
    ('income', 'Income', FALSE, TRUE, TRUE, FALSE, 'personal', 50),
    ('payment', 'Card Payment', FALSE, FALSE, TRUE, FALSE, 'personal', 60),
    ('debt_payment', 'Debt Payment', FALSE, FALSE, TRUE, FALSE, 'personal', 70),
    ('transfer', 'Internal Transfer', FALSE, FALSE, TRUE, FALSE, 'personal', 80),
    ('stored_value_reload', 'Prepaid Card Reload', FALSE, FALSE, TRUE, FALSE, 'personal', 90),
    ('manual_review', 'Needs Review', FALSE, FALSE, FALSE, FALSE, 'personal', 100),
    ('zero', 'Zero Amount', FALSE, FALSE, FALSE, FALSE, 'personal', 110)
ON CONFLICT (transaction_type) DO NOTHING;
