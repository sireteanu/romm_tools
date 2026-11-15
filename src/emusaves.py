"""Saves of standalone emulators that don't use RetroArch's one-file-per-game layout (romm_tools 2.0).

Each emulator folder you add on the Settings page (path inside the container + kind + RomM platform) is read as
*units*. A unit is one thing synced with RomM:

  kind         folder you point at          per-game units -> RomM saves          shared units -> RomM memory cards
  duckstation  DuckStation's memcards/      "<Game title>_1.mcd" (per-game cards)   shared_card_1.mcd, shared_card_2.mcd
  pcsx2        PCSX2's memcards/            -                                       Mcd001.ps2 ... and folder memory
                                                                                    cards (a .ps2 folder, zipped)
  dolphin      Dolphin's GC/ folder         GCI files of one game, zipped as        MemoryCardA.USA.raw ... (raw cards)
                                            "GCI-<game code>.zip"
  ppsspp       PPSSPP's PSP/SAVEDATA/       each save folder, zipped as             -
                                            "PSP-<folder>.zip" (RomM's own name for
                                            PPSSPP folders, so RomM's RetroArch
                                            Cloud Sync and this app share them)

Per-game units are matched to a RomM game by title (DuckStation's card name, PPSSPP's PARAM.SFO title), or by a
link you make by hand (Settings -> Standalone emulators -> Link). Dolphin GCI files carry only a game code, so they
need a link once per game.

Rules are the same as the rest of save sync: decide() on (local, RomM, last synced state), nothing is overwritten
without a backup, unclear cases wait for your decision. Deletions are not carried over for these units.
"""
from __future__ import annotations

import hashlib
import io
import re
import struct
import threading
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from .sync_state import STATE, PendingAction, utcnow_iso

KINDS = {
    "duckstation": {"label": "DuckStation (PS1 memory cards)", "platform": "psx", "emulator": "duckstation",
                    "hint": "DuckStation's memcards folder"},
    "pcsx2": {"label": "PCSX2 (PS2 memory cards)", "platform": "ps2", "emulator": "pcsx2",
              "hint": "PCSX2's memcards folder"},
    "dolphin": {"label": "Dolphin (GameCube saves)", "platform": "ngc", "emulator": "dolphin",
                "hint": "Dolphin's GC folder (holds USA / EUR / JAP)"},
    "ppsspp": {"label": "PPSSPP (PSP saves)", "platform": "psp", "emulator": "ppsspp",
               "hint": "PPSSPP's PSP/SAVEDATA folder"},
}
_lock = threading.RLock()
_status: Dict[str, dict] = {}           # folder id -> {units, matched, unmatched[...], last_sync, error}


# region folders (settings.json "emu_folders")
def folders() -> List[dict]:
    from .settings import load
    return [f for f in (load().get("emu_folders") or []) if f.get("kind") in KINDS]


def add_folder(kind: str, path: str, platform: Optional[str] = None) -> dict:
    from .settings import load, save
    if kind not in KINDS:
        raise ValueError("Pick one of the listed emulators.")
    p = Path(path.strip())
    if not p.is_absolute():
        raise ValueError("Give the folder's full path inside the container, starting with /.")
    if not p.is_dir():
        raise ValueError(f"{p} isn't a folder inside the container. Map it into the container first.")
    if str(p).rstrip("/") in ("/", "/data") or str(p).startswith("/data/"):
        raise ValueError("That folder can't be used.")
    data = load()
    cur = data.get("emu_folders") or []
    if any(Path(f["path"]) == p for f in cur):
        raise ValueError("That folder is already in the list.")
    n = 1 + sum(1 for f in cur if f["kind"] == kind)
    entry = {"id": f"{kind}-{n}", "kind": kind, "path": str(p),
             "platform": (platform or KINDS[kind]["platform"]).strip().lower()}
    while any(f["id"] == entry["id"] for f in cur):
        n += 1
        entry["id"] = f"{kind}-{n}"
    data["emu_folders"] = cur + [entry]
    save(data)
    return entry


def remove_folder(fid: str) -> None:
    from .settings import load, save
    data = load()
    data["emu_folders"] = [f for f in (data.get("emu_folders") or []) if f.get("id") != fid]
    save(data)
    _status.pop(fid, None)
# endregion


