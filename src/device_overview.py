"""Devices page: which devices last synced each save, and when (romm_tools 2.0).

Sources: RomM's device list and each save's `device_syncs` (RomM 5.4+, needs this app registered as a device and
devices.read), plus Syncthing's devices when the Syncthing integration is set up. Only games in your sync folders
are listed. Read when the page asks, cached for a minute.
"""
from __future__ import annotations

import time
from typing import Dict, List

from .sync_files import _VERSION_TAG, save_alias
from .sync_state import STATE

_cache: Dict[str, object] = {"at": 0.0, "value": None}


def client_kind(device: dict) -> str:
    """'grout' | 'retroarch' | 'romm_tools' | 'other' for a RomM device."""
    c = f"{device.get('client') or ''} {device.get('name') or ''}".lower()
    for k in ("grout", "retroarch", "romm_tools"):
        if k in c:
            return k
    return "other"


def overview(client, force: bool = False) -> dict:
    if not force and _cache["value"] is not None and time.monotonic() - float(_cache["at"]) < 60:
        return _cache["value"]  # type: ignore[return-value]
    from . import syncthing
    devices = client.list_devices() if client.device_id else []
    by_id = {d["id"]: d for d in devices}
    orch = STATE.orchestrator
    games = {}
    if orch is not None and orch.lcl is not None:
        for g in orch.lcl.games.values():
            if g.is_matched:
                games[g.romm_id] = g
    rows: List[dict] = []
    if games:
        newest: Dict[tuple, dict] = {}
        allsyncs: Dict[tuple, dict] = {}
        for it in client.list_saves_with_syncs():
            g = games.get(it.get("rom_id"))
            if g is None:
                continue
            name = _VERSION_TAG.sub("", it.get("file_name", ""))
            # one game's save under another device's name ("Game.gba.sav" from Grout, "Game.srm") is one row
            k = (it["rom_id"], save_alias(name) or name)
            if k not in newest or (it.get("updated_at") or "") > (newest[k].get("updated_at") or ""):
                newest[k] = it
            for s in it.get("device_syncs") or []:
                cur = allsyncs.setdefault(k, {}).get(s["device_id"])
                if cur is None or (s.get("last_synced_at") or "") > (cur["at"] or ""):
                    allsyncs[k][s["device_id"]] = {"at": s.get("last_synced_at"), "current": False,
                                                   "_item": it["id"], "_cur": bool(s.get("is_current"))}
        for k, it in sorted(newest.items(), key=lambda kv: (games[kv[0][0]].platform, games[kv[0][0]].name)):
            rom_id = k[0]
            name = _VERSION_TAG.sub("", it.get("file_name", ""))
            g = games[rom_id]
            syncs = {}
            for dev, s in (allsyncs.get(k) or {}).items():
                # up to date = it last synced the newest copy, and RomM says that copy is current for it
                syncs[dev] = {"at": s["at"], "current": s["_cur"] and s["_item"] == it["id"]}
            origin = it.get("origin_device_id")
            rows.append({"game": g.name, "system": (g.romm_row or {}).get("platform_display_name") or g.platform,
                         "file": name, "updated_at": it.get("updated_at"), "emulator": it.get("emulator"),
                         "origin": (by_id.get(origin) or {}).get("name") or origin, "syncs": syncs})
    used = {d for r in rows for d in r["syncs"]}
    shown = [d for d in devices if d["id"] in used or d["id"] == client.device_id]
    shown.sort(key=lambda d: (d["id"] != client.device_id, (d.get("name") or "").lower()))
    value = {"romm_devices": [{"id": d["id"], "name": d.get("name") or d.get("client") or d["id"],
                               "client": d.get("client"), "kind": client_kind(d), "last_seen": d.get("last_seen"),
                               "this_app": d["id"] == client.device_id} for d in shown],
             "registered": bool(client.device_id), "rows": rows, "syncthing": syncthing.overview()}
    _cache.update(at=time.monotonic(), value=value)
    return value
