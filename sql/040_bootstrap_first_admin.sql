/*
    One-time bootstrap script - NOT part of the M1-M28 module sequence,
    and deliberately not auto-run by application code.

    THE GAP THIS SCRIPT CLOSES: every subsequent user/role mapping in this
    system is created through POST /admin/users (app/api/routes/users.py),
    which itself requires the caller to already hold HR_ADMIN or SYS_ADMIN.
    On a brand-new database there is no such user yet, so nobody can ever
    reach that screen - a bootstrapping problem, not a bug. This script
    creates exactly one System Administrator mapping by hand, directly
    against the Users/User_Roles tables the same way 001's DDL defines
    them, so the very first login has a way in. Every admin mapping after
    this one should be created through the application (POST/PUT
    /admin/users), which also writes an Audit_Log entry - this script does
    not, since Audit_Log's own FK to Users cannot reference a user this
    script hasn't committed yet in the same batch on every SQL Server
    configuration; run it, confirm the login works, then optionally hand
    row-level history for it to the Audit Log viewer's "first login" entry
    written automatically by POST /auth/login instead.

    HOW TO USE:
    1. Run 001-039 first (full schema + seed permissions), in order.
    2. Replace 'COMPANY\\firstadmin' below with the real AD username (in
       DOMAIN\username form, matching whatever AUTH_MODE forwards/binds)
       of the person who will perform the first login and create every
       other user/role mapping from the UI.
    3. Run this script once.
    4. Log in as that user, confirm GET /auth/me shows role_codes
       containing "SYS_ADMIN", then use POST /admin/users for every
       real user/role mapping from here on - never re-run this script
       for anyone else.
*/

USE PMS_DB;
GO

DECLARE @FirstAdminADUsername VARCHAR(100) = 'COMPANY\firstadmin';  -- <-- EDIT THIS

IF NOT EXISTS (SELECT 1 FROM Users WHERE ADUsername = @FirstAdminADUsername)
BEGIN
    INSERT INTO Users (ADUsername, EmployeeID, IsActive)
    VALUES (@FirstAdminADUsername, NULL, 1);
END;

DECLARE @UserID INT = (SELECT UserID FROM Users WHERE ADUsername = @FirstAdminADUsername);
DECLARE @SysAdminRoleID INT = (SELECT RoleID FROM Roles WHERE RoleCode = 'SYS_ADMIN');

IF @SysAdminRoleID IS NULL
BEGIN
    RAISERROR('SYS_ADMIN role not found - run sql/002_seed_roles_and_permissions.sql first.', 16, 1);
END;

IF NOT EXISTS (SELECT 1 FROM User_Roles WHERE UserID = @UserID AND RoleID = @SysAdminRoleID)
BEGIN
    INSERT INTO User_Roles (UserID, RoleID) VALUES (@UserID, @SysAdminRoleID);
END;
GO
