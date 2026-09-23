"""Tum modeller.

Alembic'in tablolari gorebilmesi icin her model burada import edilmelidir.
"""

from app.models.ai import AICostEvent, AIRun, AITask
from app.models.brand import Brand, BrandGuideline, Campaign
from app.models.content import ContentCalendar, ContentIdea, ContentScript
from app.models.enums import (
    AIProviderName,
    AITaskStatus,
    AutomationStatus,
    AutomationTrigger,
    ContentStatus,
    MediaType,
    Platform,
    ReklamPlatformu,
    ReportPeriod,
    WorkspaceRole,
)
from app.models.identity import User, Workspace, WorkspaceMember
from app.models.izlenen import IzlemeTuru, TrackedAccount
from app.models.kampanya import CampaignPlatform
from app.models.ops import (
    Approval,
    AuditLog,
    Notification,
    SystemError,
    SystemSetting,
    WebhookEvent,
)
from app.models.otomasyon import (
    ApiClient,
    ApiClientWorkspace,
    AutomationRun,
    AutomationSetting,
)
from app.models.reporting import Report, ReportSection
from app.models.research import CompetitorObservation, TrendObservation
from app.models.social import (
    AccountMetrics,
    MediaMetricsNormalized,
    MediaMetricsRaw,
    OAuthCredential,
    PlatformMedia,
    SocialAccount,
)
from app.models.yetki import UserPermission

__all__ = [
    "AICostEvent", "AIProviderName", "AIRun", "AITask", "AITaskStatus",
    "AccountMetrics", "ApiClient", "ApiClientWorkspace", "Approval",
    "AuditLog", "AutomationRun", "AutomationSetting", "AutomationStatus",
    "AutomationTrigger", "Brand", "BrandGuideline",
    "Campaign", "CompetitorObservation", "ContentCalendar",
    "ContentIdea", "ContentScript", "ContentStatus", "MediaMetricsNormalized",
    "MediaMetricsRaw", "MediaType", "Notification", "OAuthCredential",
    "Platform", "PlatformMedia", "Report", "ReportPeriod", "ReportSection", "UserPermission", "TrackedAccount", "IzlemeTuru", "CampaignPlatform",
    "ReklamPlatformu",
    "SocialAccount", "SystemError", "SystemSetting", "TrendObservation", "User", "WebhookEvent",
    "Workspace", "WorkspaceMember", "WorkspaceRole",
]