# region units
@dataclass
class Unit:
    folder: dict
    name: str                    # name on RomM: "Crash_1.mcd", "PSP-ULUS10041.zip", "GCI-GALE.zip", "Mcd001.ps2"
    mode: str                    # "save" (per game, RomM save) | "card" (shared, RomM memory card)
    members: Dict[str, Path]     # name inside the bundle (or the file name) -> path on disk
    bundle: bool = False         # zipped on RomM (several files, or a folder)
    match: str = ""              # what is matched to a RomM game: a title or a game code
    title: str = ""              # shown on the page

    @property
    def key(self) -> str:
        return f"emu:{self.folder['id']}:{self.name}"

    @property
    def root(self) -> Path:
        return Path(self.folder["path"])

    def read(self) -> bytes:
        if not self.bundle:
            return next(iter(self.members.values())).read_bytes()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for arc in sorted(self.members):
                info = zipfile.ZipInfo(arc, date_time=(1980, 1, 1, 0, 0, 0))   # same bytes for the same files
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, self.members[arc].read_bytes())
        return buf.getvalue()

    def hash(self) -> str:
        """md5 of the file, or of the bundle's (name, md5) list - independent of zip details."""
        if not self.bundle:
            return _md5_path(next(iter(self.members.values())))
        h = hashlib.md5()
        for arc in sorted(self.members):
            h.update(arc.encode() + b"\0" + _md5_path(self.members[arc]).encode() + b"\n")
        return h.hexdigest()

    def mtime(self) -> datetime:
        return datetime.fromtimestamp(max(p.stat().st_mtime for p in self.members.values()), timezone.utc)

    def size(self) -> int:
        return sum(p.stat().st_size for p in self.members.values())


def _md5_path(p: Path) -> str:
    from .sync_files import cached_md5
    return cached_md5(p)


