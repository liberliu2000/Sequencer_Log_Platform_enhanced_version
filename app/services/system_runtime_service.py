from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.settings import get_settings
from app.services.env_file_service import EnvFileService

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    psutil = None


def _round(value: float | int | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except Exception:
        return None


def _mb(value: int | float | None) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) / 1024 / 1024, 1)
    except Exception:
        return None


def _gb(value: int | float | None) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) / 1024 / 1024 / 1024, 2)
    except Exception:
        return None


class SystemRuntimeService:
    def __init__(self, env_service: EnvFileService | None = None):
        self.env_service = env_service or EnvFileService()

    def current_policy(self) -> dict[str, Any]:
        settings = get_settings()
        memory_limit_percent = max(0, min(int(settings.system_memory_soft_limit_percent), 98))
        memory_reserve_mb = max(0, int(settings.system_memory_soft_reserve_mb))
        cpu_limit_percent = max(0, min(int(settings.system_cpu_soft_limit_percent), 100))
        guard_wait_seconds = max(2, int(settings.system_memory_guard_wait_seconds))
        return {
            "memory_soft_limit_percent": memory_limit_percent,
            "memory_soft_reserve_mb": memory_reserve_mb,
            "cpu_soft_limit_percent": cpu_limit_percent,
            "guard_wait_seconds": guard_wait_seconds,
            "blocks_new_tasks_only": True,
            "policy_note": "When CPU or memory pressure is high, new task dispatch is delayed but running tasks keep going.",
        }

    def current_snapshot(self) -> dict[str, Any]:
        settings = get_settings()
        cpu = self._read_cpu()
        memory = self._read_memory()
        disk = self._read_disk(Path(settings.data_dir))
        policy = self.current_policy()
        guard = self.dispatch_guard(cpu=cpu, memory=memory, policy=policy)
        return {
            "collected_at": datetime.utcnow().isoformat(),
            "cpu": cpu,
            "memory": memory,
            "disk": disk,
            "policy": policy,
            "guard": guard,
        }

    def dispatch_guard(
        self,
        *,
        cpu: dict[str, Any] | None = None,
        memory: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cpu = cpu or self._read_cpu()
        memory = memory or self._read_memory()
        policy = policy or self.current_policy()
        memory_limit_percent = int(policy.get("memory_soft_limit_percent") or 0)
        memory_reserve_mb = int(policy.get("memory_soft_reserve_mb") or 0)
        cpu_limit_percent = int(policy.get("cpu_soft_limit_percent") or 0)
        wait_seconds = int(policy.get("guard_wait_seconds") or 5)

        reasons: list[str] = []
        current_memory_percent = memory.get("percent")
        available_mb = memory.get("available_mb")
        cpu_percent = cpu.get("percent")

        if (
            memory_limit_percent > 0
            and current_memory_percent is not None
            and float(current_memory_percent) >= memory_limit_percent
        ):
            reasons.append(
                f"memory usage {current_memory_percent}% reached the soft limit {memory_limit_percent}%"
            )
        if memory_reserve_mb > 0 and available_mb is not None and float(available_mb) <= memory_reserve_mb:
            reasons.append(
                f"available memory {available_mb} MB is below the reserved threshold {memory_reserve_mb} MB"
            )
        if cpu_limit_percent > 0 and cpu_percent is not None and float(cpu_percent) >= cpu_limit_percent:
            reasons.append(f"CPU usage {cpu_percent}% reached the soft limit {cpu_limit_percent}%")

        blocked = bool(reasons)
        return {
            "blocked": blocked,
            "dispatch_allowed": not blocked,
            "reasons": reasons,
            "summary": "; ".join(reasons)
            if reasons
            else "System resources are healthy enough to continue dispatching new tasks.",
            "guard_wait_seconds": wait_seconds,
            "cpu_percent": cpu_percent,
            "memory_percent": current_memory_percent,
            "available_headroom_percent": None
            if current_memory_percent is None or memory_limit_percent <= 0
            else _round(memory_limit_percent - float(current_memory_percent)),
            "available_headroom_mb": None
            if available_mb is None or memory_reserve_mb <= 0
            else _round(float(available_mb) - memory_reserve_mb),
            "available_cpu_headroom_percent": None
            if cpu_percent is None or cpu_limit_percent <= 0
            else _round(cpu_limit_percent - float(cpu_percent)),
        }

    def adaptive_cpu_allocation(
        self,
        requested_cpu_cores: int | None,
        available_cpu_count: int,
        configured_max: int,
    ) -> dict[str, Any]:
        logical_cores = max(1, int(available_cpu_count or os.cpu_count() or 1))
        requested = max(1, int(requested_cpu_cores or configured_max or 1))
        requested = min(requested, logical_cores, max(1, int(configured_max or 1)))

        snapshot = self.current_snapshot()
        guard = snapshot.get("guard", {})
        cpu_percent = ((snapshot.get("cpu") or {}).get("percent"))
        cpu_limit = ((snapshot.get("policy") or {}).get("cpu_soft_limit_percent")) or 0

        recommended = requested
        reason = "requested"
        if guard.get("blocked"):
            recommended = 1
            reason = "system_guard"
        elif cpu_percent is not None and cpu_limit and float(cpu_percent) >= max(60.0, float(cpu_limit) - 10.0):
            recommended = max(1, min(requested, requested // 2 or 1))
            reason = "cpu_pressure"

        return {
            "requested_cpu_cores": requested,
            "recommended_cpu_cores": recommended,
            "reason": reason,
            "snapshot": snapshot,
        }

    def update_memory_policy(
        self,
        *,
        memory_soft_limit_percent: int | None = None,
        memory_soft_reserve_mb: int | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        if memory_soft_limit_percent is not None:
            if int(memory_soft_limit_percent) < 50 or int(memory_soft_limit_percent) > 98:
                raise ValueError("memory_soft_limit_percent must be between 50 and 98")
            self.env_service.update_item(
                "SYSTEM_MEMORY_SOFT_LIMIT_PERCENT",
                str(int(memory_soft_limit_percent)),
            )
        if memory_soft_reserve_mb is not None:
            if int(memory_soft_reserve_mb) < 0 or int(memory_soft_reserve_mb) > 262144:
                raise ValueError("memory_soft_reserve_mb must be between 0 and 262144")
            self.env_service.update_item(
                "SYSTEM_MEMORY_SOFT_RESERVE_MB",
                str(int(memory_soft_reserve_mb)),
            )

        snapshot = self.current_snapshot()
        snapshot["updated_by"] = actor or "system"
        return snapshot

    def _read_cpu(self) -> dict[str, Any]:
        logical_cores = os.cpu_count() or 1
        load_avg = None
        if hasattr(os, "getloadavg"):
            try:
                load1, load5, load15 = os.getloadavg()
                load_avg = {
                    "load_1m": _round(load1, 2),
                    "load_5m": _round(load5, 2),
                    "load_15m": _round(load15, 2),
                }
            except Exception:
                load_avg = None

        if psutil is not None:
            try:
                return {
                    "percent": _round(psutil.cpu_percent(interval=0.15)),
                    "logical_cores": logical_cores,
                    "physical_cores": psutil.cpu_count(logical=False) or logical_cores,
                    "load_avg": load_avg,
                    "source": "psutil",
                }
            except Exception:
                pass

        approx_percent = None
        if load_avg and logical_cores > 0 and load_avg.get("load_1m") is not None:
            approx_percent = min(100.0, max(0.0, float(load_avg["load_1m"]) / logical_cores * 100))
        return {
            "percent": _round(approx_percent),
            "logical_cores": logical_cores,
            "physical_cores": logical_cores,
            "load_avg": load_avg,
            "source": "fallback",
        }

    def _read_memory(self) -> dict[str, Any]:
        if psutil is not None:
            try:
                mem = psutil.virtual_memory()
                return {
                    "total_mb": _mb(mem.total),
                    "used_mb": _mb(mem.used),
                    "available_mb": _mb(mem.available),
                    "percent": _round(mem.percent),
                    "source": "psutil",
                }
            except Exception:
                pass

        linux_meminfo = self._read_linux_meminfo()
        if linux_meminfo:
            total = linux_meminfo.get("MemTotal")
            available = linux_meminfo.get("MemAvailable") or linux_meminfo.get("MemFree")
            if total and available is not None:
                used = max(int(total) - int(available), 0)
                percent = used / total * 100 if total else 0
                return {
                    "total_mb": _round(total / 1024, 1),
                    "used_mb": _round(used / 1024, 1),
                    "available_mb": _round(available / 1024, 1),
                    "percent": _round(percent),
                    "source": "linux_meminfo",
                }

        return {
            "total_mb": None,
            "used_mb": None,
            "available_mb": None,
            "percent": None,
            "source": "unknown",
        }

    def _read_disk(self, target_path: Path) -> dict[str, Any]:
        path = target_path if target_path.exists() else Path.cwd()
        usage = shutil.disk_usage(path)
        total = usage.total
        used = usage.used
        free = usage.free
        percent = used / total * 100 if total else 0
        return {
            "path": str(path),
            "total_gb": _gb(total),
            "used_gb": _gb(used),
            "free_gb": _gb(free),
            "percent": _round(percent),
        }

    @staticmethod
    def _read_linux_meminfo() -> dict[str, int]:
        meminfo_path = Path("/proc/meminfo")
        if not meminfo_path.exists():
            return {}
        result: dict[str, int] = {}
        try:
            for line in meminfo_path.read_text(encoding="utf-8").splitlines():
                if ":" not in line:
                    continue
                key, raw_value = line.split(":", 1)
                parts = raw_value.strip().split()
                if not parts:
                    continue
                try:
                    result[key] = int(parts[0])
                except Exception:
                    continue
        except Exception:
            return {}
        return result
