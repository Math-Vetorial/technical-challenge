import json

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
