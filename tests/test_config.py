import pathlib
import textwrap

from bid_radar.config import load_config


def test_defaults_load(root):
    cfg = load_config(root)
    assert cfg["sources"]["bidnet"]["page_size"] == 100
    assert cfg["scoring"]["location_points"]["Colorado"] == 2


def test_local_overlay_deep_merges(tmp_path, root):
    (tmp_path / "config.yaml").write_text((root / "config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "config.local.yaml").write_text(textwrap.dedent("""
        output_dir: C:/somewhere/scratch
        sources:
          bidnet:
            saved_search_ids: ["111", "222"]
    """), encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg["output_dir"] == "C:/somewhere/scratch"
    assert cfg["sources"]["bidnet"]["saved_search_ids"] == ["111", "222"]
    assert cfg["sources"]["bidnet"]["page_size"] == 100  # untouched sibling survives


def test_env_overrides(monkeypatch, root):
    monkeypatch.setenv("SAM_API_KEY", "abc123")
    monkeypatch.setenv("BID_RADAR_OUTPUT_DIR", "D:/out")
    cfg = load_config(root)
    assert cfg["sources"]["samgov"]["api_key"] == "abc123"
    assert cfg["output_dir"] == "D:/out"


def test_dotenv_file_feeds_env_overrides(tmp_path, root, monkeypatch):
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    (tmp_path / "config.yaml").write_text((root / "config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".env").write_text("# comment\nSAM_API_KEY = \"fromdotenv\"\nexport OTHER='x'\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg["sources"]["samgov"]["api_key"] == "fromdotenv"


def test_real_env_wins_over_dotenv(tmp_path, root, monkeypatch):
    monkeypatch.setenv("SAM_API_KEY", "fromshell")
    (tmp_path / "config.yaml").write_text((root / "config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".env").write_text("SAM_API_KEY=fromdotenv\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg["sources"]["samgov"]["api_key"] == "fromshell"
