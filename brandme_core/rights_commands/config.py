"""Explicit deployment configuration; secrets never appear in repr or errors."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping

from brandme_core.config import check_legacy_flags, get_mode

TOKEN = re.compile(r"[A-Za-z0-9._~+/-]{32,256}")
#: Every other service credential the gateway holds; the command credential differs from all of them.
OTHER_TOKENS = ("RIGHTS_SERVICE_TOKEN", "PRIVACY_SERVICE_TOKEN", "PRIVACY_EXPORT_SERVICE_TOKEN", "CHAIN_SERVICE_TOKEN")


@dataclass(frozen=True)
class CommandConfig:
    environment: str
    project: str
    instance: str
    database: str
    network: str
    contract: str
    token: str = field(repr=False)
    port: int = 8000

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "CommandConfig":
        mode = get_mode(env)
        if env.get("ENVIRONMENT") != mode.value or check_legacy_flags(mode, env):
            raise ValueError("mode and environment must agree without stub flags")
        emulator = env.get("SPANNER_EMULATOR_HOST", "")
        if mode.is_strict and emulator or not mode.is_strict and not emulator:
            raise ValueError("strict modes require real Spanner; demo/development requires its emulator")
        required = ("SPANNER_PROJECT_ID", "SPANNER_INSTANCE_ID", "SPANNER_DATABASE_ID")
        if any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", env.get(k, "")) for k in required):
            raise ValueError("explicit Spanner configuration required")
        token = env.get("RIGHTS_COMMAND_SERVICE_TOKEN", "")
        if not TOKEN.fullmatch(token) or token in {env.get(k) for k in OTHER_TOKENS}:
            raise ValueError("a distinct rights command service credential is required")
        network, contract = env.get("RIGHTS_COMMAND_NETWORK", ""), env.get("RIGHTS_COMMAND_CONTRACT_ADDRESS", "")
        if network not in ("undeployed", "preview", "preprod") or not re.fullmatch(r"[0-9a-f]{64}", contract):
            raise ValueError("explicit test network and contract scope required")
        port = int(env.get("PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError("invalid port")
        return cls(mode.value, *(env[k] for k in required), network, contract, token, port)
