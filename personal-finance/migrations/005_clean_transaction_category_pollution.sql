UPDATE transactions
SET
    category = '',
    subcategory = ''
WHERE transaction_type IN (
    'payment',
    'debt_payment',
    'transfer',
    'stored_value_reload',
    'income',
    'manual_review',
    'zero'
)
  AND COALESCE(manual_override, FALSE) = FALSE;
