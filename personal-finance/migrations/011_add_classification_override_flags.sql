ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category_manual_override BOOLEAN DEFAULT FALSE;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS type_manual_override BOOLEAN DEFAULT FALSE;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS merchant_manual_override BOOLEAN DEFAULT FALSE;

UPDATE transactions
SET
    category_manual_override = COALESCE(category_manual_override, COALESCE(manual_override, FALSE)),
    type_manual_override = COALESCE(type_manual_override, COALESCE(manual_override, FALSE)),
    merchant_manual_override = COALESCE(merchant_manual_override, COALESCE(manual_override, FALSE));