def bundle_hash(data: bytes) -> Optional[str]:
    """The hash Unit.hash() gives for the same files, from a zip downloaded from RomM."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            h = hashlib.md5()
            for arc in sorted(n for n in z.namelist() if not n.endswith("/")):
                h.update(arc.encode() + b"\0" + hashlib.md5(z.read(arc)).hexdigest().encode() + b"\n")
            return h.hexdigest()
    except zipfile.BadZipFile:
        return None


def parse_sfo(data: bytes) -> Dict[str, object]:
    """PARAM.SFO key/values (TITLE, SAVEDATA_DIRECTORY...)."""
    if len(data) < 20 or data[:4] != b"\0PSF":
        return {}
    key_start, data_start, count = struct.unpack_from("<III", data, 8)
    out = {}
    for i in range(min(count, 64)):
        off = 20 + i * 16
        if off + 16 > len(data):
            break
        k_off, fmt, length, _max, d_off = struct.unpack_from("<HHIII", data, off)
        k_end = data.find(b"\0", key_start + k_off)
        key = data[key_start + k_off:k_end].decode("utf-8", "replace")
        raw = data[data_start + d_off:data_start + d_off + length]
        out[key] = struct.unpack("<I", raw[:4])[0] if fmt == 0x0404 and len(raw) >= 4 else \
            raw.split(b"\0", 1)[0].decode("utf-8", "replace")
    return out


def scan(folder: dict) -> List[Unit]:
    """The units in one emulator folder (reads file names and, for PPSSPP, each PARAM.SFO)."""
    root, kind = Path(folder["path"]), folder["kind"]
    if not root.is_dir():
        raise FileNotFoundError(f"{root} isn't a folder inside the container")
    units: List[Unit] = []
    if kind == "duckstation":
        for p in sorted(root.glob("*.mcd")):
            if p.name.lower().startswith("shared_card"):
                units.append(Unit(folder, p.name, "card", {p.name: p}, title=p.stem))
            else:
                title = re.sub(r"_\d+$", "", p.stem)
                units.append(Unit(folder, p.name, "save", {p.name: p}, match=title, title=title))
    elif kind == "pcsx2":
        for p in sorted(root.iterdir()):
            if p.is_file() and p.suffix.lower() in (".ps2", ".mcd", ".bin"):
                units.append(Unit(folder, p.name, "card", {p.name: p}, title=p.stem))
            elif p.is_dir() and p.suffix.lower() == ".ps2":   # folder memory card
                members = {str(f.relative_to(p)): f for f in sorted(p.rglob("*")) if f.is_file()}
                if members:
                    units.append(Unit(folder, p.name + ".zip", "card", members, bundle=True, title=p.name))
    elif kind == "dolphin":
        for p in sorted(root.rglob("*.raw")):
            rel = str(p.relative_to(root))
            if rel.count("/") <= 1:
                units.append(Unit(folder, rel.replace("/", "_"), "card", {rel: p}, title=rel))
        games: Dict[str, Dict[str, Path]] = {}
        for p in sorted(root.rglob("*.gci")):
            parts = p.name.split("-")
            code = parts[1] if len(parts) >= 3 and len(parts[1]) == 4 else p.stem[:4]
            games.setdefault(code.upper(), {})[str(p.relative_to(root))] = p
        for code, members in games.items():
            units.append(Unit(folder, f"GCI-{code}.zip", "save", members, bundle=True, match=code, title=code))
    elif kind == "ppsspp":
        for d in sorted(x for x in root.iterdir() if x.is_dir()):
            members = {f.name: f for f in sorted(d.iterdir()) if f.is_file()}
            if not members:
                continue
            title = ""
            sfo = d / "PARAM.SFO"
            if sfo.exists():
                try:
                    title = str(parse_sfo(sfo.read_bytes()).get("TITLE") or "")
                except Exception:  # noqa: BLE001
                    title = ""
            serial = re.sub(r"DATA\d+$", "", d.name, flags=re.IGNORECASE)
            units.append(Unit(folder, f"PSP-{d.name}.zip", "save", members, bundle=True,
                              match=title or serial, title=title or d.name))
    return units


def unit_target(folder: dict, name: str) -> Optional[Dict[str, Path]]:
    """Where a RomM file with this name lands in the folder (for files only on RomM). None = not ours."""
    root, kind = Path(folder["path"]), folder["kind"]
    if kind == "duckstation" and name.lower().endswith(".mcd"):
        return {name: root / name}
    if kind == "ppsspp":
        m = re.match(r"^PSP-(.+?)(?: \[.*\])?\.zip$", name)
        if m:
            return {"__dir__": root / m.group(1)}
    if kind == "dolphin" and re.match(r"^GCI-\w{4}\.zip$", name):
        return {"__dir__": root}
    return None
# endregion


# region matching
def link_key(folder: dict, unit_match: str) -> tuple:
    return f"emu:{folder['id']}", unit_match


def match_rom(unit: Unit, roms: List[dict]) -> Optional[dict]:
    from . import links
    from .library_classes import LibraryScanner
    plat, game = link_key(unit.folder, unit.match)
    rid = links.get(plat, game)
    if rid is not None:
        return next((r for r in roms if r["id"] == rid), None)
    if not unit.match or unit.folder["kind"] == "dolphin":
        return None
    return (LibraryScanner.find_rom(unit.match, roms, exact_only=True)
            or LibraryScanner.find_rom_by_title(unit.match, roms))
# endregion


# region sync
def _engine():
    from .sync_engine import SyncEngine
    return SyncEngine()


def _remote_saves_for(remote_saves: List[dict], name: str) -> List[dict]:
    from .sync_files import _VERSION_TAG
    return [it for it in remote_saves if _VERSION_TAG.sub("", it.get("file_name", "")) == name]


def sync_all(srv=None) -> dict:
    """Sync every emulator folder once. Called after full syncs, RomM-change syncs and folder changes."""
    fl = folders()
    if not fl:
        return {}
    eng = _engine()
    if srv is None and STATE.orchestrator is not None:
        srv = STATE.orchestrator.srv
    library = srv.library if srv is not None else []
    summary = {"pushed": 0, "pulled": 0, "queued": 0, "errors": 0}
    with STATE.sync_lock:
        try:
            remote_saves = eng.romm.list_all("saves")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Standalone emulators: couldn't read RomM's saves ({e})")
            return summary
        cards = None
        for folder in fl:
            st = {"units": 0, "matched": 0, "unmatched": [], "cards": 0, "last_sync": utcnow_iso(), "error": None}
            try:
                units = scan(folder)
            except Exception as e:  # noqa: BLE001
                st["error"] = str(e)
                _status[folder["id"]] = st
                logger.error(f"Standalone emulators: {folder['path']}: {e}")
                continue
            roms = [r for r in library if r.get("platform_slug") == folder["platform"]]
            st["units"] = len(units)
            seen = set()
            for u in units:
                seen.add(u.name)
                try:
                    if u.mode == "card":
                        if cards is None:
                            cards = eng.romm.list_cards()
                        st["cards"] += 1
                        _sync_card(eng, u, cards, summary)
                        continue
                    rom = match_rom(u, roms)
                    if rom is None:
                        st["unmatched"].append({"name": u.name, "match": u.match, "title": u.title})
                        continue
                    st["matched"] += 1
                    _sync_save(eng, u, rom, _remote_saves_for([s for s in remote_saves if s["rom_id"] == rom["id"]],
                                                            u.name), summary)
                except Exception as e:  # noqa: BLE001
                    summary["errors"] += 1
                    logger.error(f"Standalone emulators: {u.name}: {e}")
            _pull_remote_only(eng, folder, roms, remote_saves, seen, summary)
            if folder["kind"] in ("duckstation", "pcsx2", "dolphin"):
                if cards is None:
                    cards = eng.romm.list_cards()
                _pull_remote_cards(eng, folder, cards, seen, summary)
            _status[folder["id"]] = st
        STATE.save()
    if any(summary.values()):
        logger.info(f"[EMULATORS] uploaded {summary['pushed']}, downloaded {summary['pulled']}, "
                    f"awaiting approval {summary['queued']}, errors {summary['errors']}")
    return summary


def _action(u: Unit, kind: str, rom: Optional[dict], rf: Optional[dict], reason: str = "") -> PendingAction:
    return PendingAction(
        kind=kind, file_type="save", game=u.title or u.name, platform=u.folder["id"],
        rom_id=(rom or {}).get("id") or 0, file_name=u.name,
        local_path=str(next(iter(u.members.values()))) if u.members else None,
        local_hash=u.hash() if u.members else None, local_size=u.size() if u.members else None,
        local_mtime=u.mtime().isoformat() if u.members else None,
        romm_id=(rf or {}).get("id"), romm_file_name=(rf or {}).get("file_name"),
        romm_updated_at=(rf or {}).get("updated_at"), romm_size=(rf or {}).get("file_size_bytes"),
        emu={"key": u.key, "folder": u.folder["id"], "unit": u.name, "mode": u.mode}, reason=reason)


def _sync_save(eng, u: Unit, rom: dict, remote: List[dict], summary: dict) -> None:
    from .sync_files import LocalFile, parse_dt
    from .sync_rules import decide
    rf = max(remote, key=lambda it: parse_dt(it.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc)) \
        if remote else None
    baseline = STATE.get_baseline(u.key)
    lf = LocalFile("save", next(iter(u.members.values())), u.hash(), u.size(), u.mtime())
    if rf is not None and u.bundle:
        rf = dict(rf)
        if baseline and baseline.get("romm_id") == rf.get("id") and baseline.get("romm_updated_at") == rf.get("updated_at"):
            rf["content_hash"] = baseline.get("romm_hash")       # unchanged on RomM: no need to download
        else:
            rf["content_hash"] = bundle_hash(eng.romm.download_asset("saves", rf))
    d = decide(lf, rf, baseline, eng.cfg.PUSH_NEW_MODE, eng.pull_mode, False, "off", None)
    if d.kind is None or d.kind == "adopt":
        if d.kind == "adopt" or (rf and lf.hash == rf.get("content_hash") and not baseline):
            STATE.set_baseline(u.key, lf.hash, rf.get("updated_at"), rf.get("id"), rf.get("content_hash"), persist=False)
        STATE.drop_pending_for_key(u.key)
        return
    action = _action(u, d.kind, rom, rf, d.reason)
    if d.auto:
        STATE.drop_pending_for_key(u.key)
        ok, _msg = execute(action)
        summary["pushed" if d.kind.startswith("push") else "pulled"] += 1 if ok else 0
        summary["errors"] += 0 if ok else 1
    elif not STATE.is_dismissed(u.key, action.kind, action.local_hash, action.romm_updated_at):
        STATE.queue(action, persist=False)
        summary["queued"] += 1


def _pull_remote_only(eng, folder: dict, roms: List[dict], remote_saves: List[dict], seen: set, summary: dict):
    """RomM saves of this platform named like this emulator's units that the folder doesn't have yet."""
    from .sync_files import _VERSION_TAG
    from .sync_rules import decide
    rom_ids = {r["id"]: r for r in roms}
    newest: Dict[str, dict] = {}
    for it in remote_saves:
        if it["rom_id"] not in rom_ids:
            continue
        name = _VERSION_TAG.sub("", it.get("file_name", ""))
        if name in seen or unit_target(folder, name) is None:
            continue
        if name not in newest or (it.get("updated_at") or "") > (newest[name].get("updated_at") or ""):
            newest[name] = it
    for name, rf in newest.items():
        u = Unit(folder, name, "save", {}, bundle=name.lower().endswith(".zip"), title=rom_ids[rf["rom_id"]].get("name") or name)
        if STATE.get_baseline(u.key):
            continue   # was synced and is gone from the folder now: deletions aren't carried over here
        d = decide(None, rf, None, eng.cfg.PUSH_NEW_MODE, eng.pull_mode, False, "off", None)
        if d.kind != "pull_new":
            continue
        action = _action(u, "pull_new", rom_ids[rf["rom_id"]], rf, d.reason)
        if d.auto:
            ok, _ = execute(action)
            summary["pulled" if ok else "errors"] += 1
        elif not STATE.is_dismissed(u.key, action.kind, None, action.romm_updated_at):
            STATE.queue(action, persist=False)
            summary["queued"] += 1


def _pull_remote_cards(eng, folder: dict, cards: List[dict], seen: set, summary: dict) -> None:
    """Memory cards on RomM for this emulator that the folder doesn't have."""
    emulator = KINDS[folder["kind"]]["emulator"]
    for card in cards:
        if card.get("emulator") != emulator or card["name"] in seen:
            continue
        u = Unit(folder, card["name"], "card", {}, bundle=card["name"].lower().endswith(".zip"), title=card["name"])
        if STATE.get_baseline(u.key):
            continue
        latest = _card_latest(eng, card)
        if latest is None:
            continue
        action = _action(u, "pull_new", None, None)
        action.emu.update(card_id=card["id"], version_id=latest["id"], version_at=latest.get("updated_at"))
        action.romm_updated_at = latest.get("updated_at")
        if eng.pull_mode == "auto":
            ok, _ = execute(action)
            summary["pulled" if ok else "errors"] += 1
        elif eng.pull_mode == "confirm" and not STATE.is_dismissed(u.key, action.kind, None, action.romm_updated_at):
            STATE.queue(action, persist=False)
            summary["queued"] += 1


