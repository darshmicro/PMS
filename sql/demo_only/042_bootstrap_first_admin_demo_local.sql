/*
    DEMO-ONLY one-time bootstrap for AUTH_MODE=demo_local - the local
    Windows 11 Home demo path with no AD domain. This is the demo-mode
    equivalent of sql/040_bootstrap_first_admin.sql (which bootstraps the
    first SYS_ADMIN for a real AD-backed production deployment): every
    subsequent user is created through POST /admin/users (role mapping)
    plus POST /auth/demo/set-password/{user_id} (demo password), both of
    which require the caller to already be HR_ADMIN/SYS_ADMIN - so the
    very first login needs one account seeded by hand.

    Run this after 041_create_demo_login_table.sql in this same folder.

    Creates username "demoadmin" with password "Demo@12345" (bcrypt hash
    below - passlib's bcrypt scheme, matching app/services/demo_auth_
    service.py). CHANGE THIS PASSWORD IMMEDIATELY after your first login,
    via PUT /auth/demo/change-password - do not leave the well-known demo
    password active beyond initial setup, even for a local demo machine.
*/

USE PMS_DB;
GO

DECLARE @DemoAdminUsername VARCHAR(100) = 'demoadmin';
-- bcrypt hash of 'Demo@12345' - change your password after first login.
DECLARE @DemoAdminPasswordHash VARCHAR(255) = '$2b$12$tzqbFvAhdaC.2MedrckFJ.RCBMKWwmfoDQGRsKJJUMMHZ9OqfmMMy';

IF NOT EXISTS (SELECT 1 FROM Users WHERE ADUsername = @DemoAdminUsername)
BEGIN
    INSERT INTO Users (ADUsername, EmployeeID, IsActive)
    VALUES (@DemoAdminUsername, NULL, 1);
END;

DECLARE @UserID INT = (SELECT UserID FROM Users WHERE ADUsername = @DemoAdminUsername);
DECLARE @SysAdminRoleID INT = (SELECT RoleID FROM Roles WHERE RoleCode = 'SYS_ADMIN');

IF @SysAdminRoleID IS NULL
BEGIN
    RAISERROR('SYS_ADMIN role not found - run sql/002_seed_roles_and_permissions.sql first.', 16, 1);
END;

IF NOT EXISTS (SELECT 1 FROM User_Roles WHERE UserID = @UserID AND RoleID = @SysAdminRoleID)
BEGIN
    INSERT INTO User_Roles (UserID, RoleID) VALUES (@UserID, @SysAdminRoleID);
END;

IF NOT EXISTS (SELECT 1 FROM Demo_Login WHERE UserID = @UserID)
BEGIN
    INSERT INTO Demo_Login (UserID, PasswordHash) VALUES (@UserID, @DemoAdminPasswordHash);
END;
GO
