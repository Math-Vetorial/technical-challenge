import asyncio
import json

from data_foundry import pipeline
from data_foundry.config import Settings
from data_foundry.run import RunContext


def _settings(tmp_path, **overrides):
    return Settings(data_dir=tmp_path / "data", llm_api_key="super-secret", **overrides)


def test_create_twice_yields_distinct_runs(tmp_path):
    settings = _settings(tmp_path)

    ctx1 = RunContext.create(settings)
    ctx1.finish("success")
    ctx2 = RunContext.create(settings)
    ctx2.finish("success")

    assert ctx1.run_id != ctx2.run_id
    assert ctx1.run_dir != ctx2.run_dir
    assert ctx1.run_dir.exists()
    assert ctx2.run_dir.exists()


def test_first_manifest_untouched_after_second_run(tmp_path):
    settings = _settings(tmp_path)

    ctx1 = RunContext.create(settings)
    ctx1.finish("success")
    first_manifest_bytes = ctx1.manifest_path.read_bytes()

    ctx2 = RunContext.create(settings)
    ctx2.finish("success")

    assert ctx1.manifest_path.read_bytes() == first_manifest_bytes


def test_latest_points_to_newest_run(tmp_path):
    settings = _settings(tmp_path)

    ctx1 = RunContext.create(settings)
    ctx1.finish("success")
    ctx2 = RunContext.create(settings)
    ctx2.finish("success")

    latest = settings.curated_dir / "latest"
    if latest.is_symlink():
        assert latest.resolve() == ctx2.run_dir.resolve()
    else:
        latest_txt = settings.curated_dir / "latest.txt"
        assert latest_txt.read_text(encoding="utf-8").strip() == ctx2.run_id


def test_manifest_has_redacted_config_and_tool_versions(tmp_path):
    settings = _settings(tmp_path)

    ctx = RunContext.create(settings)
    ctx.finish("success")

    manifest = json.loads(ctx.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "success"
    assert manifest["config_snapshot"]["llm_api_key"] != "super-secret"
    assert manifest["tool_versions"]["python"]


def _latest_run_id(settings: Settings) -> str:
    latest = settings.curated_dir / "latest"
    if latest.is_symlink():
        return latest.resolve().name
    return (settings.curated_dir / "latest.txt").read_text(encoding="utf-8").strip()


def test_only_stage_and_dry_run_do_not_repoint_latest(tmp_path):
    """Regression: neither `run(..., only=...)` nor `run(..., limit=0)` (discovery-only dry run)
    produces the curated datasets, so neither must move `latest` onto a run dir that only has a
    manifest.json — that breaks every consumer (and test_outputs) that reads `latest`."""
    settings = _settings(
        tmp_path,
        source="fixtures",
        llm_provider="mock",
        download_concurrency=2,
        llm_concurrency=2,
        max_retries=0,
    )

    full_ctx = asyncio.run(pipeline.run(settings, limit=3))
    assert (full_ctx.run_dir / "localized_catalog.json").exists()
    assert (full_ctx.run_dir / "universal_metadata.json").exists()
    assert _latest_run_id(settings) == full_ctx.run_id

    only_ctx = asyncio.run(pipeline.run(settings, only="hash"))
    assert only_ctx.run_id != full_ctx.run_id
    assert not (only_ctx.run_dir / "localized_catalog.json").exists()
    assert not (only_ctx.run_dir / "universal_metadata.json").exists()
    assert _latest_run_id(settings) == full_ctx.run_id

    dry_run_ctx = asyncio.run(pipeline.run(settings, limit=0))
    assert dry_run_ctx.run_id not in {full_ctx.run_id, only_ctx.run_id}
    assert not (dry_run_ctx.run_dir / "localized_catalog.json").exists()
    assert not (dry_run_ctx.run_dir / "universal_metadata.json").exists()
    assert _latest_run_id(settings) == full_ctx.run_id
