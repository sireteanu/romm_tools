"""Devices page: which devices last synced each save, and when (romm_tools 2.0).

Sources: RomM's device list and each save's `device_syncs` (RomM 5.4+, needs this app registered as a device and
devices.read), plus Syncthing's devices when the Syncthing integration is set up. Only games in your sync folders
are listed. Read when the page asks, cached for a minute.
"""
from __future__ import annotations

import time
from typing import Dict, List

from .sync_files import _VERSION_TAG
from .sync_state import STATE

_cache: Dict[str, object] = {"at": 0.0, "value": None}


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
        for it in client.list_saves_with_syncs():
            g = games.get(it.get("rom_id"))
            if g is None:
                continue
            k = (it["rom_id"], _VERSION_TAG.sub("", it.get("file_name", "")))
            if k not in newest or (it.get("updated_at") or "") > (newest[k].get("updated_at") or ""):
                newest[k] = it
        for (rom_id, name), it in sorted(newest.items(), key=lambda kv: (games[kv[0][0]].platform, games[kv[0][0]].name)):
            g = games[rom_id]
            syncs = {}
            for s in it.get("device_syncs") or []:
                syncs[s["device_id"]] = {"at": s.get("last_synced_at"), "current": bool(s.get("is_current"))}
            origin = it.get("origin_device_id")
            rows.append({"game": g.name, "system": (g.romm_row or {}).get("platform_display_name") or g.platform,
                         "file": name, "updated_at": it.get("updated_at"), "emulator": it.get("emulator"),
                         "origin": (by_id.get(origin) or {}).get("name") or origin, "syncs": syncs})
    used = {d for r in rows for d in r["syncs"]}
    shown = [d for d in devices if d["id"] in used or d["id"] == client.device_id]
    shown.sort(key=lambda d: (d["id"] != client.device_id, (d.get("name") or "").lower()))
    value = {"romm_devices": [{"id": d["id"], "name": d.get("name") or d.get("client") or d["id"],
                               "client": d.get("client"), "last_seen": d.get("last_seen"),
                               "this_app": d["id"] == client.device_id} for d in shown],
             "registered": bool(client.device_id), "rows": rows, "syncthing": syncthing.overview()}
    _cache.update(at=time.monotonic(), value=value)
    return value
