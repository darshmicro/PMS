/*
    Creates Demo_Login - the local (non-AD) password table backing two
    different AUTH_MODE values (see app/services/demo_auth_service.py's
    docstring for the full reasoning):

    1. demo_local - the Windows 11 Home / no-AD local demo path (see
       DEPLOY_WINDOWS11_HOME_DEMO.md), refused outright when
       ENVIRONMENT=production.
    2. hybrid - AD users and local-only accounts side by side, permitted
       in production (see DEPLOYMENT.md's "Hybrid (AD + local users)"
       section) - this is why this file now lives in the numbered core
       sequence rather than under sql/demo_only/ alone. It was originally
       demo-only; it is promoted to core infrastructure here because a
       real production deployment using AUTH_MODE=hybrid needs this table
       too. sql/demo_only/041_create_demo_login_table.sql still exists
       (identical CREATE TABLE, idempotent either way) for anyone
       following the older Windows 11 Home demo instructions verbatim -
       running both is harmless.

    A pure AD-only deployment (AUTH_MODE=iis_forwarded or ldap_bind, no
    local accounts at all) never needs this table populated, but creating
    it is harmless either way (it just stays empty).

    Run this after 001-040 (schema + seed permissions + the AD bootstrap
    admin), regardless of which AUTH_MODE you end up choosing.
*/

USE PMS_DB;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Demo_Login')
BEGIN
    CREATE TABLE Demo_Login (
        DemoCredentialID INT IDENTITY PRIMARY KEY,
        UserID           INT NOT NULL UNIQUE REFERENCES Users(UserID),
        PasswordHash     VARCHAR(255) NOT NULL,
        UpdatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;
GO
