"""The shared RomM client against the mock RomM (tests/mock_romm.py) over real HTTP: devices, conflicts RomM
reports (409), RomM 5.5's held saves, pairing, memory cards and the supported platform list."""
import time

import pytest
from src.romm_client import RommClient, RommConflict
from tests import mock_romm


def test_register_device_once(romm):
    a = romm.register_device("romm_tools on test", "2.0.0")
    b = romm.register_device("romm_tools on test", "2.0.0")
    assert a and a == b
    assert [d["client"] for d in romm.list_devices()] == ["romm_tools"]


def test_romm_refuses_a_stale_upload_from_this_device(romm, tmp_path):
    romm.device_id = romm.register_device("romm_tools on test", "2.0.0")
    f = tmp_path / "Lantern Keep (USA).srm"
    f.write_bytes(b"v1")
    first = romm.upload("saves", f, 13, None, content_hash="h1")
    # another device changes RomM's copy...
    romm._request("PUT", f"/api/saves/{first['id']}", files={"saveFile": ("x.srm", b"from the deck")})
    f.write_bytes(b"v2 written before we saw the deck's save")
    with pytest.raises(RommConflict):
        romm.upload("saves", f, 13, None, content_hash="h2")
    # ...and choosing "keep mine" may overwrite it
    assert romm.upload("saves", f, 13, None, overwrite=True)["id"] == first["id"]


def test_held_save_is_uploaded_as_a_new_version(romm, tmp_path):
    f = tmp_path / "Orbit Golf (USA).srm"
    f.write_bytes(b"new")
    item = next(i for i in romm.list_all("saves") if i["rom_id"] == 42)
    romm._request("POST", f"/debug/hold/{item['id']}")
    with pytest.raises(RommConflict):
        romm.upload("saves", f, 42, item["id"])
    assert romm.upload("saves", f, 42, None)["id"] != item["id"]


def test_download_receipt_is_sent_with_a_device(romm):
    romm.device_id = romm.register_device("romm_tools on test", "2.0.0")
    item = romm.list_all("saves")[0]
    romm.confirm_downloaded("saves", item["id"], item.get("content_hash"))
    assert (romm.device_id, item["id"]) in mock_romm.S.device_sync


def test_pairing(romm):
    start = romm.pair_start("romm_tools-test", "romm_tools on test", "2.0.0")
    assert start["user_code"] and "pair/device" in start["verification_path_complete"]
    assert romm.pair_poll(start["device_code"]) is None           # not approved yet
    romm._request("POST", "/debug/pair/approve", params={"user_code": start["user_code"]})
    got = romm.pair_poll(start["device_code"])
    assert got["access_token"].startswith("rmm_") and got["device_id"]


def test_pairing_denied(romm):
    start = romm.pair_start("romm_tools-test", "romm_tools on test", "2.0.0")
    romm._request("POST", "/debug/pair/approve", params={"user_code": start["user_code"], "deny": "true"})
    with pytest.raises(RuntimeError, match="denied"):
        romm.pair_poll(start["device_code"])


def test_memory_card_round_trip(romm):
    card = romm.create_card("Mcd001.ps2", "pcsx2")
    romm.upload_card_version(card["id"], "Mcd001.ps2", b"\x00card")
    versions = romm.card_versions(card["id"])
    import io
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(romm.download_card_version(versions[0]["id"])))
    assert z.read("Mcd001.ps2") == b"\x00card"
    assert romm.list_cards("pcsx2")[0]["id"] == card["id"]


def test_supported_platforms_and_version(romm):
    slugs = {p["slug"] for p in romm.supported_platforms()}
    assert {"snes", "psx"} <= slugs
    assert romm.at_least("4.0.0")


def test_pairing_from_the_settings_page_saves_the_token(romm, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from src import devices
    st = devices.start_pairing(romm, "2.0.0")
    assert st["status"] == "waiting" and st["user_code"] and st["link"].startswith(romm.url)
    romm._request("POST", "/debug/pair/approve", params={"user_code": st["user_code"]})
    for _ in range(100):
        if devices.pairing_status()["status"] != "waiting":
            break
        time.sleep(0.1)
    assert devices.pairing_status()["status"] == "paired" and devices.has_paired_token()
    assert romm.api_token == "rmm_mock_paired_token" and romm.device_id
    fresh = RommClient(romm_url=romm.url, auth_type="http", romm_username="u", romm_password="p")
    devices.apply_saved(fresh)                       # next start: the paired token replaces the login
    assert fresh.auth_type == "api" and fresh.device_id == romm.device_id
    devices.forget(fresh, ("http", ""))
    assert not devices.has_paired_token() and fresh.auth_type == "http"


def test_devices_page_lists_who_synced_what(romm, tmp_path):
    from types import SimpleNamespace
    from src import device_overview
    from src.sync_state import STATE
    romm.device_id = romm.register_device("romm_tools on test", "2.0.0")
    f = tmp_path / "Lantern Keep (USA).srm"
    f.write_bytes(b"mine")
    romm.upload("saves", f, 13, None)
    game = SimpleNamespace(name="Lantern Keep (USA)", platform="snes", is_matched=True, romm_id=13,
                           romm_row={"platform_display_name": "SNES"})
    STATE.orchestrator = SimpleNamespace(lcl=SimpleNamespace(games={"x": game}))
    try:
        d = device_overview.overview(romm, force=True)
    finally:
        STATE.orchestrator = None
    row = next(r for r in d["rows"] if r["file"] == "Lantern Keep (USA).srm")
    assert row["syncs"][romm.device_id]["current"] is True
    assert d["romm_devices"][0]["this_app"] is True
