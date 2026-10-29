"""Tool registry and starter tool implementations (Agent.md §10).

Tools are registered code modules. Each tool has:
  - stable identifier
  - human-readable description
  - strict input schema
  - strict result schema
  - risk level
  - permission category
  - timeout
  - dry-run capability where meaningful
  - audit behavior

The model can propose a tool call; the policy engine decides allow/deny/
require_approval; only trusted application code executes tools.

No arbitrary shell, eval, PowerShell, Bash, arbitrary executable paths, hidden
persistence, credential extraction, raw browser-profile access, unrestricted
filesystem access, or security-control modification.
"""

from __future__ import annotations

import os
import platform
import shutil
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import psutil  # type: ignore[import-untyped]

from jarvis.policy.engine import RiskLevel

# Workspace root for file tools. Constrained to user-selected workspaces.
# Defaults to the repository root; operators must point this at a real user
# workspace before enabling file write tools.
ALLOWED_WORKSPACE = os.path.abspath(os.environ.get("JARVIS_WORKSPACE", os.getcwd()))

# Application allowlist for open_application (never arbitrary executables).
ALLOWED_APPLICATIONS: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "explorer": "explorer.exe",
}

# Max search results to return from search_allowed_files.
MAX_SEARCH_RESULTS = 100


ToolVerdict = Literal["done", "unverified", "failed", "ask", "started"]
"""Outcome verdict for a tool execution.

- done: it happened, and it was checked — never assumed from a return code.
- unverified: the request went out and the result could not be confirmed.
  Never spoken as a success.
- failed: it did not happen, and here is why.
- ask: nothing was done; doing it would have been a guess.
- started: it is under way; the outcome follows separately.
"""


@dataclass(frozen=True)
class ToolResult:
    tool_id: str
    ok: bool
    result: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    message: str | None = None
    duration_ms: float = 0.0
    verdict: ToolVerdict | None = None

    def __post_init__(self) -> None:
        if self.verdict is None:
            object.__setattr__(self, "verdict", "done" if self.ok else "failed")


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    description: str
    input_schema: dict[str, Any]
    result_schema: dict[str, Any]
    risk_level: RiskLevel
    permission_category: str
    timeout_s: float
    dry_run: bool = False
    audit: bool = True


class Tool(ABC):
    """Base class for registered tools."""

    def __init__(self, definition: ToolDefinition) -> None:
        self.definition = definition

    @abstractmethod
    def execute(self, args: dict[str, Any]) -> ToolResult:
        ...


# ── path safety (filesystem tools) --------------------------------------


def _canonicalize(path: str) -> str:
    """Return the absolute, realpath-resolved, normalized path."""
    return os.path.realpath(os.path.abspath(path))


def _is_within_workspace(path: str, workspace: str) -> bool:
    """True if `path` is inside `workspace` (no traversal or symlink escape)."""
    canon = _canonicalize(path)
    ws = _canonicalize(workspace)
    # Must be equal to or strictly within the workspace.
    return canon == ws or canon.startswith(ws + os.sep)


def _validate_path(path: str, workspace: str = ALLOWED_WORKSPACE) -> str:
    """Validate and canonicalize a path; reject traversal/symlink escapes."""
    canon = _canonicalize(path)
    if not _is_within_workspace(canon, workspace):
        _msg = f"path outside allowed workspace: {path}"
        raise ValueError(_msg)
    return canon


# ── registry ------------------------------------------------------------


