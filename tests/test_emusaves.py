"""Standalone emulator folders (src/emusaves.py) against the mock RomM: DuckStation per-game and shared cards,
PPSSPP save folders, PCSX2 cards, matching by title and links."""
import io
import struct
import zipfile

import pytest

from tests import mock_romm


def sfo(title: str) -> bytes:
    key, val = b"TITLE\0", title.encode() + b"\0"
    header = b"\0PSF" + struct.pack("<IIII", 0x101, 20 + 16, 20 + 16 + len(key), 1)
    entry = struct.pack("<HHIII", 0, 0x0204, len(val), len(val), 0)
    return header + entry + key + val


@pytest.fixture
def setup(romm, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    from src import emusaves, sync_engine
    from src.sync_state import STATE
    STATE.baselines.clear()
    STATE.pending.clear()
    # psx / psp games in the mock library
    mock_romm.PLATFORMS.setdefault(90, ("psx", "PlayStation", "Sony"))
    mock_romm.PLATFORMS.setdefault(91, ("psp", "PlayStation Portable", "Sony"))
    mock_romm.PLATFORMS.setdefault(92, ("ps2", "PlayStation 2", "Sony"))
    mock_romm.S.add_rom(901, 90, "Crash Bandicoot (USA).chd", "Crash Bandicoot")
    mock_romm.S.add_rom(911, 91, "Patapon (USA).iso", "Patapon")

    class Cfg:
        DRY_RUN = False
        FILE_MODE = 0o777
        PUSH_NEW_MODE = "auto"
        PULL_MODE = "auto"

        def sync_dir_for(self, ft):
            return tmp_path / "syncdata"

    class Eng(sync_engine.SyncEngine):
        def __init__(self):
            self.cfg = Cfg()
            self.romm = romm
            self.PUID = self.PGID = None

        @property
        def pull_mode(self):
            return "auto"

        def _backup_local(self, path, platform):
            backups.append(path.read_bytes())

        def _write_local(self, dest, content, mtime):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)

    backups = []
    monkeypatch.setattr(emusaves, "_engine", lambda: Eng())

    class Srv:
        library = [r for r in mock_romm.S.roms]

    return emusaves, Srv(), tmp_path, backups


def test_duckstation_per_game_card_and_shared_card(setup, romm):
    emusaves, srv, tmp, _ = setup
    cards = tmp / "duck"
    cards.mkdir()
    (cards / "Crash Bandicoot_1.mcd").write_bytes(b"crash save")
    (cards / "shared_card_1.mcd").write_bytes(b"shared")
    emusaves.add_folder("duckstation", str(cards))
    s = emusaves.sync_all(srv)
    assert s["pushed"] == 2 and s["errors"] == 0
    up = [i for i in romm.list_all("saves") if i["rom_id"] == 901]
    assert up[0]["file_name"] == "Crash Bandicoot_1.mcd" and up[0]["emulator"] == "duckstation"
    assert romm.list_cards("duckstation")[0]["name"] == "shared_card_1.mcd"
    # nothing changed: nothing to do
    assert emusaves.sync_all(srv) == {"pushed": 0, "pulled": 0, "queued": 0, "errors": 0}
    # another device updates the per-game card on RomM -> downloaded
    romm._request("PUT", f"/api/saves/{up[0]['id']}", files={"saveFile": ("x", b"newer from deck")})
    assert emusaves.sync_all(srv)["pulled"] == 1
    assert (cards / "Crash Bandicoot_1.mcd").read_bytes() == b"newer from deck"


def test_ppsspp_folder_is_one_zipped_save_named_like_romm(setup, romm):
    emusaves, srv, tmp, _ = setup
    sd = tmp / "SAVEDATA"
    (sd / "UCUS98711DATA00").mkdir(parents=True)
    (sd / "UCUS98711DATA00" / "PARAM.SFO").write_bytes(sfo("Patapon"))
    (sd / "UCUS98711DATA00" / "DATA.BIN").write_bytes(b"progress")
    emusaves.add_folder("ppsspp", str(sd))
    assert emusaves.sync_all(srv)["pushed"] == 1
    item = next(i for i in romm.list_all("saves") if i["rom_id"] == 911)
    assert item["file_name"] == "PSP-UCUS98711DATA00.zip"
    z = zipfile.ZipFile(io.BytesIO(romm.download_asset("saves", item)))
    assert sorted(z.namelist()) == ["DATA.BIN", "PARAM.SFO"]
    # a second device's folder on RomM only -> created here
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zz:
        zz.writestr("DATA.BIN", b"other save")
    mock_romm.S.add_asset("saves", 911, "PSP-UCUS98711DATA01.zip", buf.getvalue())
    assert emusaves.sync_all(srv)["pulled"] == 1
    assert (sd / "UCUS98711DATA01" / "DATA.BIN").read_bytes() == b"other save"


def test_unmatched_until_linked(setup, romm):
    emusaves, srv, tmp, _ = setup
    cards = tmp / "duck"
    cards.mkdir()
    (cards / "SLUS-00594_1.mcd").write_bytes(b"save")     # named by serial: no title to match
    f = emusaves.add_folder("duckstation", str(cards))
    emusaves.sync_all(srv)
    st = emusaves.status()[0]
    assert st["matched"] == 0 and st["unmatched"][0]["match"] == "SLUS-00594"
    from src import links
    links.set_link(*emusaves.link_key(f, "SLUS-00594"), 901)
    assert emusaves.sync_all(srv)["pushed"] == 1


def test_pcsx2_card_conflict_waits(setup, romm):
    emusaves, srv, tmp, backups = setup
    mc = tmp / "memcards"
    mc.mkdir()
    (mc / "Mcd001.ps2").write_bytes(b"card v1")
    emusaves.add_folder("pcsx2", str(mc))
    assert emusaves.sync_all(srv)["pushed"] == 1
    card = romm.list_cards("pcsx2")[0]
    romm.upload_card_version(card["id"], "Mcd001.ps2", b"card from the deck")
    (mc / "Mcd001.ps2").write_bytes(b"card v2 here")
    s = emusaves.sync_all(srv)
    assert s["queued"] == 1
    from src.sync_state import STATE
    action = next(iter(STATE.pending.values()))
    ok, _ = emusaves.execute(action, "romm")
    assert ok and (mc / "Mcd001.ps2").read_bytes() == b"card from the deck" and backups == [b"card v2 here"]


def test_sfo_title():
    from src.emusaves import parse_sfo
    assert parse_sfo(sfo("Patapon 2"))["TITLE"] == "Patapon 2"
    assert parse_sfo(b"junk") == {}
