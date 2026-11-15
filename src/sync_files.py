"""Local files, fingerprints, dates and names for save sync (from the romm_syncthing_sync GUI fork; original
project by amn-96, MIT). No RomM calls in here."""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from loguru import logger

from .sync_state import data_dir

CONFLICT_MARKER = "(conflict "
_VERSION_TAG = re.compile(r"\s*\[\d{4}-\d{2}-\d{2}[^\]]*\]")  # RomM 5.x slot version tag

KIND_API = {"save": "saves", "state": "states"}


# region helpers
def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_hash_cache: Dict[str, Tuple[float, int, str]] = {}
_hash_cache_loaded = False
_hash_cache_dirty = False


def _hash_cache_file() -> Path:
    return data_dir() / "hash_cache.json"


def _load_hash_cache():
    global _hash_cache_loaded
    if _hash_cache_loaded:
        return
    _hash_cache_loaded = True
    try:
        import json
        raw = json.loads(_hash_cache_file().read_text())
        _hash_cache.update({k: tuple(v) for k, v in raw.items()})
        logger.debug(f"Loaded {len(_hash_cache)} cached file fingerprints")
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug(f"Ignoring unreadable hash cache: {e}")


def save_hash_cache(prune: bool = False):
    """Persist fingerprints so a restart doesn't re-read every save. prune (full syncs only, which read the
    folders anyway) drops files that no longer exist; small syncs skip it so they don't touch every file."""
    global _hash_cache_dirty
    if not _hash_cache_dirty:
        return
    import json
    if prune:
        for k in [k for k in _hash_cache if not os.path.exists(k)]:
            del _hash_cache[k]
    tmp = _hash_cache_file().with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(_hash_cache))
        os.replace(tmp, _hash_cache_file())
        _hash_cache_dirty = False
    except OSError as e:
        logger.debug(f"Couldn't save hash cache: {e}")


def cached_md5(path: Path) -> str:
    global _hash_cache_dirty
    _load_hash_cache()
    st = path.stat()
    c = _hash_cache.get(str(path))
    if c and c[0] == st.st_mtime and c[1] == st.st_size:
        return c[2]
    h = md5_file(path)
    _hash_cache[str(path)] = (st.st_mtime, st.st_size, h)
    _hash_cache_dirty = True
    return h


def parse_dt(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def same_time(a, b) -> bool:
    da, db = parse_dt(a), parse_dt(b)
    if da is None or db is None:
        return da is db
    return abs((da - db).total_seconds()) < 1


def local_name_for_remote(item: dict, rom_row: Optional[dict] = None) -> str:
    """Name a RomM save/state should have in the sync folder.

    RetroArch only loads saves/states named after the ROM file, but RomM 5.x's own players and other
    devices store them under other names: a version tag ("Game [2026-08-17_19-02-17].srm"), a slot name
    ("Game.autosave.state0"), or no game name at all ("autosave.srm"). Strip the tag, and if what's left
    doesn't name this ROM, rename it to the ROM's file name + the save/state extension:
        "autosave [2026-08-17_19-02-17].srm"                 -> "Mario's Picross (USA, Europe).srm"
        "Mario's Picross (USA, Europe).autosave.state0"      -> "Mario's Picross (USA, Europe).state0"
        "Panzer Dragoon Saga (USA).bcr" (ROM "... (Disc 1)")  -> unchanged (multi-disc .m3u name)
    """
    name = _VERSION_TAG.sub("", item["file_name"])
    if not rom_row:
        return name
    from .library_classes import LibraryScanner
    game_name, ftype = LibraryScanner.parse_save_filename(name)
    local_stem = rom_row.get("_local_stem")  # matched by title or linked by hand: the local game's own name
    if not game_name or not ftype or game_name == local_stem or \
            (not local_stem and LibraryScanner.find_rom(game_name, [rom_row]) is not None):
        return name
    rom_stem = local_stem or rom_row.get("fs_name_no_ext") or os.path.splitext(rom_row.get("fs_name") or "")[0]
    if not rom_stem:
        return name
    suffix = name[len(game_name):]  # ".srm", ".state0", ".state.auto", ".autosave.state0" ...
    if ftype in ("state", "state_screen"):
        m = re.search(r"\.state(?:\d+|\.auto)?(?:\.png)?$", suffix)
        suffix = m.group(0) if m else suffix
        suffix = re.sub(r"^\.state0(?=$|\.png$)", ".state", suffix)  # RetroArch's slot 0 is ".state"
    else:
        suffix = os.path.splitext(name)[1]
    return rom_stem + suffix


def file_key(file_type: str, rom_id: int, name: str) -> str:
    return f"{file_type}:{rom_id}:{name}"


@dataclass
class LocalFile:
    file_type: str
    path: Path
    hash: str
    size: int
    mtime: datetime
    screenshot: Optional[Path] = None
