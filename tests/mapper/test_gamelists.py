"""Game names: gamelist.xml names compared with RomM's, and renaming in RomM (src/mapper/gamelists.py
and the /roms/api/names routes)."""
import json
import os

import pytest

from src.mapper import gamelists

from conftest import Env, make_dirs

PLATFORMS = [
    {"id": 1, "slug": "snes", "fs_slug": "snes", "name": "Super Nintendo", "display_name": "Super Nintendo"},
    {"id": 2, "slug": "gba", "fs_slug": "gba", "name": "Game Boy Advance", "display_name": "Game Boy Advance"},
    {"id": 3, "slug": "genesis", "fs_slug": "megadrive", "name": "Genesis", "display_name": "Genesis"},
]


def write_gamelist(folder, entries, root="gameList"):
    os.makedirs(folder, exist_ok=True)
    games = "".join(f"<game><path>{p}</path><name>{n}</name></game>" for p, n in entries)
    with open(os.path.join(folder, "gamelist.xml"), "w", encoding="utf-8") as f:
        f.write(f'<?xml version="1.0"?>\n<{root}>{games}</{root}>')


def rom(i, pid, fs_name, name, fs_path):
    return {"id": i, "platform_id": pid, "fs_name": fs_name, "name": name, "fs_path": fs_path}


# ---------------------------------------------------------------- gamelists.py

