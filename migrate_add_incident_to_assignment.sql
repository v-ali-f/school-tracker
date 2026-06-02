-- Миграция: добавить поле incident_id в таблицу service_assignment
-- Применить один раз на сервере (PostgreSQL) и локально (SQLite)
--
-- PostgreSQL:
ALTER TABLE service_assignment ADD COLUMN IF NOT EXISTS incident_id INTEGER REFERENCES incident(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_service_assignment_incident_id ON service_assignment(incident_id);

-- SQLite (не поддерживает IF NOT EXISTS для ADD COLUMN в старых версиях):
-- ALTER TABLE service_assignment ADD COLUMN incident_id INTEGER REFERENCES incident(id);