def _card_latest(eng, card: dict) -> Optional[dict]:
    versions = eng.romm.card_versions(card["id"])
    return versions[0] if versions else None


def _sync_card(eng, u: Unit, cards: List[dict], summary: dict) -> None:
    emulator = KINDS[u.folder["kind"]]["emulator"]
    card = next((c for c in cards if c["emulator"] == emulator and c["name"] == u.name), None)
    baseline = STATE.get_baseline(u.key)
    local_hash = u.hash()
    if card is None:
        kind, reason = "push_new", ""
        latest = None
    else:
        latest = _card_latest(eng, card)
        if latest is None:
            kind, reason = "push_update", ""
        elif not baseline:
            remote_hash = _card_hash(eng, u, latest)
            if remote_hash == local_hash:
                STATE.set_baseline(u.key, local_hash, latest.get("updated_at"), latest["id"], remote_hash, persist=False)
                return
            from .sync_files import parse_dt
            newer_local = u.mtime() > (parse_dt(latest.get("updated_at")) or u.mtime())
            kind = "push_update" if newer_local else "conflict"
            reason = ("" if newer_local else "RomM has a different copy of this memory card and this app hasn't "
                      "synced it before. Choose which one to keep.")
        else:
            local_changed = local_hash != baseline.get("local_hash")
            remote_changed = latest["id"] != baseline.get("romm_id")
            if not local_changed and not remote_changed:
                return
            kind = "conflict" if (local_changed and remote_changed) else ("push_update" if local_changed else "pull_update")
            reason = "The memory card changed both here and on RomM since the last sync." if kind == "conflict" else ""
    action = _action(u, kind, None, None, reason)
    action.emu.update(card_id=(card or {}).get("id"), version_id=(latest or {}).get("id"),
                      version_at=(latest or {}).get("updated_at"))
    action.romm_updated_at = (latest or {}).get("updated_at")
    auto = kind in ("push_new", "push_update") or (kind == "pull_update" and eng.pull_mode == "auto")
    if kind == "push_new" and eng.cfg.PUSH_NEW_MODE != "auto":
        auto = False
    if auto:
        ok, _ = execute(action)
        summary["pushed" if kind.startswith("push") else "pulled"] += 1 if ok else 0
        summary["errors"] += 0 if ok else 1
    elif not STATE.is_dismissed(u.key, action.kind, action.local_hash, action.romm_updated_at):
        STATE.queue(action, persist=False)
        summary["queued"] += 1


