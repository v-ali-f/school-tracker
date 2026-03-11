-- Дополнительные поля v56 для модуля олимпиад
ALTER TABLE olympiad_subject_mapping ADD COLUMN IF NOT EXISTS department_id INTEGER;
ALTER TABLE olympiad_subject_mapping ADD COLUMN IF NOT EXISTS comment TEXT;
ALTER TABLE olympiad_subject_mapping ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
ALTER TABLE olympiad_import_session ADD COLUMN IF NOT EXISTS department_id INTEGER;
ALTER TABLE olympiad_result ADD COLUMN IF NOT EXISTS result_type VARCHAR(30);
ALTER TABLE olympiad_unmatched_row ADD COLUMN IF NOT EXISTS unmatched_reason TEXT;
ALTER TABLE olympiad_unmatched_row ADD COLUMN IF NOT EXISTS maybe_left_school BOOLEAN DEFAULT FALSE;
ALTER TABLE olympiad_unmatched_row ADD COLUMN IF NOT EXISTS comment TEXT;
ALTER TABLE olympiad_unmatched_row ADD COLUMN IF NOT EXISTS raw_stage VARCHAR(50);

UPDATE olympiad_subject_mapping
SET updated_at = COALESCE(updated_at, created_at)
WHERE updated_at IS NULL;