class ToolRegistry:
    """Registers and executes tools. Only trusted app code calls execute()."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.definition.id] = tool

    def get(self, tool_id: str) -> Tool | None:
        return self._tools.get(tool_id)

    def list_tools(self) -> list[ToolDefinition]:
        return [t.definition for t in self._tools.values()]

    def execute(self, tool_id: str, args: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(tool_id)
        if tool is None:
            return ToolResult(
                tool_id=tool_id,
                ok=False,
                error_code="unknown_tool",
                message=f"unknown tool: {tool_id}",
            )
        start = datetime.now(UTC)
        try:
            result = tool.execute(args)
        except Exception as exc:  # noqa: BLE001 — tool errors are captured
            duration = (datetime.now(UTC) - start).total_seconds() * 1000
            return ToolResult(
                tool_id=tool_id,
                ok=False,
                error_code="tool_error",
                message=str(exc),
                duration_ms=duration,
            )
        duration = (datetime.now(UTC) - start).total_seconds() * 1000
        return ToolResult(
            tool_id=tool_id,
            ok=result.ok,
            result=result.result,
            error_code=result.error_code,
            message=result.message,
            duration_ms=duration,
            verdict=result.verdict,
        )


# ── starter tools -------------------------------------------------------


class GetCurrentDateTime(Tool):
    """Level 0: current date/time (read-only calculation)."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        now = datetime.now(UTC)
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={
                "utc_iso": now.isoformat(),
                "local_iso": datetime.now().astimezone().isoformat(),
                "timestamp": now.timestamp(),
            },
        )


class GetSystemInformation(Tool):
    """Level 1: read-only system information."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
                "hostname": platform.node(),
            },
        )


class GetCpuMemoryDiskStatus(Tool):
    """Level 1: read-only CPU/memory/disk status."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(ALLOWED_WORKSPACE)
            return ToolResult(
                tool_id=self.definition.id,
                ok=True,
                result={
                    "cpu_percent": cpu_percent,
                    "memory_total": mem.total,
                    "memory_available": mem.available,
                    "memory_percent": mem.percent,
                    "disk_total": disk.total,
                    "disk_free": disk.free,
                    "disk_percent": disk.percent,
                    "disk_path": ALLOWED_WORKSPACE,
                },
            )
        except ImportError:
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="dependency_missing",
                message="psutil not installed; install for system status",
            )


class ListAllowedDirectory(Tool):
    """Level 1: list entries in an allowed workspace directory."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", ALLOWED_WORKSPACE)
        try:
            canon = _validate_path(path)
        except ValueError as exc:
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="path_traversal",
                message=str(exc),
            )
        if not os.path.isdir(canon):
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="not_a_directory",
                message=f"not a directory: {path}",
            )
        entries: list[dict[str, Any]] = []
        try:
            for name in sorted(os.listdir(canon)):
                full = os.path.join(canon, name)
                entries.append(
                    {
                        "name": name,
                        "path": full,
                        "is_dir": os.path.isdir(full),
                        "is_file": os.path.isfile(full),
                        "size": os.path.getsize(full) if os.path.isfile(full) else None,
                    }
                )
        except OSError as exc:
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="os_error",
                message=str(exc),
            )
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"path": canon, "entries": entries, "count": len(entries)},
        )


class ReadAllowedTextFile(Tool):
    """Level 1: read a text file within the allowed workspace."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", "")
        max_bytes = int(args.get("max_bytes", 65536))
        try:
            canon = _validate_path(path)
        except ValueError as exc:
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="path_traversal",
                message=str(exc),
            )
        if not os.path.isfile(canon):
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="not_a_file",
                message=f"not a file: {path}",
            )
        try:
            with open(canon, encoding="utf-8", errors="replace") as fh:
                content = fh.read(max_bytes)
        except OSError as exc:
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="os_error",
                message=str(exc),
            )
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={
                "path": canon,
                "content": content,
                "truncated": os.path.getsize(canon) > max_bytes,
                "size": os.path.getsize(canon),
            },
        )


class SearchAllowedFiles(Tool):
    """Level 1: search file names (and optionally content) within the workspace."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        query = str(args.get("query", ""))
        search_content = bool(args.get("search_content", False))
        path = args.get("path", ALLOWED_WORKSPACE)
        try:
            canon = _validate_path(path)
        except ValueError as exc:
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="path_traversal",
                message=str(exc),
            )
        matches: list[dict[str, Any]] = []
        try:
            for root, _dirs, files in os.walk(canon):
                for name in files:
                    if query.lower() not in name.lower() and not search_content:
                        continue
                    full = os.path.join(root, name)
                    entry: dict[str, Any] = {"name": name, "path": full}
                    if search_content:
                        try:
                            with open(full, encoding="utf-8", errors="replace") as fh:
                                content = fh.read(4096)
                            if query.lower() in content.lower():
                                entry["content_snippet"] = content[:200]
                                matches.append(entry)
                        except OSError:
                            continue
                    else:
                        matches.append(entry)
                    if len(matches) >= MAX_SEARCH_RESULTS:
                        break
                if len(matches) >= MAX_SEARCH_RESULTS:
                    break
        except OSError as exc:
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="os_error",
                message=str(exc),
            )
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"query": query, "path": canon, "matches": matches, "count": len(matches)},
        )


class SearchLocalMemories(Tool):
    """Level 1: search explicit long-term memories (stub; memory layer Phase 7)."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"query": args.get("query", ""), "memories": [], "count": 0},
            message="memory index not built yet — empty result is unverified",
            verdict="unverified",
        )