def _unzip(data: bytes) -> Dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist()
                if not n.endswith("/") and not n.startswith("/") and ".." not in Path(n).parts}


def _card_bytes(eng, version_id: int, u: Unit) -> Dict[str, bytes]:
    """{member: bytes} of a card version (RomM stores card images zipped)."""
    files = _unzip(eng.romm.download_card_version(version_id))
    if not u.bundle and len(files) == 1:
        return {next(iter(u.members or {u.name: None})): next(iter(files.values()))}
    return files


def _card_hash(eng, u: Unit, version: dict) -> Optional[str]:
    files = _card_bytes(eng, version["id"], u)
    if u.bundle and len(files) == 1 and next(iter(files)).lower().endswith(".zip"):
        files = _unzip(next(iter(files.values())))
    if not u.bundle:
        return hashlib.md5(next(iter(files.values()))).hexdigest() if files else None
    h = hashlib.md5()
    for arc in sorted(files):
        h.update(arc.encode() + b"\0" + hashlib.md5(files[arc]).hexdigest().encode() + b"\n")
    return h.hexdigest()


def _find_unit(action: PendingAction) -> Optional[Unit]:
    folder = next((f for f in folders() if f["id"] == action.emu.get("folder")), None)
    if folder is None:
        return None
    for u in scan(folder):
        if u.name == action.emu.get("unit"):
            return u
    target = unit_target(folder, action.emu.get("unit"))
    if target is not None:
        return Unit(folder, action.emu["unit"], action.emu.get("mode", "save"), {},
                    bundle=action.emu["unit"].lower().endswith(".zip"), title=action.game)
    if action.emu.get("mode") == "card":   # a card only on RomM
        return Unit(folder, action.emu["unit"], "card", {}, bundle=action.emu["unit"].lower().endswith(".zip"))
    return None


