#!/bin/sh
# Runs once, on first start of an empty data volume.
#   app_owner  owns the schema; used only by the one-shot migrate service.
#   app_rw     used by the running app: data access only, no DDL, and only
#              SELECT/INSERT on security_events (the migration revokes the rest).
# Nobody else may connect; the public schema is closed to PUBLIC.
set -eu

psql -v ON_ERROR_STOP=1 --username postgres <<SQL
CREATE ROLE app_owner LOGIN PASSWORD '${DB_OWNER_PASSWORD}';
CREATE ROLE app_rw    LOGIN PASSWORD '${DB_RW_PASSWORD}';
CREATE DATABASE app OWNER app_owner;
REVOKE ALL ON DATABASE app FROM PUBLIC;
REVOKE ALL ON DATABASE postgres FROM PUBLIC;
REVOKE ALL ON DATABASE template1 FROM PUBLIC;
GRANT CONNECT ON DATABASE app TO app_owner, app_rw;
SQL

psql -v ON_ERROR_STOP=1 --username postgres --dbname app <<SQL
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO app_owner;
GRANT USAGE ON SCHEMA public TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app_rw;
SQL
