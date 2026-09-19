/*
    M3 (Org Masters) + M4 (Employee Master) DDL.
    Run after 001_create_auth_rbac_tables.sql (Employees must already exist).
    All ALTER TABLE statements on Employees are additive/nullable - no
    existing column is renamed or dropped, so M1/M2 data and code keep
    working unchanged (see README_M1_M2.md's forward note).
*/

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Companies')
BEGIN
    CREATE TABLE Companies (
        CompanyID   INT IDENTITY PRIMARY KEY,
        CompanyCode VARCHAR(20) NOT NULL UNIQUE,
        CompanyName VARCHAR(150) NOT NULL,
        IsActive    BIT NOT NULL DEFAULT 1
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Plants')
BEGIN
    CREATE TABLE Plants (
        PlantID     INT IDENTITY PRIMARY KEY,
        CompanyID   INT NOT NULL REFERENCES Companies(CompanyID),
        PlantCode   VARCHAR(20) NOT NULL UNIQUE,
        PlantName   VARCHAR(150) NOT NULL,
        IsActive    BIT NOT NULL DEFAULT 1
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Departments')
BEGIN
    CREATE TABLE Departments (
        DepartmentID INT IDENTITY PRIMARY KEY,
        PlantID      INT NOT NULL REFERENCES Plants(PlantID),
        DeptCode     VARCHAR(20) NOT NULL UNIQUE,
        DeptName     VARCHAR(150) NOT NULL,
        IsActive     BIT NOT NULL DEFAULT 1
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Sections')
BEGIN
    CREATE TABLE Sections (
        SectionID    INT IDENTITY PRIMARY KEY,
        DepartmentID INT NOT NULL REFERENCES Departments(DepartmentID),
        SectionCode  VARCHAR(20) NOT NULL UNIQUE,
        SectionName  VARCHAR(150) NOT NULL,
        IsActive     BIT NOT NULL DEFAULT 1
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Designations')
BEGIN
    CREATE TABLE Designations (
        DesignationID   INT IDENTITY PRIMARY KEY,
        DesignationCode VARCHAR(20) NOT NULL UNIQUE,
        DesignationName VARCHAR(150) NOT NULL,
        IsActive        BIT NOT NULL DEFAULT 1
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Grades')
BEGIN
    CREATE TABLE Grades (
        GradeID   INT IDENTITY PRIMARY KEY,
        GradeCode VARCHAR(20) NOT NULL UNIQUE,
        GradeName VARCHAR(100) NOT NULL,
        IsActive  BIT NOT NULL DEFAULT 1
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Employee_Categories')
BEGIN
    CREATE TABLE Employee_Categories (
        EmployeeCategoryID INT IDENTITY PRIMARY KEY,
        CategoryCode       VARCHAR(20) NOT NULL UNIQUE,
        CategoryName       VARCHAR(100) NOT NULL,
        IsActive           BIT NOT NULL DEFAULT 1
    );
END;
GO

/* -----------------------------------------------------------------------
   M4: extend Employees additively now that the master tables above exist.
   ----------------------------------------------------------------------- */
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'DepartmentID')
BEGIN
    ALTER TABLE Employees ADD DepartmentID INT NULL REFERENCES Departments(DepartmentID);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'SectionID')
BEGIN
    ALTER TABLE Employees ADD SectionID INT NULL REFERENCES Sections(SectionID);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'DesignationID')
BEGIN
    ALTER TABLE Employees ADD DesignationID INT NULL REFERENCES Designations(DesignationID);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'GradeID')
BEGIN
    ALTER TABLE Employees ADD GradeID INT NULL REFERENCES Grades(GradeID);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'PlantID')
BEGIN
    ALTER TABLE Employees ADD PlantID INT NULL REFERENCES Plants(PlantID);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'EmployeeCategoryID')
BEGIN
    ALTER TABLE Employees ADD EmployeeCategoryID INT NULL REFERENCES Employee_Categories(EmployeeCategoryID);
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'DateOfJoining')
BEGIN
    ALTER TABLE Employees ADD DateOfJoining DATE NULL;
END;

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('Employees') AND name = 'HRID')
BEGIN
    ALTER TABLE Employees ADD HRID INT NULL REFERENCES Employees(EmployeeID);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Employees_Department')
BEGIN
    CREATE INDEX IX_Employees_Department ON Employees(DepartmentID);
END;

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Employees_Plant')
BEGIN
    CREATE INDEX IX_Employees_Plant ON Employees(PlantID);
END;
GO
