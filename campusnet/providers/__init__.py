"""Provider 注册表。"""
from __future__ import annotations

from typing import Any, Dict, List, Type

from .base import BaseProvider, LoginResult
from .custom import CustomProvider
from .drcom import DrcomProvider
from .eportal import EportalProvider
from .srun import SrunProvider

REGISTRY: Dict[str, Type[BaseProvider]] = {
    SrunProvider.name: SrunProvider,
    EportalProvider.name: EportalProvider,
    DrcomProvider.name: DrcomProvider,
    CustomProvider.name: CustomProvider,
}

ALIASES = {
    "srun": "srun",
    "深澜": "srun",
    "哆点": "srun",
    "eportal": "eportal",
    "ruijie": "eportal",
    "锐捷": "eportal",
    "drcom": "drcom",
    "dr.com": "drcom",
    "城市热点": "drcom",
    "custom": "custom",
    "自定义": "custom",
}


def get_provider(name: str, cfg: Dict[str, Any]) -> BaseProvider:
    key = ALIASES.get(str(name).strip().lower(), str(name).strip().lower())
    cls = REGISTRY.get(key)
    if cls is None:
        raise SystemExit(f"未知的认证类型: {name}\n可选: {', '.join(sorted(REGISTRY))}")
    return cls(cfg)


def available() -> List[str]:
    return sorted(REGISTRY)


__all__ = [
    "BaseProvider",
    "LoginResult",
    "REGISTRY",
    "ALIASES",
    "get_provider",
    "available",
    "SrunProvider",
    "EportalProvider",
    "DrcomProvider",
    "CustomProvider",
]
