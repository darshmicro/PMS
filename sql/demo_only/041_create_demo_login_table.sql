/*
    DEMO-ONLY - not part of the M1-M28 production build, and not run
    against a production database. See app/services/demo_auth_service.py's
    docstring for the full reasoning.

    Only needed if you are running this system with AUTH_MODE=demo_local -
    the Windows 11 Home / no-AD local demo path. A production deployment
    (AUTH_MODE=iis_forwarded, per DEPLOYMENT.md) never creates this table
    and never needs it.

    Run this after 001-039 (the full production schema + permission seed),
    and before 042_bootstrap_first_admin_demo_local.sql in this same folder.
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
