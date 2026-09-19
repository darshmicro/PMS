"""
Employee model.

History note: M1/M2 introduced this with only the columns needed for
AD-mapping/RBAC (EmployeeCode, ADUsername, name/contact, manager/HOD
self-reference, employment status). M4 (this revision) adds the
remaining Employee Master fields from spec Section 6 - Department,
Section, Designation, Grade, Plant, Date of Joining, and an HR contact -
now that M3 has created those master tables. All new columns are
nullable so the migration is additive over existing rows (e.g. the
bootstrap System Administrator created during M1/M2 setup).
"""
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Employee(Base):
    __tablename__ = "Employees"

    EmployeeID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    EmployeeCode: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    ADUsername: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    FullName: Mapped[str] = mapped_column(String(150), nullable=False)
    Email: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # --- Added in M4 (Employee Master, spec Section 6) ---
    DepartmentID: Mapped[int | None] = mapped_column(ForeignKey("Departments.DepartmentID"), nullable=True)
    SectionID: Mapped[int | None] = mapped_column(ForeignKey("Sections.SectionID"), nullable=True)
    DesignationID: Mapped[int | None] = mapped_column(ForeignKey("Designations.DesignationID"), nullable=True)
    GradeID: Mapped[int | None] = mapped_column(ForeignKey("Grades.GradeID"), nullable=True)
    PlantID: Mapped[int | None] = mapped_column(ForeignKey("Plants.PlantID"), nullable=True)
    EmployeeCategoryID: Mapped[int | None] = mapped_column(
        ForeignKey("Employee_Categories.EmployeeCategoryID"), nullable=True
    )
    DateOfJoining: Mapped[date | None] = mapped_column(Date, nullable=True)
    HRID: Mapped[int | None] = mapped_column(ForeignKey("Employees.EmployeeID"), nullable=True)

    # --- Added for the profile-photo feature: stores the on-disk filename
    # under attachment_service.storage_root() (never the absolute path,
    # same convention as Attachment.StoredPath) - null means no photo
    # uploaded yet, and profile_service.employee_photo_url() is the single
    # place that turns this into a servable URL. ---
    ProfilePhotoPath: Mapped[str | None] = mapped_column(String(255), nullable=True)

    ManagerID: Mapped[int | None] = mapped_column(ForeignKey("Employees.EmployeeID"), nullable=True)
    HODID: Mapped[int | None] = mapped_column(ForeignKey("Employees.EmployeeID"), nullable=True)

    EmploymentStatus: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)

    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    manager: Mapped["Employee | None"] = relationship(
        "Employee", remote_side=[EmployeeID], foreign_keys=[ManagerID]
    )
    hod: Mapped["Employee | None"] = relationship(
        "Employee", remote_side=[EmployeeID], foreign_keys=[HODID]
    )
    hr_contact: Mapped["Employee | None"] = relationship(
        "Employee", remote_side=[EmployeeID], foreign_keys=[HRID]
    )
    department: Mapped["Department | None"] = relationship("Department", foreign_keys=[DepartmentID])
    section: Mapped["Section | None"] = relationship("Section", foreign_keys=[SectionID])
    designation: Mapped["Designation | None"] = relationship("Designation", foreign_keys=[DesignationID])
    grade: Mapped["Grade | None"] = relationship("Grade", foreign_keys=[GradeID])
    plant: Mapped["Plant | None"] = relationship("Plant", foreign_keys=[PlantID])
    employee_category: Mapped["EmployeeCategory | None"] = relationship(
        "EmployeeCategory", foreign_keys=[EmployeeCategoryID]
    )
    user: Mapped["User | None"] = relationship("User", back_populates="employee", uselist=False)
