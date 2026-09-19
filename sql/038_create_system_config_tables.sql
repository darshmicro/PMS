/*
    M28 DDL: System_Config (spec Section 5 row 545 / screen #37). Run
    after 037 (Performance History permissions).

    One row per named setting (key/value) - see the SystemConfig model's
    docstring for why this is a key/value table rather than one column
    per setting, and for why it is scoped to non-secret operational
    settings only (SMTP relay, AD server/domain, file storage path) and
    never true credentials (DB_PASSWORD, AD_BIND_PASSWORD,
    SESSION_SECRET_KEY - those remain environment-variable-only, per
    Section 33/42, enforced by system_config_service.py's NON_SECRET_KEYS
    allowlist at the application layer, not by this table's schema).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'System_Config')
BEGIN
    CREATE TABLE System_Config (
        ConfigID        INT IDENTITY PRIMARY KEY,
        ConfigKey       VARCHAR(100) NOT NULL UNIQUE,
        ConfigValue     VARCHAR(500) NULL,
        Description     VARCHAR(300) NULL,
        ModifiedBy      INT NULL REFERENCES Users(UserID),
        ModifiedAt      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;
GO

/*
    No default rows are seeded here deliberately - an empty table means
    every operational setting falls back to its environment-variable
    default (see app/core/config.py's Settings class) until a System
    Administrator explicitly overrides it through this screen, matching
    the "never hard-coded" principle this module's own docstring
    documents at length.
*/
GO