def test_read_gamelist(tmp_path):
    d = str(tmp_path / "snes")
    os.makedirs(d)
    with open(os.path.join(d, "gamelist.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0"?><gameList>'
                '<game><path>./Super Mario World (USA).sfc</path><name>Super Mario World</name></game>'
                '<game><path>./Hacks/Kaizo.sfc</path><name>  Kaizo   Mario &amp; Friends </name></game>'
                '<folder><path>./Multi (USA)</path><name>Multi</name></folder>'
                '<game><path>./no-name.sfc</path></game>'
                '</gameList>')
    got = gamelists.read_gamelist(os.path.join(d, "gamelist.xml"))
    assert got == {"Super Mario World (USA).sfc": "Super Mario World",
                   "Hacks/Kaizo.sfc": "Kaizo Mario & Friends", "Multi (USA)": "Multi"}


def test_read_gamelist_bad_xml(tmp_path):
    f = tmp_path / "gamelist.xml"
    f.write_text("<gameList><game><path>./a</path>")
    with pytest.raises(ValueError, match="not valid XML"):
        gamelists.read_gamelist(str(f))


def test_rom_rel_path():
    assert gamelists.rom_rel_path({"fs_path": "roms/snes", "fs_name": "a.sfc"}, "snes") == "a.sfc"
    assert gamelists.rom_rel_path({"fs_path": "roms/snes/Hacks", "fs_name": "a.sfc"}, "snes") == "Hacks/a.sfc"
    assert gamelists.rom_rel_path({"fs_path": "snes/roms", "fs_name": "a.sfc"}, "snes") == "a.sfc"   # structure B


def test_platform_folders(tmp_path):
    extra = tmp_path / "gamelists"
    for n in ("megadrive", "GBA", "unknown"):
        (extra / n).mkdir(parents=True)
    got = gamelists.platform_folders([("snes", "/path/to/roms/snes")], [str(extra)], PLATFORMS)
    assert got == {1: ["/path/to/roms/snes"], 2: [str(extra / "GBA")], 3: [str(extra / "megadrive")]}


def test_compare(tmp_path):
    snes = str(tmp_path / "snes")
    write_gamelist(snes, [("./Super Mario World (USA).sfc", "Super Mario World"),
                          ("./Zelda (USA).sfc", "The Legend of Zelda: A Link to the Past"),
                          ("./Hacks/Zelda (USA).sfc", "Zelda Parallel Worlds"),
                          ("./F-Zero (USA).sfc", "F-ZERO"),
                          ("./Only In Gamelist.sfc", "Only")])
    roms = [rom(1, 1, "Super Mario World (USA).sfc", "Super Mario World", "roms/snes"),
            rom(2, 1, "Zelda (USA).sfc", "Zelda", "roms/snes"),
            rom(3, 1, "Zelda (USA).sfc", "Zelda (USA)", "roms/snes/Hacks"),
            rom(4, 1, "F-Zero (USA).sfc", "F-Zero", "roms/snes"),
            rom(5, 1, "Not In Gamelist.sfc", "Not", "roms/snes"),
            rom(6, 2, "Other.gba", "Other", "roms/gba")]       # no gamelist for gba
    res = gamelists.compare(PLATFORMS, gamelists.collect({1: [snes]}), roms, {"4": "F-ZERO"})
    rows = {r["id"]: r for r in res["rows"]}
    assert set(rows) == {2, 3, 4}
    assert rows[2]["gamelist_name"] == "The Legend of Zelda: A Link to the Past"
    assert rows[3]["gamelist_name"] == "Zelda Parallel Worlds" and rows[3]["file"] == "Hacks/Zelda (USA).sfc"
    assert rows[4]["ignored"] and rows[4]["case_only"]
    assert res["summary"] == {"gamelists": 1, "platforms": 1, "different": 2, "ignored": 1, "same": 1,
                              "romm_not_in_gamelist": 1, "gamelist_not_in_romm": 1}


def test_compare_file_name_fallback(tmp_path):
    """A gamelist that lists a ROM in another folder still matches by file name - unless two entries share it."""
    d = str(tmp_path / "gba")
    write_gamelist(d, [("./sub/A.gba", "Game A"), ("./x/B.gba", "B one"), ("./y/B.gba", "B two")])
    roms = [rom(1, 2, "A.gba", "A", "roms/gba"), rom(2, 2, "B.gba", "B", "roms/gba")]
    res = gamelists.compare(PLATFORMS, gamelists.collect({2: [d]}), roms, {})
    assert [(r["id"], r["gamelist_name"]) for r in res["rows"]] == [(1, "Game A")]


def test_subfolder_gamelists_and_folders_without_one(tmp_path):
    """Not every folder has a gamelist; subfolders can have their own (paths relative to them).
    Media folders, "never read" names and folders that are another platform aren't searched."""
    snes, gba = str(tmp_path / "snes"), str(tmp_path / "gba")
    write_gamelist(snes, [("./Root.sfc", "Root Game")])
    write_gamelist(os.path.join(snes, "Hacks"), [("./Hack.sfc", "Great Hack")])
    write_gamelist(os.path.join(snes, "Hacks", "Kaizo"), [("./Kaizo.sfc", "Kaizo Hack")])
    write_gamelist(os.path.join(snes, "media"), [("./Root.sfc", "From media")])
    write_gamelist(os.path.join(snes, "Extras"), [("./X.sfc", "Skipped")])
    write_gamelist(os.path.join(snes, "Satellaview"), [("./Bs.sfc", "Another platform's")])
    os.makedirs(gba)                                     # no gamelist anywhere
    folders = {1: [snes], 2: [gba], 3: [os.path.join(snes, "Satellaview")]}
    found = gamelists.collect(folders, skip=["extra*"])
    assert [p for _f, p in found[1]] == ["", "Hacks", "Hacks/Kaizo"]
    assert found[2] == [] and [p for _f, p in found[3]] == [""]
    roms = [rom(1, 1, "Root.sfc", "Root", "roms/snes"), rom(2, 1, "Hack.sfc", "Hack", "roms/snes/Hacks"),
            rom(3, 1, "Kaizo.sfc", "Kaizo", "roms/snes/Hacks/Kaizo"), rom(4, 2, "A.gba", "A", "roms/gba")]
    res = gamelists.compare(PLATFORMS, found, roms, {})
    assert sorted((r["id"], r["gamelist_name"], r["file"]) for r in res["rows"]) == [
        (1, "Root Game", "Root.sfc"), (2, "Great Hack", "Hacks/Hack.sfc"), (3, "Kaizo Hack", "Hacks/Kaizo/Kaizo.sfc")]
    assert res["no_gamelist"] == ["Game Boy Advance"]


def test_check_name():
    assert gamelists.check_name("  A   B ") == "A B"
    for bad in ("", "   ", None, "x" * 351):
        with pytest.raises(ValueError):
            gamelists.check_name(bad)


# ---------------------------------------------------------------- the page's API

class FakeRomm:
    url = "http://romm.test"

    def __init__(self, roms):
        self.roms = {r["id"]: r for r in roms}
        self.renamed = []
        self.fail = set()

    def list_platforms(self):
        return PLATFORMS

    def get_full_library(self, platform_ids=None, trim=None, on_progress=None):
        ids = {p for p, _ in platform_ids or []}
        items = [dict(r) for r in self.roms.values() if not ids or r["platform_id"] in ids]
        return {"items": trim(items) if trim else items}

    def rename_rom(self, rom_id, name):
        if rom_id in self.fail:
            raise RuntimeError("RomM refused the change")
        self.roms[rom_id]["name"] = name
        self.renamed.append((rom_id, name))
        return dict(self.roms[rom_id])


@pytest.fixture
def app(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch)
    make_dirs(env.roms, "snes", "gba")
    write_gamelist(os.path.join(env.roms, "snes"), [("./Game 0.zip", "Zelda: A Link to the Past")])
    extra = os.path.join(env.root, "es-de", "gamelists")
    write_gamelist(os.path.join(extra, "gba"), [("./Game 0.zip", "Metroid Fusion")])
    server, client = env.start()
    fake = FakeRomm([rom(1, 1, "Game 0.zip", "Game 0", "roms/snes"),
                     rom(2, 2, "Game 0.zip", "Game 0", "roms/gba")])
    monkeypatch.setattr(server, "romm_client", lambda: fake)
    # the RomM library page: the roms folder is a download folder with one folder per platform
    r = client.put("/api/romm/options", json={"sources": [env.roms]})
    assert r.status_code == 200
    return env, server, client, fake, extra


def test_names_from_romm_library_and_extra_folder(app):
    env, server, client, fake, extra = app
    v = client.get("/api/names").get_json()
    assert [(r["id"], r["gamelist_name"]) for r in v["rows"]] == [(1, "Zelda: A Link to the Past")]
    v = client.put("/api/names/options", json={"folders": extra + "\n"}).get_json()
    assert v["folders"] == [extra]
    assert sorted((r["id"], r["gamelist_name"]) for r in v["rows"]) == [(1, "Zelda: A Link to the Past"),
                                                                       (2, "Metroid Fusion")]
    assert json.loads(env.read_config("game-names.json"))["folders"] == [extra]
    assert client.put("/api/names/options", json={"folders": ["relative/path"]}).status_code == 400


def test_names_apply_typed_name_and_undo(app):
    env, server, client, fake, extra = app
    client.get("/api/names")
    v = client.post("/api/names/apply", json={"changes": [{"id": 1, "name": "  Zelda  ALttP "}]}).get_json()
    assert v["done"] == 1 and fake.renamed == [(1, "Zelda ALttP")]
    assert v["rows"][0]["romm_name"] == "Zelda ALttP"            # still differs from the gamelist: stays listed
    assert v["undo"]["count"] == 1
    v = client.post("/api/names/apply", json={"changes": [{"id": 1, "name": "Zelda: A Link to the Past"}]}).get_json()
    assert v["rows"] == [] and v["summary"]["same"] == 1
    v = client.post("/api/names/undo").get_json()
    assert fake.roms[1]["name"] == "Zelda ALttP" and v["undo"]["count"] == 1   # the earlier batch is next
    client.post("/api/names/undo")
    assert fake.roms[1]["name"] == "Game 0"
    assert client.post("/api/names/undo").status_code == 400


def test_names_apply_refuses_unknown_and_reports_failures(app):
    env, server, client, fake, extra = app
    client.get("/api/names")
    fake.fail.add(1)
    v = client.post("/api/names/apply", json={"changes": [{"id": 1, "name": "X"}, {"id": 99, "name": "Y"},
                                                          {"id": 1, "name": ""}]}).get_json()
    assert v["done"] == 0 and fake.renamed == []
    assert {f["id"] for f in v["failed"]} == {1, 99} and len(v["failed"]) == 3
    assert client.post("/api/names/apply", json={"changes": []}).status_code == 400


def test_names_ignore(app):
    env, server, client, fake, extra = app
    client.get("/api/names")
    v = client.put("/api/names/ignore", json={"ids": [1]}).get_json()
    assert v["rows"][0]["ignored"] and v["summary"]["different"] == 0 and v["summary"]["ignored"] == 1
    assert json.loads(env.read_config("game-names.json"))["ignored"] == {"1": "Zelda: A Link to the Past"}
    # a new gamelist name shows the game again
    write_gamelist(os.path.join(env.roms, "snes"), [("./Game 0.zip", "Zelda 3")])
    v = client.get("/api/names?fresh=1").get_json()
    assert not v["rows"][0]["ignored"]
    v = client.put("/api/names/ignore", json={"ids": [1], "ignore": False}).get_json()
    assert json.loads(env.read_config("game-names.json"))["ignored"] == {}


def test_names_without_romm(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch)
    server, client = env.start()
    monkeypatch.setattr(server, "romm_client", lambda: None)
    v = client.get("/api/names").get_json()
    assert v["romm"] is False and v["rows"] == []
    assert client.post("/api/names/apply", json={"changes": [{"id": 1, "name": "x"}]}).status_code == 400
