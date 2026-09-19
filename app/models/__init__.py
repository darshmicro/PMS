# Import order matters only in the sense that every model must be registered
# on Base.metadata before SQLAlchemy's mapper configuration runs (which
# happens automatically on first use, or explicitly via configure_mappers()
# in tests). Masters are imported before Employee since Employee's FKs
# reference them, though string-based ForeignKey/relationship declarations
# would tolerate either order.
from app.models.masters import (  # noqa: F401
    Company,
    Department,
    Designation,
    EmployeeCategory,
    Grade,
    Plant,
    Section,
)
from app.models.employee import Employee  # noqa: F401
from app.models.performance_masters import (  # noqa: F401
    CompetencyMaster,
    KPAMaster,
    KPIMaster,
    KPIScoringRule,
    PerformanceCycle,
    RatingMaster,
)
from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance  # noqa: F401
from app.models.self_assessment import SelfAssessment  # noqa: F401
from app.models.rbac import Permission, Role, RolePermission, User, UserRole  # noqa: F401
from app.models.manager_review import ManagerReview  # noqa: F401
from app.models.hod_review import HODReview  # noqa: F401
from app.models.hr_review import HRReview  # noqa: F401
from app.models.plant_head_approval import PlantHeadApproval  # noqa: F401
from app.models.md_approval import MDApproval  # noqa: F401
from app.models.employee_competency import EmployeeCompetency  # noqa: F401
from app.models.performance_score import PerformanceRating, PerformanceScore  # noqa: F401
from app.models.workflow_history import WorkflowHistory  # noqa: F401
from app.models.development_plan import DevelopmentPlan  # noqa: F401
from app.models.pip import PIP  # noqa: F401
from app.models.attachment import Attachment  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.system_config import SystemConfig  # noqa: F401
from app.models.demo_credential import DemoCredential  # noqa: F401