def execute(action: PendingAction, choice: Optional[str] = None):
    """Run one unit action (also from the approvals list). -> (ok, message)"""
    from .sync_errors import explain_error
    with STATE.sync_lock:
        action.status = "running"
        try:
            u = _find_unit(action)
            if u is None:
                raise _Stale("That emulator folder or file is gone.")
            kind = action.kind
            if kind == "conflict":
                if choice not in ("local", "romm"):
                    raise ValueError("For these files choose 'Keep mine' or 'Keep RomM's'.")
                kind = "push_update" if choice == "local" else "pull_update"
            if u.members and action.local_hash and u.hash() != action.local_hash:
                raise _Stale("The file changed after this was queued; it will be checked again on the next sync.")
            eng = _engine()
            msg = (_push(eng, u, action, overwrite=action.kind == "conflict") if kind.startswith("push")
                   else _pull(eng, u, action))
            STATE.clear_error(action.key)
            STATE.finish_action(action, "done", msg)
            logger.info(f"✔ {msg}")
            return True, msg
        except _Stale as e:
            STATE.finish_action(action, "stale", str(e))
            return False, str(e)
        except Exception as e:  # noqa: BLE001
            msg = explain_error(e, action)
            STATE.finish_action(action, "failed", msg)
            STATE.record_error(action, msg, detail=str(e))
            logger.error(f"✘ {action.kind} {u.name if 'u' in locals() and u else action.file_name} failed: {msg}")
            return False, msg


class _Stale(Exception):
    pass


def _push(eng, u: Unit, action: PendingAction, overwrite: bool = False) -> str:
    if eng.cfg.DRY_RUN:
        return f"[dry run] would upload {u.name}"
    data, h = u.read(), u.hash()
    emulator = KINDS[u.folder["kind"]]["emulator"]
    if u.mode == "card":
        card_id = action.emu.get("card_id")
        if not card_id:
            card_id = eng.romm.create_card(u.name, emulator)["id"]
        member = next(iter(u.members)) if not u.bundle else None
        if u.bundle:
            v = eng.romm._json("POST", f"/api/memory-cards/{card_id}/versions",
                               files={"cardFile": (u.name, data)}, timeout=300)
        else:
            v = eng.romm.upload_card_version(card_id, member, data)
        STATE.set_baseline(u.key, h, v.get("updated_at"), v.get("id"), h)
        return f"Uploaded memory card {u.name} to RomM"
    resp = eng.romm.upload("saves", next(iter(u.members.values())), action.rom_id, None, upload_name=u.name,
                           content=data, emulator=emulator, content_hash=None if u.bundle else h,
                           overwrite=overwrite)
    STATE.set_baseline(u.key, h, resp.get("updated_at"), resp.get("id"), h if u.bundle else resp.get("content_hash"))
    return f"Uploaded {u.title or u.name} ({u.name}) to RomM"


