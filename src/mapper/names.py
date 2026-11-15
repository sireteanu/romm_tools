"""Game names page: RomM's name for each game next to the <name> in your frontends' gamelist.xml files, and
renaming games in RomM (one or many, with Undo). Part of ROM folders; served under /roms/api/names."""
from __future__ import annotations

import json
import os
import threading
from typing import Any

from fastapi import APIRouter, Body
from loguru import logger

import sys

S = sys.modules[__package__ + ".server"]  # the server module importing this one (also when reloaded)

router = APIRouter()

# ---------------------------------------------------------------- game names (gamelist.xml -> RomM)
# The Game names page: RomM's name for each game next to the <name> in the frontend's gamelist.xml,
# and a way to give RomM the gamelist's name (or one you type). See gamelists.py.

NAMES_FILE = os.path.join(S.CONFIG_DIR, "game-names.json")
NAMES_HISTORY = 20             # batches of renames kept for Undo
NAMES_MAX_BATCH = 2000
names_lock = threading.Lock()          # game-names.json
names_job_lock = threading.Lock()      # held while gamelists and RomM are read
_names = {"result": None, "at": None, "error": None, "step": "", "done": 0, "total": None}


def names_saved():
    try:
        with open(NAMES_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return {"folders": [str(x) for x in data.get("folders") or []],
            "ignored": {str(k): str(v) for k, v in (data.get("ignored") or {}).items()},
            "history": list(data.get("history") or [])[-NAMES_HISTORY:]}


def names_save(data):
    S.atomic_write(NAMES_FILE, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def names_mapped_folders():
    """[(slug, folder)] - every platform folder on the RomM library page (the folder RomM reads as
    roms/<slug>). Uses the folder list the RomM library page already read when there is one."""
    saved = S.romm_saved()
    if not saved.get("sources"):
        return []
    m, _saved, error = S.romm_mapping(reuse=True)
    if m is None:
        return []
    return [(p["slug"], os.path.join(m.base, p["mount"]) if m.base else p["mount"]) for p in m.platforms]


def names_read():
    """Read RomM's platforms, the gamelists, then the ROMs of the platforms that have one."""
    from . import gamelists
    client = S.romm_client()
    if client is None:
        raise RuntimeError("No RomM address is set (ROMM_URL in the container settings).")
    _names.update(step="Reading RomM's platforms", done=0, total=None)
    platforms = client.list_platforms()
    _names.update(step="Looking for gamelist.xml files")
    saved = names_saved()
    folders = gamelists.platform_folders(names_mapped_folders(), saved["folders"], platforms)
    skip = S.romm.options_from({"romm": S.romm_saved()})["skip_names"]
    found = gamelists.collect(folders, skip)
    have = {pid for pid, files in found.items() if files}
    targets = [(p["id"], p.get("display_name") or p.get("name") or p.get("slug")) for p in platforms if p["id"] in have]
    roms = []
    if targets:
        keep = ("id", "name", "fs_name", "fs_path", "platform_id")

        def trim(page):
            return [{k: r.get(k) for k in keep} for r in page]

        def progress(label, fetched, total):
            _names.update(step=f"Reading RomM's games: {label}", done=fetched, total=total)

        roms = client.get_full_library(targets, trim=trim, on_progress=progress)["items"]
    result = gamelists.compare(platforms, found, roms, names_saved()["ignored"])
    s = result["summary"]
    S.log(f"Game names: {s['gamelists']} gamelist(s), {s['different']} name(s) differ from RomM")
    return result


def start_names_read():
    """Read in a background thread (a big library takes a while); the page follows /api/names/progress."""
    if not names_job_lock.acquire(blocking=False):
        return False
    _names.update(error=None, step="Starting", done=0, total=None)

    def worker():
        try:
            _names["result"] = names_read()
            _names["at"] = S.now_iso()
        except Exception as e:  # noqa: BLE001 - shown on the page
            _names["error"] = str(e)
            S.log(f"Game names: reading failed: {e}")
        finally:
            names_job_lock.release()

    if S.ROMM_BACKGROUND:
        threading.Thread(target=worker, name="game-names-read", daemon=True).start()
    else:
        worker()
    return True


def names_progress():
    return {"running": names_job_lock.locked(), "step": _names["step"], "done": _names["done"],
            "total": _names["total"]}


def names_view():
    saved = names_saved()
    last = saved["history"][-1] if saved["history"] else None
    base = {"folders": saved["folders"], "error": _names["error"], "at": _names["at"],
            "romm": bool(S.romm_client()), "mapped": len(S.romm_saved().get("sources") or []),
            "undo": {"time": last["time"], "count": len(last["changes"])} if last else None}
    if names_job_lock.locked():
        return {**base, "reading": names_progress()}
    res = _names["result"] or {"rows": [], "gamelists": [], "no_gamelist": [], "summary": {}}
    ignored = saved["ignored"]
    rows = [{**r, "ignored": ignored.get(str(r["id"])) == r["gamelist_name"]} for r in res["rows"]]
    summary = dict(res["summary"])
    if rows or summary:
        summary["ignored"] = sum(r["ignored"] for r in rows)
        summary["different"] = len(rows) - summary["ignored"]
    return {**base, "rows": rows, "gamelists": res["gamelists"], "no_gamelist": res.get("no_gamelist", []),
            "summary": summary}


@router.get("/api/names")
def api_names(fresh: str = ""):
    if fresh == "1" or (_names["result"] is None and _names["error"] is None):
        if S.romm_client() is not None:
            start_names_read()
    return S.jsonify(names_view())


@router.get("/api/names/progress")
def api_names_progress():
    return S.jsonify(names_progress())


@router.put("/api/names/options")
def api_names_options(body: Any = Body(None)):
    body = body or {}
    raw = body.get("folders") or []
    items = raw.splitlines() if isinstance(raw, str) else list(raw)
    folders = []
    for v in items:
        v = str(v or "").strip().rstrip("/")
        if not v:
            continue
        if not v.startswith("/"):
            return S.jsonify({"error": f"{v}: a gamelist folder must be a full path starting with /"}, 400)
        if v not in folders:
            folders.append(v)
    with names_lock:
        data = names_saved()
        data["folders"] = folders
        names_save(data)
    S.log("Game names: extra gamelist folders: " + (", ".join(folders) or "none"))
    start_names_read()
    return S.jsonify(names_view())


@router.put("/api/names/ignore")
def api_names_ignore(body: Any = Body(None)):
    """Keep RomM's name for these games: they're hidden until their gamelist name changes."""
    body = body or {}
    rows = {str(r["id"]): r for r in (_names["result"] or {}).get("rows", [])}
    with names_lock:
        data = names_saved()
        for i in body.get("ids") or []:
            r = rows.get(str(i))
            if r is None:
                continue
            if body.get("ignore", True):
                data["ignored"][str(i)] = r["gamelist_name"]
            else:
                data["ignored"].pop(str(i), None)
        names_save(data)
    return S.jsonify(names_view())


def names_rename(changes, client):
    """Rename in RomM -> (done [{id, old, new, platform, file}], failed [{id, error}])."""
    done, failed = [], []
    for c in changes:
        try:
            got = client.rename_rom(c["id"], c["new"])
            done.append({**c, "new": got.get("name") or c["new"]})
        except Exception as e:  # noqa: BLE001 - reported per game
            failed.append({"id": c["id"], "error": str(e)})
    return done, failed


@router.post("/api/names/apply")
def api_names_apply(body: Any = Body(None)):
    """Give these games a new name in RomM: {"changes": [{"id", "name"}]} - the gamelist's name or
    one you typed. Only games on the list can be renamed (RomM's current name is known for Undo)."""
    from . import gamelists
    if names_job_lock.locked():
        return S.jsonify({"error": "Still reading the gamelists and RomM - try again in a moment."}, 409)
    client = S.romm_client()
    if client is None:
        return S.jsonify({"error": "No RomM address is set (ROMM_URL in the container settings)."}, 400)
    body = body or {}
    asked = body.get("changes") or []
    if not isinstance(asked, list) or not asked:
        return S.jsonify({"error": "Nothing to rename."}, 400)
    if len(asked) > NAMES_MAX_BATCH:
        return S.jsonify({"error": f"At most {NAMES_MAX_BATCH} games at once."}, 400)
    rows = {r["id"]: r for r in (_names["result"] or {}).get("rows", [])}
    changes, failed = [], []
    for c in asked:
        try:
            rid = int(c.get("id"))
            new = gamelists.check_name(c.get("name"))
        except (TypeError, ValueError, AttributeError) as e:
            failed.append({"id": c.get("id") if isinstance(c, dict) else None, "error": str(e)})
            continue
        r = rows.get(rid)
        if r is None:
            failed.append({"id": rid, "error": "not on the list any more - refresh"})
            continue
        if new != r["romm_name"]:
            changes.append({"id": rid, "old": r["romm_name"], "new": new, "platform": r["platform"],
                            "file": r["file"]})
    done, bad = names_rename(changes, client)
    failed += bad
    if done:
        with names_lock:
            data = names_saved()
            data["history"] = (data["history"] + [{"time": S.now_iso(), "changes": done}])[-NAMES_HISTORY:]
            names_save(data)
        res = _names["result"]
        by_id = {d["id"]: d["new"] for d in done}
        keep = []
        for r in res["rows"]:
            if r["id"] in by_id:
                if by_id[r["id"]] == r["gamelist_name"]:
                    res["summary"]["same"] = res["summary"].get("same", 0) + 1
                    continue
                r = {**r, "romm_name": by_id[r["id"]], "case_only": by_id[r["id"]].casefold() == r["gamelist_name"].casefold()}
            keep.append(r)
        res["rows"] = keep
        for d in done:
            logger.info(f"[ROM folders] Game names: {d['platform']} / {d['file']}: {d['old']!r} -> {d['new']!r}")
        S.log(f"Game names: renamed {len(done)} game(s) in RomM" + (f", {len(failed)} failed" if failed else ""))
    elif failed:
        S.log(f"Game names: {len(failed)} rename(s) failed: {failed[0]['error']}")
    return S.jsonify({**names_view(), "done": len(done), "failed": failed})


@router.post("/api/names/undo")
def api_names_undo():
    """Put back the names the last batch of renames replaced, then read everything again."""
    if names_job_lock.locked():
        return S.jsonify({"error": "Still reading the gamelists and RomM - try again in a moment."}, 409)
    client = S.romm_client()
    if client is None:
        return S.jsonify({"error": "No RomM address is set (ROMM_URL in the container settings)."}, 400)
    with names_lock:
        data = names_saved()
        if not data["history"]:
            return S.jsonify({"error": "Nothing to undo."}, 400)
        last = data["history"][-1]
    back = [{**c, "old": c["new"], "new": c["old"]} for c in last["changes"] if c.get("old")]
    done, failed = names_rename(back, client)
    with names_lock:
        data = names_saved()
        if data["history"] and data["history"][-1]["time"] == last["time"]:
            if failed:   # keep the ones that couldn't be put back, so Undo can try them again
                left = {f["id"] for f in failed}
                data["history"][-1]["changes"] = [c for c in last["changes"] if c["id"] in left]
            else:
                data["history"].pop()
            names_save(data)
    S.log(f"Game names: undo put back {len(done)} name(s)" + (f", {len(failed)} failed" if failed else ""))
    start_names_read()
    return S.jsonify({**names_view(), "done": len(done), "failed": failed})


