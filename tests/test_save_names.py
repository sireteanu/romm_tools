"""One game's in-game save under different devices' names (romm_tools 2.1): RetroArch's "Game.srm", MinUI/NextUI's
"Game.gba.sav" (what Grout uploads from a NextUI handheld) and the generic "Game.sav" are the same save."""
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="romm_sync_test_"))

from src.sync_engine import SyncEngine  # noqa: E402
from src.sync_files import (LocalFile, detect_save_style, name_in_style, remote_local_name, save_alias,  # noqa: E402
                            save_style)

ROW = {"id": 7, "fs_name": "Neon Drift (Europe).gba", "fs_name_no_ext": "Neon Drift (Europe)", "fs_extension": "gba"}
T = datetime(2026, 11, 1, tzinfo=timezone.utc)


def test_styles_and_aliases():
    assert save_style("Neon Drift (Europe).srm") == "retroarch"
    assert save_style("Neon Drift (Europe).gba.sav") == "minui"
    assert save_style("Neon Drift (Europe).sav") == "generic"
    assert save_style("Dr. Mario (USA).sav") == "generic"            # ". Mario (USA)" is no ROM extension
    assert save_style("Pokemon v1.1.sav") == "generic"               # ".1" neither
    assert save_style("Neon Drift (Europe).state1") is None
    assert save_style("Panzer Dragoon Saga (USA).bkr") is None
    assert save_alias("Neon Drift (Europe).srm") == save_alias("neon drift (europe).gba.sav") \
        == save_alias("Neon Drift (Europe).sav") == "neon drift (europe)"


def test_names_in_a_folders_style():
    assert name_in_style("Neon Drift (Europe).gba.sav", ROW, "retroarch") == "Neon Drift (Europe).srm"
    assert name_in_style("Neon Drift (Europe).srm", ROW, "minui") == "Neon Drift (Europe).gba.sav"
    assert name_in_style("Neon Drift (Europe).srm", ROW, "generic") == "Neon Drift (Europe).sav"
    assert name_in_style("Neon Drift (Europe).gba.sav", ROW, "keep") == "Neon Drift (Europe).gba.sav"
    # a folder with nothing to go by yet: only MinUI names change (to RetroArch's)
    assert name_in_style("Neon Drift (Europe).gba.sav", ROW, None) == "Neon Drift (Europe).srm"
    assert name_in_style("Neon Drift (Europe).sav", ROW, None) == "Neon Drift (Europe).sav"
    assert name_in_style("Neon Drift (Europe).state1", ROW, "minui") == "Neon Drift (Europe).state1"
    # with the ROM known, only its own extension counts: a version number stays part of the name
    assert name_in_style("Neon Drift v1.0a.sav", ROW, "retroarch") == "Neon Drift v1.0a.srm"
    assert detect_save_style(["A.gba.sav", "B.gba.sav", "C.srm", "C.state1"]) == "minui"
    assert detect_save_style(["A.srm", "B.sav"]) == "retroarch"     # a tie goes to RetroArch
    assert detect_save_style(["A.state"]) is None


def test_romm_names_get_the_folder_style_and_the_rom_name():
    tagged = {"file_name": "Neon Drift (Europe).gba [2026-11-01_10-00-00].sav"}
    assert remote_local_name(tagged, ROW, "retroarch") == "Neon Drift (Europe).srm"
    assert remote_local_name({"file_name": "autosave.srm"}, ROW, "minui") == "Neon Drift (Europe).gba.sav"
    assert remote_local_name({"file_name": "Neon Drift (Europe).srm"}, ROW, "minui") == "Neon Drift (Europe).gba.sav"


def _item(i, name, when):
    return {"id": i, "rom_id": 7, "file_name": name, "updated_at": when, "_api": "saves"}


