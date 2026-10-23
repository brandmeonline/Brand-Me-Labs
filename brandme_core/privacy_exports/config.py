"""Explicit environment, chain scope and private export bucket configuration."""
from dataclasses import dataclass, field
import re

from brandme_core.config import check_legacy_flags, get_mode


@dataclass(frozen=True)
class ExportConfig:
    environment: str
    project: str
    instance: str
    database: str
    network: str
    contract: str
    bucket: str
    token: str = field(repr=False)
    storage_emulator: str = ""
    port: int = 8000

    @classmethod
    def from_env(cls, env):
        mode = get_mode(env)
        if env.get("ENVIRONMENT") != mode.value or check_legacy_flags(mode, env):
            raise ValueError("explicit matching environment required")
        spanner_emulator = env.get("SPANNER_EMULATOR_HOST", "")
        storage_emulator = env.get("EXPORT_STORAGE_EMULATOR_HOST", "")
        if mode.is_strict and (spanner_emulator or storage_emulator):
            raise ValueError("emulators forbidden in strict modes")
        if not mode.is_strict and not (spanner_emulator and storage_emulator):
            raise ValueError("development requires local emulators")
        keys = ("SPANNER_PROJECT_ID", "SPANNER_INSTANCE_ID", "SPANNER_DATABASE_ID")
        if any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", env.get(k, "")) for k in keys):
            raise ValueError("explicit Spanner configuration required")
        network, contract = env.get("EXPORT_NETWORK", ""), env.get("EXPORT_CONTRACT_ADDRESS", "")
        if network not in ("undeployed", "preview", "preprod") or not re.fullmatch(r"[0-9a-f]{64}", contract):
            raise ValueError("test network and contract required")
        bucket = env.get("EXPORT_BUCKET", "")
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,61}[a-z0-9]", bucket) or not bucket.startswith(f"brandme-{mode.value}-exports-"):
            raise ValueError("dedicated environment export bucket required")
        token = env.get("PRIVACY_EXPORT_SERVICE_TOKEN", "")
        if not re.fullmatch(r"[A-Za-z0-9._~+/-]{32,256}", token) or token in (
                env.get("RIGHTS_SERVICE_TOKEN"), env.get("PRIVACY_SERVICE_TOKEN"), env.get("CHAIN_SERVICE_TOKEN")):
            raise ValueError("distinct export service credential required")
        port = int(env.get("PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError("invalid port")
        return cls(mode.value, *(env[k] for k in keys), network, contract, bucket, token, storage_emulator, port)
