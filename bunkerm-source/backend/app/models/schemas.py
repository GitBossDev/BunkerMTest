"""
Modelos Pydantic para request/response de la API unificada.
Consolida todos los modelos dispersos en los microservicios anteriores.
"""
from __future__ import annotations

import re as _re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# DynSec — clientes, roles, grupos, ACLs
# ---------------------------------------------------------------------------

class ClientCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)

    @field_validator("username")
    @classmethod
    def username_safe(cls, v: str) -> str:
        # Solo caracteres alfanuméricos, guiones, guiones bajos y puntos
        if not _re.fullmatch(r"[A-Za-z0-9_.\-]+", v):
            raise ValueError(
                "Username may only contain letters, numbers, hyphens, underscores, and dots"
            )
        return v


class ClientResponse(BaseModel):
    username: str
    message: str
    success: bool


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    textname: Optional[str] = Field(default=None, max_length=128)
    acls: Optional[List[Dict[str, Any]]] = None
    nonce: Optional[str] = None
    timestamp: Optional[int] = None

    @field_validator("name")
    @classmethod
    def name_safe(cls, v: str) -> str:
        if not _re.fullmatch(r"[A-Za-z0-9_.\-]+", v):
            raise ValueError(
                "Role name may only contain letters, numbers, hyphens, underscores, and dots"
            )
        return v


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    textname: Optional[str] = Field(default=None, max_length=128)
    roles: Optional[List[str]] = None

    @field_validator("name")
    @classmethod
    def name_safe(cls, v: str) -> str:
        if not _re.fullmatch(r"[A-Za-z0-9_.\-]+", v):
            raise ValueError(
                "Group name may only contain letters, numbers, hyphens, underscores, and dots"
            )
        return v


class RoleAssignment(BaseModel):
    role_name: str
    priority: Optional[int] = 1


class GroupClientAssignment(BaseModel):
    client_username: str


class ACLType(str, Enum):
    PUBLISH_CLIENT_SEND = "publishClientSend"
    PUBLISH_CLIENT_RECEIVE = "publishClientReceive"
    SUBSCRIBE_LITERAL = "subscribeLiteral"
    SUBSCRIBE_PATTERN = "subscribePattern"
    UNSUBSCRIBE_LITERAL = "unsubscribeLiteral"
    UNSUBSCRIBE_PATTERN = "unsubscribePattern"


class Permission(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class ACLRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=256)
    aclType: str = Field(..., description="ACL type (publishClientSend or subscribeLiteral)")
    permission: str = Field(..., description="Permission (allow or deny)")

    @field_validator("topic")
    @classmethod
    def topic_safe(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("Topic must not contain NUL characters")
        if v != v.strip():
            raise ValueError("Topic must not have leading/trailing whitespace")
        return v


class DefaultACLConfig(BaseModel):
    publishClientSend: Optional[str] = None
    publishClientReceive: Optional[str] = None
    subscribe: Optional[str] = None
    unsubscribe: Optional[str] = None


VALID_ACL_TYPES: List[str] = [
    "publishClientSend",
    "publishClientReceive",
    "subscribeLiteral",
    "subscribePattern",
    "unsubscribeLiteral",
    "unsubscribePattern",
]


# ---------------------------------------------------------------------------
# Monitor — alertas y configuración
# ---------------------------------------------------------------------------

class AlertConfigUpdate(BaseModel):
    broker_down_grace_polls: Optional[int] = None
    client_capacity_pct: Optional[float] = None
    reconnect_loop_count: Optional[int] = None
    reconnect_loop_window_s: Optional[int] = None
    auth_fail_count: Optional[int] = None
    auth_fail_window_s: Optional[int] = None
    cooldown_minutes: Optional[int] = None


class PublishRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=256)
    payload: str = Field(..., max_length=65536)
    qos: int = Field(default=0, ge=0, le=2)
    retain: bool = False


class NotificationChannelUpsert(BaseModel):
    id: Optional[int] = None
    channelKey: str = Field(..., min_length=1, max_length=64)
    channelType: str = Field(..., min_length=1, max_length=32)
    displayName: str = Field(..., min_length=1, max_length=128)
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)
    secretRef: Optional[str] = Field(default=None, max_length=256)

    @field_validator("channelKey")
    @classmethod
    def channel_key_safe(cls, v: str) -> str:
        if not _re.fullmatch(r"[A-Za-z0-9_.\-]+", v):
            raise ValueError(
                "Channel key may only contain letters, numbers, hyphens, underscores, and dots"
            )
        return v

    @field_validator("channelType")
    @classmethod
    def channel_type_supported(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in {"email", "webhook"}:
            raise ValueError("Channel type must be 'email' or 'webhook'")
        return normalized


class IPWhitelistEntry(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    cidr: str = Field(..., min_length=1, max_length=64)
    scope: str = Field(..., min_length=1, max_length=32)
    description: str = Field(default="", max_length=256)
    enabled: bool = True

    @field_validator("id")
    @classmethod
    def whitelist_entry_id_safe(cls, v: str) -> str:
        if not _re.fullmatch(r"[A-Za-z0-9_.\-]+", v):
            raise ValueError(
                "Whitelist entry id may only contain letters, numbers, hyphens, underscores, and dots"
            )
        return v

    @field_validator("scope")
    @classmethod
    def whitelist_scope_supported(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in {"api_admin", "mqtt_clients"}:
            raise ValueError("Whitelist scope must be 'api_admin' or 'mqtt_clients'")
        return normalized


class IPWhitelistPolicyUpsert(BaseModel):
    mode: str = Field(default="disabled", min_length=1, max_length=16)
    trustedProxies: List[str] = Field(default_factory=list)
    defaultAction: Dict[str, str] = Field(
        default_factory=lambda: {"api_admin": "allow", "mqtt_clients": "allow"}
    )
    entries: List[IPWhitelistEntry] = Field(default_factory=list)
    lastUpdatedBy: Optional[Dict[str, Any]] = None

    @field_validator("mode")
    @classmethod
    def whitelist_mode_supported(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in {"disabled", "audit", "enforce"}:
            raise ValueError("Whitelist mode must be 'disabled', 'audit' or 'enforce'")
        return normalized


# ---------------------------------------------------------------------------
# Config — Mosquitto listeners y TLS
# ---------------------------------------------------------------------------

class Listener(BaseModel):
    port: int
    bind_address: Optional[str] = ""
    per_listener_settings: bool = False
    max_connections: int = 10000
    protocol: Optional[str] = None


class TLSListenerConfig(BaseModel):
    enabled: bool = False
    port: int = 8883
    cafile: Optional[str] = None
    certfile: Optional[str] = None
    keyfile: Optional[str] = None
    require_certificate: bool = False
    tls_version: Optional[str] = None


class MosquittoConfig(BaseModel):
    config: Dict[str, Any]
    listeners: List[Listener] = []
    max_inflight_messages: Optional[int] = None
    max_queued_messages: Optional[int] = None
    tls: Optional[TLSListenerConfig] = None


# ---------------------------------------------------------------------------
# Bridges — AWS y Azure
# ---------------------------------------------------------------------------

class AzureBridgeConfig(BaseModel):
    broker_address: str
    device_id: str
    sas_token: Optional[str] = None
    port: int = 8883
    bridge_name: Optional[str] = None


class AWSBridgeSettings(BaseModel):
    broker_address: str
    client_id: str
    port: int = 8883
    bridge_name: Optional[str] = None
