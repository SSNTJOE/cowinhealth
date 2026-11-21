-- Low-privilege MySQL account for Health-ing (localhost only).
-- No DROP / ALTER / GRANT / FILE / SUPER. App runtime: SELECT/INSERT/UPDATE/DELETE only.
-- Run as root (or another admin). Put the same password into .env as MYSQL_*.

CREATE DATABASE IF NOT EXISTS healthing
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- 1) First-time schema: keep using an admin account (or temporarily grant CREATE/ALTER),
--    start the app once so tables exist, then revoke those privileges.
-- 2) Day-to-day app account:

CREATE USER IF NOT EXISTS 'healthing_app'@'localhost'
  IDENTIFIED BY 'change-me-strong-password';

GRANT SELECT, INSERT, UPDATE, DELETE
  ON healthing.*
  TO 'healthing_app'@'localhost';

-- Explicitly not granted: DROP, ALTER, CREATE, REFERENCES, TRIGGER, SUPER, FILE, PROCESS, GRANT OPTION.

FLUSH PRIVILEGES;

-- Optional TCP loopback alias:
-- CREATE USER IF NOT EXISTS 'healthing_app'@'127.0.0.1' IDENTIFIED BY 'change-me-strong-password';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON healthing.* TO 'healthing_app'@'127.0.0.1';
-- FLUSH PRIVILEGES;
