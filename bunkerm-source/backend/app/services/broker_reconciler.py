"""Aplicación efectiva de cambios al broker para el control-plane transicional."""
from __future__ import annotations

import base64
import json
import os
import shutil
from datetime import datetime
from typing import Any, Dict, List

from config.dynsec_config import validate_dynsec_json
from config.mosquitto_config import _signal_mosquitto_reload, _signal_mosquitto_restart
from core.config import settings
from services import monitor_service
from services.broker_runtime import BrokerRuntimePort, _signal_dynsec_reload, get_local_broker_runtime

_MOSQUITTO_CONF_PATH: str = settings.mosquitto_conf_path
_BACKUP_DIR: str = settings.mosquitto_conf_backup_dir
_MOSQUITTO_PASSWD_PATH: str = settings.mosquitto_passwd_path
_CERTS_DIR: str = settings.mosquitto_certs_dir
_ALLOWED_CERT_EXTENSIONS = {".pem", ".crt", ".cer", ".key"}


class _ModuleConfiguredBrokerRuntime:
    """Runtime por defecto que mantiene compatibilidad con monkeypatches de módulo."""

    @property
    def mosquitto_conf_path(self) -> str:
        return _MOSQUITTO_CONF_PATH

    @property
    def mosquitto_conf_backup_dir(self) -> str:
        return _BACKUP_DIR

    @property
    def mosquitto_passwd_path(self) -> str:
        return _MOSQUITTO_PASSWD_PATH

    @property
    def mosquitto_certs_dir(self) -> str:
        return _CERTS_DIR

    def locked_dynsec(self):
        return get_local_broker_runtime().locked_dynsec()

    def read_dynsec(self) -> Dict[str, Any]:
        return get_local_broker_runtime().read_dynsec()

    def write_dynsec(self, data: Dict[str, Any]) -> None:
        get_local_broker_runtime().write_dynsec(data)

    def execute_dynsec_command(self, subcommand: List[str]) -> Dict[str, Any]:
        return get_local_broker_runtime().execute_dynsec_command(subcommand)

    def signal_mosquitto_reload(self) -> None:
        _signal_mosquitto_reload()

    def signal_mosquitto_restart(self) -> None:
        _signal_mosquitto_restart()

    def signal_dynsec_reload(self) -> None:
        _signal_dynsec_reload()


