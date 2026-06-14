UPDATE source_detection_rule
SET filename_pattern = 'preferred[ _]?package|preferred package'
WHERE source_id = 'scotia_preferred_package';
