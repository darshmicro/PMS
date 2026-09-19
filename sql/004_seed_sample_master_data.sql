/*
    SAMPLE / TEST DATA - remove before go-live (spec Section 46).
    Every row below is tagged with code prefix 'SAMPLE-' or drawn from the
    department list the spec names, so it's easy to identify and purge.
*/

INSERT INTO Companies (CompanyCode, CompanyName, IsActive)
SELECT 'SAMPLE-CO1', 'Sample Biologics Ltd', 1
WHERE NOT EXISTS (SELECT 1 FROM Companies WHERE CompanyCode = 'SAMPLE-CO1');

INSERT INTO Plants (CompanyID, PlantCode, PlantName, IsActive)
SELECT c.CompanyID, 'SAMPLE-PLT1', 'Sample Plant - Unit 1', 1
FROM Companies c WHERE c.CompanyCode = 'SAMPLE-CO1'
AND NOT EXISTS (SELECT 1 FROM Plants WHERE PlantCode = 'SAMPLE-PLT1');

INSERT INTO Departments (PlantID, DeptCode, DeptName, IsActive)
SELECT p.PlantID, v.DeptCode, v.DeptName, 1
FROM Plants p
CROSS JOIN (VALUES
    ('SAMPLE-DPT-PROD', 'Production'),
    ('SAMPLE-DPT-QA',   'Quality Assurance'),
    ('SAMPLE-DPT-QC',   'Quality Control'),
    ('SAMPLE-DPT-ENG',  'Engineering'),
    ('SAMPLE-DPT-WH',   'Warehouse'),
    ('SAMPLE-DPT-RND',  'R&D'),
    ('SAMPLE-DPT-RA',   'Regulatory Affairs'),
    ('SAMPLE-DPT-MICRO','Microbiology'),
    ('SAMPLE-DPT-HR',   'HR'),
    ('SAMPLE-DPT-FIN',  'Finance'),
    ('SAMPLE-DPT-COMM', 'Commercial'),
    ('SAMPLE-DPT-IT',   'IT')
) AS v(DeptCode, DeptName)
WHERE p.PlantCode = 'SAMPLE-PLT1'
AND NOT EXISTS (SELECT 1 FROM Departments WHERE DeptCode = v.DeptCode);

INSERT INTO Designations (DesignationCode, DesignationName, IsActive)
SELECT v.Code, v.Name, 1
FROM (VALUES
    ('SAMPLE-DSG-EXEC', 'Executive'),
    ('SAMPLE-DSG-SR',   'Senior Executive'),
    ('SAMPLE-DSG-MGR',  'Manager'),
    ('SAMPLE-DSG-SRMGR','Senior Manager'),
    ('SAMPLE-DSG-HOD',  'Head of Department'),
    ('SAMPLE-DSG-PH',   'Plant Head'),
    ('SAMPLE-DSG-MD',   'Managing Director')
) AS v(Code, Name)
WHERE NOT EXISTS (SELECT 1 FROM Designations WHERE DesignationCode = v.Code);

INSERT INTO Grades (GradeCode, GradeName, IsActive)
SELECT v.Code, v.Name, 1
FROM (VALUES ('SAMPLE-G1','Grade 1'), ('SAMPLE-G2','Grade 2'), ('SAMPLE-G3','Grade 3'), ('SAMPLE-G4','Grade 4')) AS v(Code, Name)
WHERE NOT EXISTS (SELECT 1 FROM Grades WHERE GradeCode = v.Code);

INSERT INTO Employee_Categories (CategoryCode, CategoryName, IsActive)
SELECT v.Code, v.Name, 1
FROM (VALUES ('SAMPLE-PERM','Permanent'), ('SAMPLE-CONT','Contract'), ('SAMPLE-PROB','Probation')) AS v(Code, Name)
WHERE NOT EXISTS (SELECT 1 FROM Employee_Categories WHERE CategoryCode = v.Code);
GO