class BrokerReconciler:
    """Encapsula la mutación efectiva del broker y su filesystem."""

    def __init__(self, runtime: BrokerRuntimePort | None = None) -> None:
        self.runtime = runtime or _ModuleConfiguredBrokerRuntime()

    @staticmethod
    def _permission_from_acl(entry: Dict[str, Any]) -> str:
        return "allow" if bool(entry.get("allow", False)) else "deny"

    @staticmethod
    def _acl_key(entry: Dict[str, Any]) -> tuple[str, str]:
        return str(entry.get("acltype", "")), str(entry.get("topic", ""))

    @staticmethod
    def _client_role_priority(entry: Dict[str, Any]) -> int:
        priority = entry.get("priority", 1)
        return int(priority if priority is not None else 1)

    @staticmethod
    def _command_error(prefix: str, result: Dict[str, Any]) -> str | None:
        if result["success"]:
            return None
        return f"{prefix}: {result['error_output']}"

    def _rollback_client_commands(self, rollback_commands: List[tuple[List[str], str]]) -> List[str]:
        rollback_errors: List[str] = []
        for command, prefix in reversed(rollback_commands):
            result = self.runtime.execute_dynsec_command(command)
            error = self._command_error(prefix, result)
            if error:
                rollback_errors.append(error)
        return rollback_errors

    @staticmethod
    def _group_client_priority(entry: Dict[str, Any]) -> int:
        priority = entry.get("priority", 0)
        return int(priority if priority is not None else 0)

    def apply_default_acl(self, desired: Dict[str, bool]) -> List[str]:
        errors: List[str] = []
        observed_before = self.get_observed_default_acl()

        if observed_before == desired:
            return errors

        for acl_type, allow in desired.items():
            result = self.runtime.execute_dynsec_command(
                ["setDefaultACLAccess", acl_type, "allow" if allow else "deny"]
            )
            if not result["success"]:
                errors.append(f"{acl_type}: {result['error_output']}")

        if not errors:
            with self.runtime.locked_dynsec():
                data = self.runtime.read_dynsec()
                data["defaultACLAccess"] = desired
                self.runtime.write_dynsec(data)

        return errors

    def signal_mosquitto_reload(self) -> List[str]:
        try:
            self.runtime.signal_mosquitto_reload()
            return []
        except Exception as exc:
            return [f"signalMosquittoReload: {exc}"]

    def signal_mosquitto_restart(self) -> List[str]:
        try:
            self.runtime.signal_mosquitto_restart()
            monitor_service.invalidate_max_connections_cache()
            return []
        except Exception as exc:
            return [f"signalMosquittoRestart: {exc}"]

    def apply_client_projection(
        self,
        username: str,
        desired: Dict[str, Any],
        creation_password: str | None = None,
    ) -> List[str]:
        errors: List[str] = []
        rollback_commands: List[tuple[List[str], str]] = []
        with self.runtime.locked_dynsec():
            data = self.runtime.read_dynsec()
            client = self._find_client(data, username)
            if desired["deleted"]:
                if client is not None:
                    result = self.runtime.execute_dynsec_command(["deleteClient", username])
                    error = self._command_error(f"deleteClient:{username}", result)
                    if error:
                        return [error]
                data["clients"] = [
                    entry for entry in data.get("clients", [])
                    if entry.get("username") != username
                ]
                try:
                    self.runtime.write_dynsec(data)
                except Exception as exc:
                    return [f"writeDynsec:{username}: {exc}"]
                return errors

            if client is None:
                if not creation_password:
                    return [f"createClient:{username}: password required for unmanaged client creation"]
                result = self.runtime.execute_dynsec_command(
                    ["createClient", username, "-p", creation_password]
                )
                error = self._command_error(f"createClient:{username}", result)
                if error:
                    return [error]
                rollback_commands.append((["deleteClient", username], f"rollbackDeleteClient:{username}"))
                client = {"username": username}
                data.setdefault("clients", []).append(client)

            observed_disabled = bool(client.get("disabled", False))
            desired_disabled = bool(desired.get("disabled", False))
            if observed_disabled != desired_disabled:
                command = ["disableClient", username] if desired_disabled else ["enableClient", username]
                error = self._command_error(
                    f"{command[0]}:{username}",
                    self.runtime.execute_dynsec_command(command),
                )
                if error:
                    return [error]
                rollback_command = ["enableClient", username] if desired_disabled else ["disableClient", username]
                rollback_commands.append((rollback_command, f"rollback{rollback_command[0]}:{username}"))

            observed_roles = {
                str(entry.get("rolename")): self._client_role_priority(entry)
                for entry in client.get("roles", [])
                if entry.get("rolename")
            }
            desired_roles = {
                str(entry.get("rolename")): self._client_role_priority(entry)
                for entry in desired.get("roles", [])
                if entry.get("rolename")
            }

            for role_name, observed_priority in observed_roles.items():
                desired_priority = desired_roles.get(role_name)
                if desired_priority == observed_priority:
                    continue
                error = self._command_error(
                    f"removeClientRole:{username}:{role_name}",
                    self.runtime.execute_dynsec_command(["removeClientRole", username, role_name]),
                )
                if error:
                    return [error]
                rollback_commands.append(
                    (
                        ["addClientRole", username, role_name, str(observed_priority)],
                        f"rollbackAddClientRole:{username}:{role_name}",
                    )
                )

            for role_name, desired_priority in desired_roles.items():
                observed_priority = observed_roles.get(role_name)
                if observed_priority == desired_priority:
                    continue
                error = self._command_error(
                    f"addClientRole:{username}:{role_name}",
                    self.runtime.execute_dynsec_command(
                        ["addClientRole", username, role_name, str(desired_priority)]
                    ),
                )
                if error:
                    return [error]
                rollback_commands.append(
                    (
                        ["removeClientRole", username, role_name],
                        f"rollbackRemoveClientRole:{username}:{role_name}",
                    )
                )

            client["username"] = desired["username"]
            client["textname"] = desired["textname"]
            client["disabled"] = desired_disabled
            client["roles"] = desired["roles"]
            client["groups"] = desired["groups"]

            try:
                self.runtime.write_dynsec(data)
            except Exception as exc:
                errors.append(f"writeDynsec:{username}: {exc}")
                errors.extend(self._rollback_client_commands(rollback_commands))
                return errors

        return errors

    def apply_role_projection(self, role_name: str, desired: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        with self.runtime.locked_dynsec():
            data = self.runtime.read_dynsec()
            role = self._find_role(data, role_name)

            if desired["deleted"]:
                if role is not None:
                    result = self.runtime.execute_dynsec_command(["deleteRole", role_name])
                    if not result["success"]:
                        errors.append(f"deleteRole:{role_name}: {result['error_output']}")
                        return errors
                data["roles"] = [
                    entry for entry in data.get("roles", [])
                    if entry.get("rolename") != role_name
                ]
            else:
                if role is None:
                    result = self.runtime.execute_dynsec_command(["createRole", role_name])
                    if not result["success"]:
                        errors.append(f"createRole:{role_name}: {result['error_output']}")
                        return errors
                    role = {"rolename": role_name}
                    data.setdefault("roles", []).append(role)

                observed_acls = {
                    self._acl_key(entry): entry
                    for entry in role.get("acls", [])
                    if entry.get("acltype") and entry.get("topic")
                }
                desired_acls = {
                    self._acl_key(entry): entry
                    for entry in desired.get("acls", [])
                    if entry.get("acltype") and entry.get("topic")
                }

                for acl_key, observed_entry in observed_acls.items():
                    desired_entry = desired_acls.get(acl_key)
                    if desired_entry and self._permission_from_acl(desired_entry) == self._permission_from_acl(observed_entry):
                        continue
                    result = self.runtime.execute_dynsec_command(
                        ["removeRoleACL", role_name, acl_key[0], acl_key[1]]
                    )
                    if not result["success"]:
                        errors.append(f"removeRoleACL:{role_name}:{acl_key[0]}:{acl_key[1]}: {result['error_output']}")
                        return errors

                for acl_key, desired_entry in desired_acls.items():
                    observed_entry = observed_acls.get(acl_key)
                    if observed_entry and self._permission_from_acl(observed_entry) == self._permission_from_acl(desired_entry):
                        continue
                    result = self.runtime.execute_dynsec_command(
                        [
                            "addRoleACL",
                            role_name,
                            acl_key[0],
                            acl_key[1],
                            self._permission_from_acl(desired_entry),
                        ]
                    )
                    if not result["success"]:
                        errors.append(f"addRoleACL:{role_name}:{acl_key[0]}:{acl_key[1]}: {result['error_output']}")
                        return errors

                role["rolename"] = desired["rolename"]
                role["acls"] = desired["acls"]
            self.runtime.write_dynsec(data)
        return errors

    def apply_group_projection(self, group_name: str, desired: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        with self.runtime.locked_dynsec():
            data = self.runtime.read_dynsec()
            group = self._find_group(data, group_name)
            if desired["deleted"]:
                if group is not None:
                    result = self.runtime.execute_dynsec_command(["deleteGroup", group_name])
                    if not result["success"]:
                        errors.append(f"deleteGroup:{group_name}: {result['error_output']}")
                        return errors
                data["groups"] = [
                    entry for entry in data.get("groups", [])
                    if entry.get("groupname") != group_name
                ]
            else:
                if group is None:
                    result = self.runtime.execute_dynsec_command(["createGroup", group_name])
                    if not result["success"]:
                        errors.append(f"createGroup:{group_name}: {result['error_output']}")
                        return errors
                    group = {"groupname": group_name}
                    data.setdefault("groups", []).append(group)

                observed_roles = {
                    str(entry.get("rolename")): entry
                    for entry in group.get("roles", [])
                    if entry.get("rolename")
                }
                desired_roles = {
                    str(entry.get("rolename")): entry
                    for entry in desired.get("roles", [])
                    if entry.get("rolename")
                }

                for role_key in observed_roles:
                    if role_key in desired_roles:
                        continue
                    result = self.runtime.execute_dynsec_command(["removeGroupRole", group_name, role_key])
                    if not result["success"]:
                        errors.append(f"removeGroupRole:{group_name}:{role_key}: {result['error_output']}")
                        return errors

                for role_key in desired_roles:
                    if role_key in observed_roles:
                        continue
                    result = self.runtime.execute_dynsec_command(["addGroupRole", group_name, role_key])
                    if not result["success"]:
                        errors.append(f"addGroupRole:{group_name}:{role_key}: {result['error_output']}")
                        return errors

                observed_clients = {
                    str(entry.get("username")): self._group_client_priority(entry)
                    for entry in group.get("clients", [])
                    if entry.get("username")
                }
                desired_clients = {
                    str(entry.get("username")): self._group_client_priority(entry)
                    for entry in desired.get("clients", [])
                    if entry.get("username")
                }

                for username, observed_priority in observed_clients.items():
                    desired_priority = desired_clients.get(username)
                    if desired_priority == observed_priority:
                        continue
                    result = self.runtime.execute_dynsec_command(
                        ["removeGroupClient", group_name, username]
                    )
                    if not result["success"]:
                        errors.append(f"removeGroupClient:{group_name}:{username}: {result['error_output']}")
                        return errors

                for username, desired_priority in desired_clients.items():
                    observed_priority = observed_clients.get(username)
                    if observed_priority == desired_priority:
                        continue
                    command = ["addGroupClient", group_name, username]
                    if desired_priority > 0:
                        command.extend(["--priority", str(desired_priority)])
                    result = self.runtime.execute_dynsec_command(command)
                    if not result["success"]:
                        errors.append(f"addGroupClient:{group_name}:{username}: {result['error_output']}")
                        return errors

                group["groupname"] = desired["groupname"]
                group["roles"] = desired["roles"]
                group["clients"] = desired["clients"]
            self.runtime.write_dynsec(data)
        return errors

    def apply_mosquitto_config(self, rendered_content: str) -> Dict[str, Any]:
        os.makedirs(self.runtime.mosquitto_conf_backup_dir, exist_ok=True)
        previous_content = self.read_mosquitto_content()
        rollback_note: str | None = None
        errors: List[str] = []

        try:
            if os.path.exists(self.runtime.mosquitto_conf_path):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = os.path.join(self.runtime.mosquitto_conf_backup_dir, f"mosquitto.conf.bak.{timestamp}")
                shutil.copy2(self.runtime.mosquitto_conf_path, backup_path)

            with open(self.runtime.mosquitto_conf_path, "w", encoding="utf-8") as handle:
                handle.write(rendered_content)
            os.chmod(self.runtime.mosquitto_conf_path, 0o644)
            self.runtime.signal_mosquitto_restart()
            monitor_service.invalidate_max_connections_cache()
        except Exception as exc:
            errors.append(str(exc))
            if previous_content:
                try:
                    with open(self.runtime.mosquitto_conf_path, "w", encoding="utf-8") as handle:
                        handle.write(previous_content)
                    os.chmod(self.runtime.mosquitto_conf_path, 0o644)
                    self.runtime.signal_mosquitto_restart()
                    monitor_service.invalidate_max_connections_cache()
                    rollback_note = "rollback applied"
                except Exception as rollback_exc:
                    rollback_note = f"rollback failed: {rollback_exc}"

        return {
            "errors": errors,
            "rollbackNote": rollback_note,
        }

    def apply_mosquitto_passwd(self, rendered_content: str) -> Dict[str, Any]:
        parent_dir = os.path.dirname(self.runtime.mosquitto_passwd_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        previous_exists = os.path.exists(self.runtime.mosquitto_passwd_path)
        previous_content = self.read_mosquitto_passwd_content()
        rollback_note: str | None = None
        errors: List[str] = []

        try:
            if previous_exists:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{self.runtime.mosquitto_passwd_path}.bak.{timestamp}"
                shutil.copy2(self.runtime.mosquitto_passwd_path, backup_path)

            with open(self.runtime.mosquitto_passwd_path, "w", encoding="utf-8") as handle:
                handle.write(rendered_content)
            os.chmod(self.runtime.mosquitto_passwd_path, 0o644)
            self.runtime.signal_mosquitto_reload()
        except Exception as exc:
            errors.append(str(exc))
            try:
                if previous_exists:
                    with open(self.runtime.mosquitto_passwd_path, "w", encoding="utf-8") as handle:
                        handle.write(previous_content)
                    os.chmod(self.runtime.mosquitto_passwd_path, 0o644)
                elif os.path.exists(self.runtime.mosquitto_passwd_path):
                    os.remove(self.runtime.mosquitto_passwd_path)
                self.runtime.signal_mosquitto_reload()
                rollback_note = "rollback applied"
            except Exception as rollback_exc:
                rollback_note = f"rollback failed: {rollback_exc}"

        return {
            "errors": errors,
            "rollbackNote": rollback_note,
        }

    def apply_tls_cert_store(self, desired_entries: List[Dict[str, Any]]) -> List[str]:
        os.makedirs(self.runtime.mosquitto_certs_dir, exist_ok=True)
        rollback_snapshots: Dict[str, bytes | None] = {}
        errors: List[str] = []

        for entry in desired_entries:
            filename = entry["filename"]
            path = os.path.join(self.runtime.mosquitto_certs_dir, filename)
            extension = os.path.splitext(filename)[1].lower()
            if extension not in _ALLOWED_CERT_EXTENSIONS:
                errors.append(f"invalid extension for {filename}")
                break
            if not os.path.abspath(path).startswith(os.path.abspath(self.runtime.mosquitto_certs_dir)):
                errors.append(f"invalid path for {filename}")
                break

            if filename not in rollback_snapshots:
                rollback_snapshots[filename] = open(path, "rb").read() if os.path.exists(path) else None

            try:
                if entry.get("deleted", False):
                    if os.path.exists(path):
                        os.remove(path)
                    continue

                content_base64 = entry.get("contentBase64")
                if not isinstance(content_base64, str) or not content_base64:
                    errors.append(f"missing content for {filename}")
                    break
                content = base64.b64decode(content_base64.encode("ascii"))
                with open(path, "wb") as handle:
                    handle.write(content)
                os.chmod(path, 0o640)
            except Exception as exc:
                errors.append(f"{filename}: {exc}")
                break

        if errors:
            for filename, previous_content in rollback_snapshots.items():
                path = os.path.join(self.runtime.mosquitto_certs_dir, filename)
                try:
                    if previous_content is None:
                        if os.path.exists(path):
                            os.remove(path)
                    else:
                        with open(path, "wb") as handle:
                            handle.write(previous_content)
                        os.chmod(path, 0o640)
                except Exception:
                    pass

        return errors

    def apply_dynsec_config(self, desired_data: Dict[str, Any]) -> Dict[str, Any]:
        rollback_note: str | None = None
        errors: List[str] = []

        try:
            validate_dynsec_json(desired_data)
        except ValueError as exc:
            return {
                "errors": [f"invalid dynsec config: {exc}"],
                "rollbackNote": rollback_note,
            }

        with self.runtime.locked_dynsec():
            observed_before = self.runtime.read_dynsec()
            if observed_before == desired_data:
                return {"errors": errors, "rollbackNote": rollback_note}

            try:
                self.runtime.write_dynsec(desired_data)
                self.runtime.signal_dynsec_reload()
            except Exception as exc:
                errors.append(str(exc))
                try:
                    self.runtime.write_dynsec(observed_before)
                    self.runtime.signal_dynsec_reload()
                    rollback_note = "rollback applied"
                except Exception as rollback_exc:
                    rollback_note = f"rollback failed: {rollback_exc}"

        return {
            "errors": errors,
            "rollbackNote": rollback_note,
        }

    def read_mosquitto_content(self) -> str:
        if not os.path.exists(self.runtime.mosquitto_conf_path):
            return ""
        with open(self.runtime.mosquitto_conf_path, "r", encoding="utf-8") as handle:
            return handle.read()

    def read_mosquitto_passwd_content(self) -> str:
        if not os.path.exists(self.runtime.mosquitto_passwd_path):
            return ""
        with open(self.runtime.mosquitto_passwd_path, "r", encoding="utf-8") as handle:
            return handle.read()

    def get_observed_default_acl(self) -> Dict[str, bool]:
        data = self.runtime.read_dynsec()
        source = data.get("defaultACLAccess", {})
        return {
            "publishClientSend": bool(source.get("publishClientSend", True)),
            "publishClientReceive": bool(source.get("publishClientReceive", True)),
            "subscribe": bool(source.get("subscribe", True)),
            "unsubscribe": bool(source.get("unsubscribe", True)),
        }

    @staticmethod
    def _find_client(data: Dict[str, Any], username: str) -> Dict[str, Any] | None:
        for client in data.get("clients", []):
            if client.get("username") == username:
                return client
        return None

    @staticmethod
    def _find_role(data: Dict[str, Any], role_name: str) -> Dict[str, Any] | None:
        for role in data.get("roles", []):
            if role.get("rolename") == role_name:
                return role
        return None

    @staticmethod
    def _find_group(data: Dict[str, Any], group_name: str) -> Dict[str, Any] | None:
        for group in data.get("groups", []):
            if group.get("groupname") == group_name:
                return group
        return None