def _write(eng, dest: Path, content: bytes, platform: str):
    if dest.exists():
        eng._backup_local(dest, platform)
    eng._write_local(dest, content, datetime.now(timezone.utc))


def _pull(eng, u: Unit, action: PendingAction) -> str:
    if eng.cfg.DRY_RUN:
        return f"[dry run] would download {u.name}"
    platform = f"emulators/{u.folder['id']}"
    if u.mode == "card":
        vid = action.emu.get("version_id")
        files = _card_bytes(eng, vid, u)
        if u.bundle and len(files) == 1 and next(iter(files)).lower().endswith(".zip"):
            files = _unzip(next(iter(files.values())))
        if not u.bundle:
            dest = next(iter(u.members.values()), None) or (u.root / u.name)
            _write(eng, dest, next(iter(files.values())), platform)
        else:
            base = u.root / (u.name[:-4] if u.name.lower().endswith(".zip") else u.name)
            for arc, content in files.items():
                _write(eng, base / arc, content, platform)
        u2 = next((x for x in scan(u.folder) if x.name == u.name), None)
        h = u2.hash() if u2 else None
        STATE.set_baseline(u.key, h, action.emu.get("version_at"), vid, h)
        return f"Downloaded memory card {u.name} from RomM"
    item = eng.romm.get_asset("saves", action.romm_id) if action.romm_id else None
    if item is None:
        raise _Stale("RomM's copy is gone.")
    data = eng.romm.download_asset("saves", item)
    target = unit_target(u.folder, u.name) or {}
    if not u.bundle:
        dest = next(iter(u.members.values()), None) or target.get(u.name) or (u.root / u.name)
        _write(eng, dest, data, platform)
    else:
        if u.members:
            first_arc, first_path = next(iter(u.members.items()))
            base = Path(str(first_path)[: -len(first_arc)]) if str(first_path).endswith(first_arc) else u.root
        else:
            base = target.get("__dir__", u.root)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for arc in z.namelist():
                if arc.endswith("/") or arc.startswith("/") or ".." in Path(arc).parts:
                    continue
                _write(eng, base / arc, z.read(arc), platform)
    u2 = next((x for x in scan(u.folder) if x.name == u.name), None)
    h = u2.hash() if u2 else None
    STATE.set_baseline(u.key, h, item.get("updated_at"), item.get("id"), h if u.bundle else item.get("content_hash"))
    eng.romm.confirm_downloaded("saves", item["id"], None if u.bundle else h)
    return f"Downloaded {u.title or u.name} ({u.name}) from RomM"
# endregion


# region status and background
def status() -> List[dict]:
    out = []
    for f in folders():
        st = dict(_status.get(f["id"]) or {})
        out.append({**f, "label": KINDS[f["kind"]]["label"], **st})
    return out


_timer: dict = {"t": None}


def schedule(delay: float = 10.0) -> None:
    """Sync the emulator folders a little after a change in one of them (watch mode)."""
    def run():
        try:
            sync_all()
        except Exception as e:  # noqa: BLE001
            logger.error(f"Standalone emulators: sync failed: {e}")
    with _lock:
        if _timer["t"] is not None:
            _timer["t"].cancel()
        _timer["t"] = threading.Timer(delay, run)
        _timer["t"].daemon = True
        _timer["t"].start()


def watch(observer) -> None:
    """Watch the emulator folders with the save sync observer (watch mode)."""
    from watchdog.events import FileSystemEventHandler

    class _H(FileSystemEventHandler):
        def on_any_event(self, event):
            if not event.is_directory or event.event_type in ("created", "deleted", "moved"):
                schedule()

    for f in folders():
        if Path(f["path"]).is_dir():
            observer.schedule(_H(), f["path"], recursive=True)
            logger.info(f"Watching emulator folder: {f['path']} ({KINDS[f['kind']]['label']})")
# endregion
