#!/bin/sh
# Sample CRM data and a read-only "backup" role (it can dump, it cannot change anything).
set -e
psql -v ON_ERROR_STOP=1 -U postgres -d crm <<SQL
CREATE TABLE customers (id serial PRIMARY KEY, name text NOT NULL, city text, created date DEFAULT current_date);
INSERT INTO customers (name, city)
SELECT 'Customer ' || i, (ARRAY['Québec', 'Lévis', 'Montréal', 'Sherbrooke'])[1 + i % 4] FROM generate_series(1, 500) i;
CREATE ROLE backup LOGIN PASSWORD '${BACKUP_DB_PASSWORD}';
GRANT pg_read_all_data TO backup;
SQL