class SearchIndexedDocuments(Tool):
    """Level 1: search indexed documents (stub; RAG layer Phase 7)."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"query": args.get("query", ""), "results": [], "count": 0},
            message="document index not built yet — empty result is unverified",
            verdict="unverified",
        )


class ListRunningApplications(Tool):
    """Level 1: list running applications (real, via psutil process names)."""

    _MAX_NAMES = 500  # cap on distinct process names returned

    def execute(self, args: dict[str, Any]) -> ToolResult:
        del args  # no arguments used
        try:
            names: list[str] = []
            for proc in psutil.process_iter(["name"]):
                try:
                    name = proc.info.get("name")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                if name and name not in names:
                    names.append(name)
                    if len(names) >= self._MAX_NAMES:
                        break
        except Exception as exc:  # noqa: BLE001 — process table reads are best-effort
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="process_list_failed",
                message=str(exc),
            )
        names.sort(key=str.lower)
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"applications": names, "count": len(names)},
        )


class GetClipboardText(Tool):
    """Level 2: get clipboard text (requires approval / explicit permission)."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"text": "", "note": "clipboard read requires UI approval"},
            message="nothing was read — clipboard access needs your approval first",
            verdict="ask",
        )


class OpenApplication(Tool):
    """Level 2: open an application from the allowlist."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        name = str(args.get("name", ""))
        resolved = ALLOWED_APPLICATIONS.get(name)
        if resolved is None:
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="not_allowlisted",
                message=f"application not in allowlist: {name}",
            )
        # Never accept arbitrary executable arguments from the model.
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={
                "name": name,
                "resolved": resolved,
                "launched": False,
                "note": "launch performed by Tauri host after approval",
            },
            message="handed to the Tauri host for launch — outcome follows separately",
            verdict="started",
        )


class OpenUrl(Tool):
    """Level 2: open a URL (http/https by default; validate scheme)."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        url = str(args.get("url", ""))
        if not url.startswith(("http://", "https://")):
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="invalid_scheme",
                message="only http and https URLs are permitted",
            )
        # Extract hostname for the approval UI.
        hostname = ""
        try:
            hostname = url.split("//", 1)[1].split("/", 1)[0].split(":", 1)[0]
        except IndexError:
            pass
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"url": url, "hostname": hostname, "opened": False},
            message="handed to the Tauri host to open — outcome follows separately",
            verdict="started",
        )


class CreateTextFile(Tool):
    """Level 2: create a text file in the approved workspace (atomic write)."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", "")
        content = str(args.get("content", ""))
        try:
            canon = _validate_path(path)
        except ValueError as exc:
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="path_traversal",
                message=str(exc),
            )
        if os.path.exists(canon):
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="already_exists",
                message=f"file already exists: {path} (use update_text_file)",
            )
        # Reject symlink escapes: parent must not be a symlink pointing outside.
        parent = os.path.dirname(canon)
        if os.path.islink(parent):
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="symlink_escape",
                message="parent directory is a symlink; refusing to write",
            )
        os.makedirs(parent, exist_ok=True)
        # Atomic write via temp file + replace.
        fd, tmp = tempfile.mkstemp(dir=parent, prefix=".jarvis_tmp_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp, canon)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"path": canon, "bytes": len(content.encode("utf-8"))},
        )


class UpdateTextFile(Tool):
    """Level 2: update a text file with preview/diff, atomic write, backup."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        path = args.get("path", "")
        content = str(args.get("content", ""))
        try:
            canon = _validate_path(path)
        except ValueError as exc:
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="path_traversal",
                message=str(exc),
            )
        if not os.path.isfile(canon):
            return ToolResult(
                tool_id=self.definition.id,
                ok=False,
                error_code="not_a_file",
                message=f"not a file: {path}",
            )
        # Read existing for backup + diff preview.
        with open(canon, encoding="utf-8", errors="replace") as fh:
            existing = fh.read()
        # Create backup before writing.
        backup = canon + ".jarvis.bak"
        shutil.copy2(canon, backup)
        # Atomic write.
        parent = os.path.dirname(canon)
        fd, tmp = tempfile.mkstemp(dir=parent, prefix=".jarvis_tmp_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp, canon)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={
                "path": canon,
                "backup": backup,
                "bytes_written": len(content.encode("utf-8")),
                "previous_bytes": len(existing.encode("utf-8")),
            },
        )


