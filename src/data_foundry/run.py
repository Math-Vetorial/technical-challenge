"""RunContext: versioned run directories, the manifest, and the `latest` pointer."""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import pydantic

from data_foundry.config import Settings
from data_foundry.logging_setup import get_logger
from data_foundry.schemas import RunManifest, dump_json

logger = get_logger(__name__)


def _new_run_id() -> str:
    now = datetime.now(UTC)
    return f"{now:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"


def _git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        return None


def _tool_versions() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "pydantic": pydantic.VERSION,
        "platform": platform.platform(),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RunContext:
    """Owns one immutable, versioned run: its directory, its manifest, and the `latest` pointer."""

    def __init__(self, settings: Settings, manifest: RunManifest, run_dir: Path) -> None:
        self.settings = settings
        self.manifest = manifest
        self.run_dir = run_dir

    @property
    def run_id(self) -> str:
        return self.manifest.run_id

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "manifest.json"

    @classmethod
    def create(cls, settings: Settings) -> RunContext:
        settings.raw_dir.mkdir(parents=True, exist_ok=True)
        settings.staging_dir.mkdir(parents=True, exist_ok=True)
        settings.curated_dir.mkdir(parents=True, exist_ok=True)

        run_id = _new_run_id()
        run_dir = settings.curated_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        manifest = RunManifest(
            run_id=run_id,
            started_at=datetime.now(UTC),
            status="running",
            git_sha=_git_sha(),
            config_snapshot=settings.redacted(),
            source_url=settings.list_url,
            tool_versions=_tool_versions(),
        )
        ctx = cls(settings=settings, manifest=manifest, run_dir=run_dir)
        ctx.write_manifest()
        logger.info("run created run_id=%s dir=%s", run_id, run_dir)
        return ctx

    def write_manifest(self) -> None:
        dump_json(self.manifest, self.manifest_path)

    def update_counts(self, **kw: int) -> None:
        self.manifest.counts.update(kw)
        self.write_manifest()

    def set_quality(self, quality: dict[str, Any]) -> None:
        self.manifest.quality = quality
        self.write_manifest()

    def record_output(self, name: str, path: Path) -> None:
        rel = path.relative_to(self.run_dir) if path.is_relative_to(self.run_dir) else path
        self.manifest.outputs[name] = str(rel)
        self.manifest.output_hashes[name] = _sha256_file(path)
        self.write_manifest()

    def finish(self, status: Literal["success", "failed"]) -> None:
        self.manifest.status = status
        self.manifest.finished_at = datetime.now(UTC)
        self.write_manifest()
        if status == "success":
            self._update_latest_pointer()

    def _update_latest_pointer(self) -> None:
        """Point curated_dir/latest at this run. Real symlink, falling back to latest.txt."""
        latest_path = self.settings.curated_dir / "latest"
        latest_txt = self.settings.curated_dir / "latest.txt"

        if latest_path.is_symlink() or latest_path.exists():
            latest_path.unlink()

        try:
            latest_path.symlink_to(self.run_dir, target_is_directory=True)
            latest_txt.unlink(missing_ok=True)
        except OSError:
            latest_txt.write_text(self.run_id, encoding="utf-8")
