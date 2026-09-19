/*
    DEMO-ONLY - not part of the M1-M28 production build. Seeds a small,
    realistic org hierarchy (one person per business role) so you can log
    in as each role and see what that role's dashboard/permissions look
    like, without clicking through POST /employees + POST /admin/users +
    POST /auth/demo/set-password by hand six times in /docs.

    Only meaningful with AUTH_MODE=demo_local (Windows 11 Home demo).
    Run this AFTER:
      - 000_FULL_DATABASE_SETUP.sql (or 001-039 individually), AND
      - sql/demo_only/041_create_demo_login_table.sql, AND
      - sql/demo_only/042_bootstrap_first_admin_demo_local.sql (demoadmin)

    Creates 6 Employee + User + Demo_Login rows, one per role:
      EMPLOYEE      emp.demo      / Demo@12345   Rohan Iyer
      MANAGER       manager.demo  / Demo@12345   Sunita Sharma  (Rohan's manager)
      HOD           hod.demo      / Demo@12345   Amit Verma     (dept head)
      PLANT_HEAD    planthead.demo/ Demo@12345   Vikram Singh
      HR            hr.demo       / Demo@12345   Neha Gupta
      MD            md.demo       / Demo@12345   Arjun Mehta

    Org links: Rohan (EMPLOYEE) -> ManagerID = Sunita, HODID = Amit.
    Sunita (MANAGER) -> HODID = Amit. Everyone's HRID = Neha.

    All EmployeeCode values are tagged 'DEMO-' so they're easy to find and
    purge later, same convention as sql/004 and sql/007's SAMPLE- rows.

    Every login below shares the same password (Demo@12345, same bcrypt
    hash as demoadmin's) purely for demo convenience - change passwords
    individually via PUT /auth/demo/change-password once logged in as each
    user, if you want them to differ.

    Idempotent: safe to re-run - every block checks for its own ADUsername
    before inserting anything.
*/

USE PMS_DB;
GO