class CopyTextToClipboard(Tool):
    """Level 2: copy text to clipboard (stub; UI approval in Phase 9)."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"copied": False, "note": "clipboard write requires UI approval"},
            message="Nothing copied: clipboard write requires UI approval first.",
            verdict="ask",
        )


class ShowDesktopNotification(Tool):
    """Level 2: show a desktop notification (stub; Phase 9 tray/notifications)."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"shown": False, "note": "notification shown by Tauri host"},
            message="Notification handed to the Tauri host; display not yet confirmed.",
            verdict="started",
        )


# Scheduler tools (Phase 8) — registered here as stubs with real schemas.


class CreateReminder(Tool):
    """Level 2: create a reminder (stub; scheduler Phase 8)."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"reminder_id": "", "created": False, "note": "scheduler in Phase 8"},
            message="No reminder stored: the scheduler arrives in Phase 8.",
            verdict="ask",
        )


class CancelReminder(Tool):
    """Level 2: cancel a reminder (stub; scheduler Phase 8)."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"reminder_id": args.get("reminder_id", ""), "cancelled": False},
            message="No reminder cancelled: the scheduler arrives in Phase 8.",
            verdict="ask",
        )


class StartTimer(Tool):
    """Level 2: start a timer (stub; scheduler Phase 8)."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"timer_id": "", "started": False, "note": "scheduler in Phase 8"},
            message="No timer started: the scheduler arrives in Phase 8.",
            verdict="ask",
        )


class CancelTimer(Tool):
    """Level 2: cancel a timer (stub; scheduler Phase 8)."""

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_id=self.definition.id,
            ok=True,
            result={"timer_id": args.get("timer_id", ""), "cancelled": False},
            message="No timer cancelled: the scheduler arrives in Phase 8.",
            verdict="ask",
        )


def build_default_registry() -> ToolRegistry:
    """Build the default registry with all starter tools (§10)."""
    registry = ToolRegistry()

    def _add(tool_class: type[Tool], **kwargs: Any) -> None:
        registry.register(tool_class(ToolDefinition(**kwargs)))

    # Safe / read-only
    _add(
        GetCurrentDateTime,
        id="get_current_datetime",
        description="Return the current date and time.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        result_schema={
            "type": "object",
            "properties": {
                "utc_iso": {"type": "string"},
                "local_iso": {"type": "string"},
                "timestamp": {"type": "number"},
            },
        },
        risk_level=RiskLevel.LEVEL_0,
        permission_category="system:read",
        timeout_s=5.0,
        dry_run=False,
    )
    _add(
        GetSystemInformation,
        id="get_system_information",
        description="Return read-only system information.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_1,
        permission_category="system:read",
        timeout_s=5.0,
    )
    _add(
        GetCpuMemoryDiskStatus,
        id="get_cpu_memory_disk_status",
        description="Return CPU, memory, and disk status.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_1,
        permission_category="system:read",
        timeout_s=5.0,
    )
    _add(
        ListAllowedDirectory,
        id="list_allowed_directory",
        description="List entries in an allowed workspace directory.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path within the workspace"}
            },
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_1,
        permission_category="filesystem:read",
        timeout_s=10.0,
    )
    _add(
        ReadAllowedTextFile,
        id="read_allowed_text_file",
        description="Read a text file within the allowed workspace.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_bytes": {"type": "integer", "minimum": 1, "maximum": 1048576},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_1,
        permission_category="filesystem:read",
        timeout_s=10.0,
    )
    _add(
        SearchAllowedFiles,
        id="search_allowed_files",
        description="Search file names (and optionally content) within the workspace.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "path": {"type": "string"},
                "search_content": {"type": "boolean"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_1,
        permission_category="filesystem:read",
        timeout_s=15.0,
    )
    _add(
        SearchLocalMemories,
        id="search_local_memories",
        description="Search explicit long-term memories.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_1,
        permission_category="memory:read",
        timeout_s=10.0,
    )
    _add(
        SearchIndexedDocuments,
        id="search_indexed_documents",
        description="Search indexed documents (RAG).",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_1,
        permission_category="knowledge:read",
        timeout_s=15.0,
    )
    _add(
        ListRunningApplications,
        id="list_running_applications",
        description="List running applications (platform-dependent).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_1,
        permission_category="system:read",
        timeout_s=5.0,
    )
    _add(
        GetClipboardText,
        id="get_clipboard_text",
        description="Get clipboard text (requires approval/explicit permission).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_2,
        permission_category="clipboard:read",
        timeout_s=5.0,
    )

    # User-impacting
    _add(
        OpenApplication,
        id="open_application",
        description="Open an application from the allowlist.",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string", "enum": list(ALLOWED_APPLICATIONS)}},
            "required": ["name"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_2,
        permission_category="apps:launch",
        timeout_s=10.0,
    )
    _add(
        OpenUrl,
        id="open_url",
        description="Open a URL (http/https only).",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string", "format": "uri"}},
            "required": ["url"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_2,
        permission_category="url:open",
        timeout_s=10.0,
    )
    _add(
        CreateTextFile,
        id="create_text_file",
        description="Create a text file in the approved workspace (atomic write).",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_2,
        permission_category="filesystem:write",
        timeout_s=10.0,
        dry_run=True,
    )
    _add(
        UpdateTextFile,
        id="update_text_file",
        description="Update a text file with preview/diff, atomic write, backup.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_2,
        permission_category="filesystem:write",
        timeout_s=10.0,
        dry_run=True,
    )
    _add(
        CopyTextToClipboard,
        id="copy_text_to_clipboard",
        description="Copy text to clipboard.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_2,
        permission_category="clipboard:write",
        timeout_s=5.0,
    )
    _add(
        ShowDesktopNotification,
        id="show_desktop_notification",
        description="Show a desktop notification.",
        input_schema={
            "type": "object",
            "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
            "required": ["title", "body"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_2,
        permission_category="notification:show",
        timeout_s=5.0,
    )
    _add(
        CreateReminder,
        id="create_reminder",
        description="Create a reminder.",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "due_at": {"type": "string"},
                "recurring": {"type": "boolean"},
            },
            "required": ["title", "due_at"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_2,
        permission_category="scheduler:write",
        timeout_s=5.0,
    )
    _add(
        CancelReminder,
        id="cancel_reminder",
        description="Cancel a reminder.",
        input_schema={
            "type": "object",
            "properties": {"reminder_id": {"type": "string"}},
            "required": ["reminder_id"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_2,
        permission_category="scheduler:write",
        timeout_s=5.0,
    )
    _add(
        StartTimer,
        id="start_timer",
        description="Start a timer.",
        input_schema={
            "type": "object",
            "properties": {"duration_s": {"type": "number", "minimum": 1}},
            "required": ["duration_s"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_2,
        permission_category="scheduler:write",
        timeout_s=5.0,
    )
    _add(
        CancelTimer,
        id="cancel_timer",
        description="Cancel a timer.",
        input_schema={
            "type": "object",
            "properties": {"timer_id": {"type": "string"}},
            "required": ["timer_id"],
            "additionalProperties": False,
        },
        result_schema={"type": "object"},
        risk_level=RiskLevel.LEVEL_2,
        permission_category="scheduler:write",
        timeout_s=5.0,
    )

    return registry