def test_a_handhelds_save_and_this_folders_save_are_one_file():
    remote = {"save": {7: [_item(1, "Neon Drift (Europe).gba.sav", "2026-11-02T00:00:00+00:00")]}, "state": {}}
    rbt = SyncEngine._remote_for_rom(remote, 7, ROW, "retroarch")
    assert list(rbt["save"]) == ["Neon Drift (Europe).srm"] and rbt["save"]["Neon Drift (Europe).srm"]["id"] == 1
    # RomM has both names (this app uploaded Game.srm before 2.1): one save, the newest wins, deletes cover both
    remote["save"][7].append(_item(2, "Neon Drift (Europe).srm", "2026-11-01T00:00:00+00:00"))
    rbt = SyncEngine._remote_for_rom(remote, 7, ROW, "retroarch")
    it = rbt["save"]["Neon Drift (Europe).srm"]
    assert it["id"] == 1 and sorted(i for _, i in it["_group"]) == [1, 2]


def test_mixed_folder_pairs_the_one_local_save():
    lf = LocalFile("save", Path("/x/Neon Drift (Europe).sav"), "h", 1, T)
    local = {("save", "Neon Drift (Europe).sav"): lf}
    rbt = {"save": {"Neon Drift (Europe).srm": {"id": 1}}, "state": {}}
    SyncEngine.pair_save_aliases(local, rbt)
    assert rbt["save"] == {"Neon Drift (Europe).sav": {"id": 1}}


def test_folder_style_setting_wins_over_detection(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from src import settings
    games = [SimpleNamespace(platform="GBA", local_save_files=[SimpleNamespace(path=Path("x/A.srm"))]),
             SimpleNamespace(platform="NDS", local_save_files=[SimpleNamespace(path=Path("x/B.sav"))])]
    assert SyncEngine.save_styles(games) == {"gba": "retroarch", "nds": "generic"}
    settings.set_folder_save_names("gba", "minui")
    assert SyncEngine.save_styles(games)["gba"] == "minui"
    settings.set_folder_save_names("gba", "auto")
    assert SyncEngine.save_styles(games)["gba"] == "retroarch"


def test_update_keeps_the_name_the_handheld_knows(romm, tmp_path, monkeypatch):
    """Pushing this folder's Game.srm over Grout's Game.gba.sav updates that RomM save under its own name."""
    from tests import mock_romm
    from src import sync_engine as se
    from src.sync_state import PendingAction
    grout = romm._json("POST", "/debug/grout_upload", params={"rom_id": 21, "file_name": "Neon Drift (Europe).gba.sav"})
    f = tmp_path / "Neon Drift (Europe).srm"
    f.write_bytes(b"played on the PC")
    eng = se.SyncEngine.__new__(se.SyncEngine)
    eng.romm = romm
    eng.cfg = SimpleNamespace(DRY_RUN=False)
    monkeypatch.setattr(eng, "_check_local_unchanged", lambda a: f)
    a = PendingAction(kind="push_update", file_type="save", game="Neon Drift (Europe)", platform="gba", rom_id=21,
                      file_name=f.name, local_path=str(f), romm_id=grout["id"],
                      romm_file_name="Neon Drift (Europe).gba.sav", romm_api="saves")
    eng._push(a)
    assert mock_romm.S.put_names[grout["id"]] == "Neon Drift (Europe).gba.sav"
    assert mock_romm.S.blobs[f"saves:{grout['id']}"] == b"played on the PC"


def test_grout_folders_and_devices(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from src import settings, sync_engine as se
    from src.device_overview import client_kind
    settings.set_folder_mode("gba", "grout")
    settings.invalidate_cache()
    assert not settings.sync_enabled("gba") and settings.grout_folders() == {"gba"}
    settings.set_folder_mode("gba", "sync")
    settings.invalidate_cache()
    assert settings.sync_enabled("gba")
    assert client_kind({"client": "Grout", "name": "Brick"}) == "grout"
    assert client_kind({"client": "retroarch"}) == "retroarch"
    assert client_kind({"client": "argosy"}) == "other"
    monkeypatch.setattr(se, "_dev_cache", {"at": 1e18, "devices": [
        {"id": "a", "client": "grout", "name": "Brick"}, {"id": "b", "client": "retroarch", "name": "Deck"}]})
    assert se.grout_devices(None) == ["Brick"] and se.retroarch_devices(None) == {"b"}