-- bcrypt hash of 'Demo@12345' (passlib's bcrypt scheme) - identical to the
-- one sql/demo_only/042 uses for demoadmin.
DECLARE @DemoPasswordHash VARCHAR(255) = '$2b$12$tzqbFvAhdaC.2MedrckFJ.RCBMKWwmfoDQGRsKJJUMMHZ9OqfmMMy';

-- ===================================================================
-- 1. HR - Neha Gupta (created first: everyone else's HRID points to her)
-- ===================================================================
IF NOT EXISTS (SELECT 1 FROM Employees WHERE ADUsername = 'hr.demo')
BEGIN
    INSERT INTO Employees (EmployeeCode, ADUsername, FullName, Email, EmploymentStatus, IsActive)
    VALUES ('DEMO-HR01', 'hr.demo', 'Neha Gupta', 'neha.gupta@example.com', 'ACTIVE', 1);
END;
DECLARE @HREmployeeID INT = (SELECT EmployeeID FROM Employees WHERE ADUsername = 'hr.demo');

IF NOT EXISTS (SELECT 1 FROM Users WHERE ADUsername = 'hr.demo')
BEGIN
    INSERT INTO Users (ADUsername, EmployeeID, IsActive) VALUES ('hr.demo', @HREmployeeID, 1);
END;
DECLARE @HRUserID INT = (SELECT UserID FROM Users WHERE ADUsername = 'hr.demo');
DECLARE @HRRoleID INT = (SELECT RoleID FROM Roles WHERE RoleCode = 'HR');
IF @HRRoleID IS NULL RAISERROR('HR role not found - run sql/002_seed_roles_and_permissions.sql first.', 16, 1);
IF NOT EXISTS (SELECT 1 FROM User_Roles WHERE UserID = @HRUserID AND RoleID = @HRRoleID)
    INSERT INTO User_Roles (UserID, RoleID) VALUES (@HRUserID, @HRRoleID);
IF NOT EXISTS (SELECT 1 FROM Demo_Login WHERE UserID = @HRUserID)
    INSERT INTO Demo_Login (UserID, PasswordHash) VALUES (@HRUserID, @DemoPasswordHash);

-- ===================================================================
-- 2. HOD - Amit Verma
-- ===================================================================
IF NOT EXISTS (SELECT 1 FROM Employees WHERE ADUsername = 'hod.demo')
BEGIN
    INSERT INTO Employees (EmployeeCode, ADUsername, FullName, Email, HRID, EmploymentStatus, IsActive)
    VALUES ('DEMO-HOD01', 'hod.demo', 'Amit Verma', 'amit.verma@example.com', @HREmployeeID, 'ACTIVE', 1);
END;
DECLARE @HODEmployeeID INT = (SELECT EmployeeID FROM Employees WHERE ADUsername = 'hod.demo');

IF NOT EXISTS (SELECT 1 FROM Users WHERE ADUsername = 'hod.demo')
    INSERT INTO Users (ADUsername, EmployeeID, IsActive) VALUES ('hod.demo', @HODEmployeeID, 1);
DECLARE @HODUserID INT = (SELECT UserID FROM Users WHERE ADUsername = 'hod.demo');
DECLARE @HODRoleID INT = (SELECT RoleID FROM Roles WHERE RoleCode = 'HOD');
IF @HODRoleID IS NULL RAISERROR('HOD role not found - run sql/002_seed_roles_and_permissions.sql first.', 16, 1);
IF NOT EXISTS (SELECT 1 FROM User_Roles WHERE UserID = @HODUserID AND RoleID = @HODRoleID)
    INSERT INTO User_Roles (UserID, RoleID) VALUES (@HODUserID, @HODRoleID);
IF NOT EXISTS (SELECT 1 FROM Demo_Login WHERE UserID = @HODUserID)
    INSERT INTO Demo_Login (UserID, PasswordHash) VALUES (@HODUserID, @DemoPasswordHash);

-- ===================================================================
-- 3. MANAGER - Sunita Sharma (reports to Amit)
-- ===================================================================
IF NOT EXISTS (SELECT 1 FROM Employees WHERE ADUsername = 'manager.demo')
BEGIN
    INSERT INTO Employees (EmployeeCode, ADUsername, FullName, Email, HODID, HRID, EmploymentStatus, IsActive)
    VALUES ('DEMO-MGR01', 'manager.demo', 'Sunita Sharma', 'sunita.sharma@example.com', @HODEmployeeID, @HREmployeeID, 'ACTIVE', 1);
END;
DECLARE @ManagerEmployeeID INT = (SELECT EmployeeID FROM Employees WHERE ADUsername = 'manager.demo');

IF NOT EXISTS (SELECT 1 FROM Users WHERE ADUsername = 'manager.demo')
    INSERT INTO Users (ADUsername, EmployeeID, IsActive) VALUES ('manager.demo', @ManagerEmployeeID, 1);
DECLARE @ManagerUserID INT = (SELECT UserID FROM Users WHERE ADUsername = 'manager.demo');
DECLARE @ManagerRoleID INT = (SELECT RoleID FROM Roles WHERE RoleCode = 'MANAGER');
IF @ManagerRoleID IS NULL RAISERROR('MANAGER role not found - run sql/002_seed_roles_and_permissions.sql first.', 16, 1);
IF NOT EXISTS (SELECT 1 FROM User_Roles WHERE UserID = @ManagerUserID AND RoleID = @ManagerRoleID)
    INSERT INTO User_Roles (UserID, RoleID) VALUES (@ManagerUserID, @ManagerRoleID);
IF NOT EXISTS (SELECT 1 FROM Demo_Login WHERE UserID = @ManagerUserID)
    INSERT INTO Demo_Login (UserID, PasswordHash) VALUES (@ManagerUserID, @DemoPasswordHash);

-- ===================================================================
-- 4. EMPLOYEE - Rohan Iyer (reports to Sunita, department head Amit)
-- ===================================================================
IF NOT EXISTS (SELECT 1 FROM Employees WHERE ADUsername = 'emp.demo')
BEGIN
    INSERT INTO Employees (EmployeeCode, ADUsername, FullName, Email, ManagerID, HODID, HRID, EmploymentStatus, IsActive)
    VALUES ('DEMO-EMP01', 'emp.demo', 'Rohan Iyer', 'rohan.iyer@example.com', @ManagerEmployeeID, @HODEmployeeID, @HREmployeeID, 'ACTIVE', 1);
END;
DECLARE @EmpEmployeeID INT = (SELECT EmployeeID FROM Employees WHERE ADUsername = 'emp.demo');

IF NOT EXISTS (SELECT 1 FROM Users WHERE ADUsername = 'emp.demo')
    INSERT INTO Users (ADUsername, EmployeeID, IsActive) VALUES ('emp.demo', @EmpEmployeeID, 1);
DECLARE @EmpUserID INT = (SELECT UserID FROM Users WHERE ADUsername = 'emp.demo');
DECLARE @EmpRoleID INT = (SELECT RoleID FROM Roles WHERE RoleCode = 'EMPLOYEE');
IF @EmpRoleID IS NULL RAISERROR('EMPLOYEE role not found - run sql/002_seed_roles_and_permissions.sql first.', 16, 1);
IF NOT EXISTS (SELECT 1 FROM User_Roles WHERE UserID = @EmpUserID AND RoleID = @EmpRoleID)
    INSERT INTO User_Roles (UserID, RoleID) VALUES (@EmpUserID, @EmpRoleID);
IF NOT EXISTS (SELECT 1 FROM Demo_Login WHERE UserID = @EmpUserID)
    INSERT INTO Demo_Login (UserID, PasswordHash) VALUES (@EmpUserID, @DemoPasswordHash);

-- ===================================================================
-- 5. PLANT_HEAD - Vikram Singh
-- ===================================================================
IF NOT EXISTS (SELECT 1 FROM Employees WHERE ADUsername = 'planthead.demo')
BEGIN
    INSERT INTO Employees (EmployeeCode, ADUsername, FullName, Email, HRID, EmploymentStatus, IsActive)
    VALUES ('DEMO-PLH01', 'planthead.demo', 'Vikram Singh', 'vikram.singh@example.com', @HREmployeeID, 'ACTIVE', 1);
END;
DECLARE @PlantHeadEmployeeID INT = (SELECT EmployeeID FROM Employees WHERE ADUsername = 'planthead.demo');

IF NOT EXISTS (SELECT 1 FROM Users WHERE ADUsername = 'planthead.demo')
    INSERT INTO Users (ADUsername, EmployeeID, IsActive) VALUES ('planthead.demo', @PlantHeadEmployeeID, 1);
DECLARE @PlantHeadUserID INT = (SELECT UserID FROM Users WHERE ADUsername = 'planthead.demo');
DECLARE @PlantHeadRoleID INT = (SELECT RoleID FROM Roles WHERE RoleCode = 'PLANT_HEAD');
IF @PlantHeadRoleID IS NULL RAISERROR('PLANT_HEAD role not found - run sql/002_seed_roles_and_permissions.sql first.', 16, 1);
IF NOT EXISTS (SELECT 1 FROM User_Roles WHERE UserID = @PlantHeadUserID AND RoleID = @PlantHeadRoleID)
    INSERT INTO User_Roles (UserID, RoleID) VALUES (@PlantHeadUserID, @PlantHeadRoleID);
IF NOT EXISTS (SELECT 1 FROM Demo_Login WHERE UserID = @PlantHeadUserID)
    INSERT INTO Demo_Login (UserID, PasswordHash) VALUES (@PlantHeadUserID, @DemoPasswordHash);

-- ===================================================================
-- 6. MD - Arjun Mehta
-- ===================================================================
IF NOT EXISTS (SELECT 1 FROM Employees WHERE ADUsername = 'md.demo')
BEGIN
    INSERT INTO Employees (EmployeeCode, ADUsername, FullName, Email, HRID, EmploymentStatus, IsActive)
    VALUES ('DEMO-MD01', 'md.demo', 'Arjun Mehta', 'arjun.mehta@example.com', @HREmployeeID, 'ACTIVE', 1);
END;
DECLARE @MDEmployeeID INT = (SELECT EmployeeID FROM Employees WHERE ADUsername = 'md.demo');

IF NOT EXISTS (SELECT 1 FROM Users WHERE ADUsername = 'md.demo')
    INSERT INTO Users (ADUsername, EmployeeID, IsActive) VALUES ('md.demo', @MDEmployeeID, 1);
DECLARE @MDUserID INT = (SELECT UserID FROM Users WHERE ADUsername = 'md.demo');
DECLARE @MDRoleID INT = (SELECT RoleID FROM Roles WHERE RoleCode = 'MD');
IF @MDRoleID IS NULL RAISERROR('MD role not found - run sql/002_seed_roles_and_permissions.sql first.', 16, 1);
IF NOT EXISTS (SELECT 1 FROM User_Roles WHERE UserID = @MDUserID AND RoleID = @MDRoleID)
    INSERT INTO User_Roles (UserID, RoleID) VALUES (@MDUserID, @MDRoleID);
IF NOT EXISTS (SELECT 1 FROM Demo_Login WHERE UserID = @MDUserID)
    INSERT INTO Demo_Login (UserID, PasswordHash) VALUES (@MDUserID, @DemoPasswordHash);
GO

PRINT 'Demo users seeded. Log in on the Local demo tab with any of:';
PRINT '  emp.demo / manager.demo / hod.demo / planthead.demo / hr.demo / md.demo';
PRINT '  password (all): Demo@12345';
GO
