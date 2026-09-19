"""
Organization Masters (spec Section 6). All are simple code/name masters
with a hierarchy chain Company -> Plant -> Department -> Section, plus
two flat masters (Designation, Grade) and Employee Category.

None support hard delete - IsActive is the only lifecycle control, since
historical performance records may reference any of these (spec Section 35).
"""
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Company(Base):
    __tablename__ = "Companies"

    CompanyID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    CompanyCode: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    CompanyName: Mapped[str] = mapped_column(String(150), nullable=False)
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Added for the company-logo feature (uploaded by HR/Plant Head under
    # the same MASTERS.EDIT permission they already hold for every other
    # master field) - same "path only, never the absolute filesystem
    # path" convention as Employee.ProfilePhotoPath and
    # Attachment.StoredPath, served via GET /masters/companies/{id}/logo.
    LogoPath: Mapped[str | None] = mapped_column(String(255), nullable=True)

    plants: Mapped[list["Plant"]] = relationship(back_populates="company")


class Plant(Base):
    __tablename__ = "Plants"

    PlantID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    CompanyID: Mapped[int] = mapped_column(ForeignKey("Companies.CompanyID"), nullable=False)
    PlantCode: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    PlantName: Mapped[str] = mapped_column(String(150), nullable=False)
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="plants")
    departments: Mapped[list["Department"]] = relationship(back_populates="plant")


class Department(Base):
    __tablename__ = "Departments"

    DepartmentID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    PlantID: Mapped[int] = mapped_column(ForeignKey("Plants.PlantID"), nullable=False)
    DeptCode: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    DeptName: Mapped[str] = mapped_column(String(150), nullable=False)
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)

    plant: Mapped["Plant"] = relationship(back_populates="departments")
    sections: Mapped[list["Section"]] = relationship(back_populates="department")


class Section(Base):
    __tablename__ = "Sections"

    SectionID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    DepartmentID: Mapped[int] = mapped_column(ForeignKey("Departments.DepartmentID"), nullable=False)
    SectionCode: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    SectionName: Mapped[str] = mapped_column(String(150), nullable=False)
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)

    department: Mapped["Department"] = relationship(back_populates="sections")


class Designation(Base):
    __tablename__ = "Designations"

    DesignationID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    DesignationCode: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    DesignationName: Mapped[str] = mapped_column(String(150), nullable=False)
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)


class Grade(Base):
    __tablename__ = "Grades"

    GradeID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    GradeCode: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    GradeName: Mapped[str] = mapped_column(String(100), nullable=False)
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)


class EmployeeCategory(Base):
    __tablename__ = "Employee_Categories"

    EmployeeCategoryID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    CategoryCode: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    CategoryName: Mapped[str] = mapped_column(String(100), nullable=False)
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)
