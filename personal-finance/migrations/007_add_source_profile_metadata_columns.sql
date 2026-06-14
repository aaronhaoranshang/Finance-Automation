ALTER TABLE source_profile ADD COLUMN account_name TEXT;
ALTER TABLE source_profile ADD COLUMN account_name_template TEXT;
ALTER TABLE source_profile ADD COLUMN processed_file_label TEXT;
ALTER TABLE source_profile ADD COLUMN processed_file_label_template TEXT;
ALTER TABLE source_profile ADD COLUMN currency TEXT DEFAULT 'CAD';
ALTER TABLE source_profile ADD COLUMN amount_multiplier DOUBLE DEFAULT 1;
ALTER TABLE source_profile ADD COLUMN default_scope TEXT DEFAULT 'personal';
ALTER TABLE source_profile ADD COLUMN account_aliases TEXT;

ALTER TABLE source_detection_rule ADD COLUMN column_value_rules TEXT;
