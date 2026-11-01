"""The combined app: one web server for both parts, the switches that turn each part on or off, and
how the frontend links get the share's owner when the container runs as root."""
import importlib
import os
import sys
import tempfile
from types import SimpleNamespace

import pytest

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="romm_tools_test_"))

from fastapi.testclient import TestClient  # noqa: E402

from src import config  # noqa: E402


def make_cfg(**features):
    cfg = SimpleNamespace(ROMM_CREDENTIALS=SimpleNamespace(url="http://x", auth_type="api"), WEB_USERNAME="",
                          WEB_PASSWORD="", SAVE_SYNC_DIR=None, STATE_SYNC_DIR=None, ALL_SYNC_DIR=None,
                          PLATFORM_MAP_PATH=None)
    cfg.FEATURES = {"save_sync": True, "rom_folders": True, "save_sync_problem": None, **features}
    return cfg


@pytest.fixture
def client(tmp_path, monkeypatch):
    """-> make(**features): a test client of the whole web app, ROM folders on temporary folders."""
    roms = tmp_path / "share" / "roms"
    (roms / "snes").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    for k, v in {"CONFIG_DIR": str(tmp_path / "config"), "SRC_BASE": str(roms),
                 "DEST_PATH": str(tmp_path / "share" / "mapping"), "ROMM_SOURCE": ""}.items():
        monkeypatch.setenv(k, v)

    def make(**features):
        for mod in ("src.mapper.server", "src.mapper.romm", "src.mapper.links"):
            sys.modules.pop(mod, None)
        web = importlib.import_module("src.web")
        return TestClient(web.create_app(make_cfg(**features)))
    return make


def test_both_parts_share_one_server(client):
    c = client()
    assert c.get("/api/features").json() == {"save_sync": True, "rom_folders": True, "save_sync_problem": None}
    assert "romm_tools" in c.get("/").text                           # the save sync dashboard
    page = c.get("/roms/")                                            # the ROM folders page
    assert page.status_code == 200 and 'data-pane="links"' in page.text and 'data-pane="romm"' in page.text
    state = c.get("/roms/api/state").json()
    assert [r["folder"] for r in state["rows"]] == ["roms/snes"]
    r = c.get("/roms", follow_redirects=False)                       # its page uses relative api/ addresses
    assert r.status_code in (301, 302, 307) and r.headers["location"].endswith("roms/")


def test_menus_link_the_two_parts():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sync_page = open(os.path.join(root, "src", "web_static", "index.html"), encoding="utf-8").read()
    rom_page = open(os.path.join(root, "src", "mapper", "static", "index.html"), encoding="utf-8").read()
    assert 'href="roms/#links"' in sync_page and 'href="roms/#romm"' in sync_page
    assert 'href="../#saves"' in rom_page and 'href="../#settings"' in rom_page
    assert '"/api/' not in rom_page                                   # absolute addresses would miss /roms/


def test_only_rom_folders_opens_on_the_rom_folders_page(client):
    c = client(save_sync=False, save_sync_problem="ROMM Host URL is required!")
    r = c.get("/", follow_redirects=False)
    assert r.status_code in (301, 302, 307) and r.headers["location"].endswith("roms/")
    assert c.get("/api/features").json()["save_sync_problem"] == "ROMM Host URL is required!"
    assert c.get("/api/health").status_code == 200


def test_rom_folders_can_be_switched_off(client):
    c = client(rom_folders=False)
    assert c.get("/roms/api/state").status_code == 404
    assert c.get("/").status_code == 200


def test_basic_auth_covers_the_rom_folders_page_too(client):
    client()                            # sets up the ROM folders part on temporary folders
    from src.web import create_app
    cfg = make_cfg()
    cfg.WEB_USERNAME, cfg.WEB_PASSWORD = "me", "secret"
    c = TestClient(create_app(cfg))
    assert c.get("/roms/api/state").status_code == 401
    assert c.get("/roms/api/state", auth=("me", "secret")).status_code == 200
    assert c.get("/api/health").status_code == 200                    # Docker's health check needs no login


@pytest.mark.parametrize("value,env,expected", [
    ("auto", {}, False),
    ("auto", {"ROMM_URL": "http://romm"}, True),
    ("auto", {"SAVE_SYNC_FOLDER": "1"}, True),
    ("false", {"ROMM_URL": "http://romm"}, False),
    ("true", {}, True),
])
def test_save_sync_switch(monkeypatch, value, env, expected):
    for k in ("ROMM_URL", "SAVE_SYNC_FOLDER", "STATE_SYNC_FOLDER", "ALL_SYNC_FOLDER"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("SAVE_SYNC", value)
    assert config.save_sync_wanted() is expected


def test_rom_folders_switch(monkeypatch):
    monkeypatch.delenv("ROM_FOLDERS", raising=False)
    assert config.rom_folders_wanted() is True
    monkeypatch.setenv("ROM_FOLDERS", "false")
    assert config.rom_folders_wanted() is False


def test_missing_save_sync_settings_are_reported_not_fatal(monkeypatch):
    for k in ("ROMM_URL", "ROMM_API_TOKEN", "SAVE_SYNC_FOLDER", "STATE_SYNC_FOLDER", "ALL_SYNC_FOLDER"):
        monkeypatch.delenv(k, raising=False)
    cfg = config.load_config()
    problems = cfg.problems()
    assert any("URL" in p for p in problems) and any("sync directories" in p for p in problems)
    with pytest.raises(ValueError):
        cfg.validate()


def test_links_get_the_share_owner_when_running_as_root(tmp_path, monkeypatch):
    from src.mapper import links
    src = tmp_path / "roms" / "snes"
    src.mkdir(parents=True)
    dest = tmp_path / "mapping"
    calls = []
    monkeypatch.setenv("PUID", "99")
    monkeypatch.setenv("PGID", "100")
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "lchown", lambda p, u, g: calls.append((os.path.relpath(p, tmp_path), u, g)))
    res = links.apply({str(dest / "rgs" / "snes"): str(src)}, str(dest))
    assert res["created"] == 1
    assert ("mapping", 99, 100) in calls and ("mapping/rgs", 99, 100) in calls
    assert ("mapping/rgs/snes", 99, 100) in calls


def test_links_keep_the_running_user_when_not_root(tmp_path, monkeypatch):
    from src.mapper import links
    (tmp_path / "roms" / "snes").mkdir(parents=True)
    monkeypatch.setenv("PUID", "99")
    monkeypatch.setenv("PGID", "100")
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    called = []
    monkeypatch.setattr(os, "lchown", lambda *a: called.append(a))
    links.apply({str(tmp_path / "mapping" / "rgs" / "snes"): str(tmp_path / "roms" / "snes")}, str(tmp_path / "mapping"))
    assert called == []


def test_both_pages_share_the_romm_components_block():
    """The RomM form controls (checkboxes, fields, selects) are one CSS block, the same on both pages."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    blocks = []
    for page in (("src", "web_static", "index.html"), ("src", "mapper", "static", "index.html")):
        html = open(os.path.join(root, *page), encoding="utf-8").read()
        start = html.index("/* === RomM components (shared) ===")
        end = html.index("/* === end RomM components === */")
        assert start < end < html.index("</style>")
        blocks.append(html[start:end])
    assert blocks[0] == blocks[1]
