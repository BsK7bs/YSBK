"""Pydantic models for API schemas.

MongoDB collections use dicts; these Pydantic models are used for request/
response validation and typed access.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Roles ----------
Role = Literal["owner", "admin", "technician", "viewer"]
ROLE_HIERARCHY = {"owner": 4, "admin": 3, "technician": 2, "viewer": 1}


class BaseDoc(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ---------- Organization ----------
class Organization(BaseDoc):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    slug: str | None = None
    logo_url: str | None = None
    timezone: str = "UTC"
    notification_prefs: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OrganizationUpdate(BaseModel):
    name: str | None = None
    logo_url: str | None = None
    timezone: str | None = None
    notification_prefs: dict[str, Any] | None = None


# ---------- User ----------
class User(BaseDoc):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    email: EmailStr
    full_name: str
    role: Role = "viewer"
    is_active: bool = True
    password_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserPublic(BaseDoc):
    id: str
    org_id: str
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool = True
    created_at: datetime | None = None


# ---------- Auth ----------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    organization_name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic
    organization: Organization


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


# ---------- Invitations ----------
class InvitationCreate(BaseModel):
    email: EmailStr
    role: Role = "viewer"


class Invitation(BaseDoc):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    email: EmailStr
    role: Role
    token: str
    invited_by: str
    accepted: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime


class AcceptInvitationRequest(BaseModel):
    token: str
    full_name: str = Field(min_length=1)
    password: str = Field(min_length=8)


# ---------- Enrollment codes ----------
class EnrollmentCode(BaseDoc):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str
    org_id: str
    created_by: str
    label: str | None = None
    used: bool = False
    used_by_device_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime


class EnrollmentCodeCreate(BaseModel):
    label: str | None = None


class EnrollmentCodeResponse(BaseModel):
    id: str
    code: str
    expires_at: datetime
    label: str | None = None
    qr_payload: str


class DeviceEnrollRequest(BaseModel):
    code: str
    hostname: str
    os_name: str | None = None
    os_version: str | None = None
    agent_version: str | None = None
    hardware_id: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    serial_number: str | None = None
    cpu: str | None = None
    ram_gb: float | None = None
    disk_gb: float | None = None
    motherboard: str | None = None
    bios_version: str | None = None


class DeviceEnrollResponse(BaseModel):
    device_id: str
    device_api_key: str
    org_id: str
    ws_url_hint: str


# ---------- Devices ----------
class Device(BaseDoc):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    hostname: str
    display_name: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    agent_version: str | None = None
    hardware_id: str | None = None
    # Extended system info (Computer Management fields)
    ip_address: str | None = None
    mac_address: str | None = None
    serial_number: str | None = None
    cpu: str | None = None
    ram_gb: float | None = None
    disk_gb: float | None = None
    motherboard: str | None = None
    bios_version: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    group_ids: list[str] = Field(default_factory=list)
    # Maintenance mode fields
    maintenance_mode: bool = False
    maintenance_started_at: datetime | None = None
    maintenance_ends_at: datetime | None = None
    maintenance_reason: str | None = None
    maintenance_suppress_alerts: bool = True
    managed: bool = True  # False for manually-registered w/o agent
    has_agent: bool = False  # True if enrolled via agent flow
    api_key_hash: str | None = None
    is_online: bool = False
    last_seen: datetime | None = None
    enrolled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    enrolled_by: str | None = None
    created_via: str = "agent"  # agent | manual
    latest_metrics: dict[str, Any] = Field(default_factory=dict)
    inventory: dict[str, Any] = Field(default_factory=dict)
    health_score: int | None = None
    risk_level: str | None = None  # healthy|warning|high_risk|critical|offline


class DevicePublic(BaseDoc):
    id: str
    org_id: str
    hostname: str
    display_name: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    agent_version: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    serial_number: str | None = None
    cpu: str | None = None
    ram_gb: float | None = None
    disk_gb: float | None = None
    motherboard: str | None = None
    bios_version: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    group_ids: list[str] = Field(default_factory=list)
    maintenance_mode: bool = False
    maintenance_ends_at: datetime | None = None
    maintenance_reason: str | None = None
    has_agent: bool = False
    created_via: str = "agent"
    is_online: bool = False
    last_seen: datetime | None = None
    enrolled_at: datetime | None = None
    latest_metrics: dict[str, Any] = Field(default_factory=dict)
    inventory: dict[str, Any] = Field(default_factory=dict)
    health_score: int | None = None
    risk_level: str | None = None


class ComputerRegisterRequest(BaseModel):
    """Manual computer registration by an admin/technician (no agent required)."""
    hostname: str = Field(min_length=1)
    display_name: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    serial_number: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    cpu: str | None = None
    ram_gb: float | None = None
    disk_gb: float | None = None
    motherboard: str | None = None
    bios_version: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class DeviceUpdate(BaseModel):
    display_name: str | None = None
    hostname: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    serial_number: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    cpu: str | None = None
    ram_gb: float | None = None
    disk_gb: float | None = None
    motherboard: str | None = None
    bios_version: str | None = None
    notes: str | None = None
    tags: list[str] | None = None


class PaginatedDevices(BaseModel):
    items: list[DevicePublic]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------- Telemetry ----------
class TelemetryFrame(BaseModel):
    """WebSocket / REST telemetry payload from the agent."""
    type: str = "metrics"  # heartbeat | metrics | inventory | event
    ts: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    inventory: dict[str, Any] | None = None
    event: dict[str, Any] | None = None


# ---------- Alerts ----------
AlertSeverity = Literal["info", "warning", "high", "critical"]


class Alert(BaseDoc):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    device_id: str
    kind: str  # cpu_high, ram_high, disk_low, temp_high, offline, crash, etc.
    severity: AlertSeverity
    message: str
    value: float | None = None
    threshold: float | None = None
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None


# ---------- Remote Actions ----------
ActionKind = Literal[
    "restart",
    "shutdown",
    "sleep",
    "lock",
    "restart_service",
    "run_script",
    "exec_cmd",
    "exec_powershell",
    "kill_process",
    "install_software",
    "uninstall_software",
    "clear_temp",
    "run_windows_update",
    "download_logs",
    "refresh_inventory",
    # Fleet & remote diagnostics extensions
    "restart_agent",
    "collect_event_logs",
    "collect_diagnostic",
    "collect_crash_dumps",
    # Phase-9 additions (Remote Actions spec)
    "refresh_telemetry",       # push one metrics frame right now
    "refresh_software",        # rebuild the installed-software inventory
    "run_health_check",        # recompute + push the health assessment
    # Future-ready (accepted by the API today, executed by the agent later)
    "remote_desktop",          # spawn an RDP-tunnel session
    "file_transfer",           # push/pull a file to/from the device
    "patch_deployment",        # install a specific KB or curated patch set
]
ActionStatus = Literal["pending", "in_progress", "succeeded", "failed", "cancelled", "expired"]

# Actions that alter machine state / execute arbitrary code — require admin+
# role AND an explicit ``confirm=true`` from the caller.
DESTRUCTIVE_ACTION_KINDS: set[str] = {
    "restart", "shutdown", "sleep", "lock",
    "restart_service", "kill_process",
    "run_script", "exec_cmd", "exec_powershell",
    "install_software", "uninstall_software",
    "clear_temp", "run_windows_update",
    "restart_agent",
    # Phase-9 future-ready — treat as destructive so operators must confirm.
    "remote_desktop", "file_transfer", "patch_deployment",
}


class RemoteAction(BaseDoc):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    device_id: str
    kind: ActionKind
    params: dict[str, Any] = Field(default_factory=dict)
    status: ActionStatus = "pending"
    created_by: str
    created_by_email: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    # Bulk / batch tracking
    batch_id: str | None = None
    parent_action_id: str | None = None  # set when created via retry
    retry_of: str | None = None  # legacy alias


class RemoteActionCreate(BaseModel):
    kind: ActionKind
    params: dict[str, Any] = Field(default_factory=dict)
    confirm: bool = False
    ttl_seconds: int = Field(default=900, ge=30, le=3600)


# --- Bulk actions ---
class BulkActionCreate(BaseModel):
    kind: ActionKind
    params: dict[str, Any] = Field(default_factory=dict)
    device_ids: list[str] = Field(default_factory=list, min_length=1, max_length=500)
    group_ids: list[str] = Field(default_factory=list)  # OR-combined with device_ids
    confirm: bool = False
    ttl_seconds: int = Field(default=900, ge=30, le=3600)
    label: str | None = None


class ActionBatch(BaseDoc):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    kind: ActionKind
    params: dict[str, Any] = Field(default_factory=dict)
    label: str | None = None
    created_by: str
    created_by_email: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total: int = 0
    device_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)


# ---------- Device Groups ----------
class DeviceGroup(BaseDoc):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    name: str = Field(min_length=1, max_length=80)
    description: str | None = None
    color: str | None = None  # tailwind-friendly color name for badge
    icon: str | None = None
    created_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


class DeviceGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = None
    color: str | None = None
    icon: str | None = None


class DeviceGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None


class DeviceGroupAssignRequest(BaseModel):
    device_ids: list[str] = Field(min_length=1)


# ---------- Maintenance Mode ----------
class MaintenanceEnableRequest(BaseModel):
    duration_minutes: int = Field(default=60, ge=1, le=60 * 24 * 30)
    reason: str | None = None
    suppress_alerts: bool = True


class ActionUpdate(BaseModel):
    status: ActionStatus
    result: dict[str, Any] | None = None
    error: str | None = None


# ---------- Audit ----------
class AuditEvent(BaseDoc):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    actor_id: str | None = None
    actor_email: str | None = None
    kind: str
    target: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
