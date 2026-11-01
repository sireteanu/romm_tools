"""Game names: compare the names in your frontends' gamelist.xml files with the names in RomM.

A gamelist.xml (EmulationStation, ES-DE, Batocera, RetroBat, Knulli) has one <game> (or <folder>)
per ROM: <path> is the ROM relative to the system's ROM folder ("./Some Game (USA).zip",
"./Hacks/Other.zip") and <name> is the name the frontend shows. RomM keeps its own name per ROM
(`name`), next to the file name (`fs_name`) and the folder (`fs_path`, "roms/snes/Hacks").

Where the gamelists are read (`platform_folders`, then `find_gamelists` in each folder):
- every platform folder from the RomM library page (the folder mounted as roms/<slug> - the same
  file RomM's own "gamelist" metadata source reads), and
- every subfolder named after a RomM platform (fs_slug or slug) in the extra gamelist folders set on
  the Game names page (a RomM library folder's roms/, a frontend's roms folder, ES-DE's gamelists/).
Not every folder has one. Subfolders are searched too (a few levels down): a gamelist in
<platform>/Hacks/ lists its games relative to Hacks/, so they become "Hacks/<path>". Media folders,
the "never read" names of the RomM library page and folders that are another platform are skipped.

Matching follows RomM's gamelist handler (backend/handler/metadata/gamelist_handler.py, Oct 2026):
the path inside the platform folder first, else the bare file name when only one entry has it.

Nothing here writes to RomM; the server sends only `name` with PUT /api/roms/{id} (RomM keeps every
other field and derives the sort name again, and keeps a name it was given on later scans).
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Optional

GAMELIST = "gamelist.xml"
MAX_GAMELIST_BYTES = 64 * 1024 * 1024    # a gamelist this big isn't one
MAX_NAME = 350                           # RomM's roms.name column
MAX_DEPTH = 4                            # subfolder levels searched for more gamelists
# folders frontends keep media in - never searched for gamelists
MEDIA_DIRS = {"media", "images", "videos", "manuals", "marquees", "screenshots", "covers", "titlescreens",
              "miximages", "3dboxes", "backcovers", "fanart", "physicalmedia", "wheels", "thumbnails"}


def clean_path(raw: str) -> str:
    """A gamelist <path> as a path inside the system's ROM folder: "./a/b.zip" -> "a/b.zip"."""
    p = (raw or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.strip("/")


def read_gamelist(path: str) -> dict:
    """{path inside the ROM folder: name} for every <game> and <folder> with both. Raises ValueError
    with a readable reason when the file can't be read."""
    try:
        if os.path.getsize(path) > MAX_GAMELIST_BYTES:
            raise ValueError("too big to be a gamelist")
        tree = ET.parse(path)
    except ET.ParseError as e:
        raise ValueError(f"not valid XML ({e})") from e
    except OSError as e:
        raise ValueError(e.strerror or str(e)) from e
    out = {}
    for el in tree.getroot().iter():
        if el.tag not in ("game", "folder"):
            continue
        rel = clean_path(el.findtext("path") or "")
        name = " ".join((el.findtext("name") or "").split())
        if rel and name and rel not in out:
            out[rel] = name
    return out


def find_gamelists(folder: str, skip=(), stop=(), max_depth: int = MAX_DEPTH) -> list:
    """Every gamelist.xml in a platform folder and its subfolders -> [(file, prefix)], prefix being
    the subfolder's path inside the platform folder ("" for the folder itself). skip: folder names
    (wildcards, any case) never searched; stop: real paths of folders that are another platform."""
    import fnmatch
    pats = [p.casefold() for p in skip]
    out = []

    def walk(d, prefix, level):
        try:
            entries = list(os.scandir(d))
        except OSError:
            return
        for e in entries:
            if e.name == GAMELIST and e.is_file():
                out.append((e.path, prefix))
        if level >= max_depth:
            return
        for e in sorted(entries, key=lambda x: x.name.casefold()):
            n = e.name.casefold()
            if n.startswith(".") or n in MEDIA_DIRS or n.startswith("downloaded_") or \
                    any(fnmatch.fnmatchcase(n, p) for p in pats):
                continue
            try:
                # links below the platform folder aren't followed (no loops); the folder itself may be one
                if not e.is_dir(follow_symlinks=False) or os.path.realpath(e.path) in stop:
                    continue
            except OSError:
                continue
            walk(e.path, f"{prefix}/{e.name}" if prefix else e.name, level + 1)

    walk(folder, "", 0)
    return out


def collect(folders: dict, skip=()) -> dict:
    """platform_folders() -> {platform id: [(gamelist file, prefix)]}, [] for a platform without one."""
    real = {os.path.realpath(d) for dirs in folders.values() for d in dirs}
    found = {}
    for pid, dirs in folders.items():
        files = []
        for d in dirs:
            stop = real - {os.path.realpath(d)}
            for f, prefix in find_gamelists(d, skip, stop):
                if f not in (x[0] for x in files):
                    files.append((f, prefix))
        found[pid] = files
    return found


def platform_folders(mapped: list, extra: list, platforms: list) -> dict:
    """-> {RomM platform id: [folders that may hold its gamelist.xml]}.

    mapped: [(slug, folder)] from the RomM library page. extra: folders whose subfolders are named
    after RomM platforms. platforms: RomM's /api/platforms."""
    by_name = {}
    for p in platforms:
        for key in (p.get("fs_slug"), p.get("slug")):
            if key:
                by_name.setdefault(key.casefold(), p["id"])
    out: dict = {}

    def add(name, folder):
        pid = by_name.get((name or "").casefold())
        if pid is not None and folder not in out.setdefault(pid, []):
            out[pid].append(folder)

    for slug, folder in mapped:
        add(slug, folder)
    for base in extra:
        try:
            names = sorted(e.name for e in os.scandir(base) if e.is_dir())
        except OSError:
            continue
        for n in names:
            add(n, os.path.join(base, n))
    return out


def rom_rel_path(rom: dict, fs_slug: str) -> str:
    """The ROM's path inside its platform folder, from RomM's fs_path ("roms/snes/Hacks") and
    fs_name: "Hacks/<fs_name>". Also handles the roms-inside-platform layout ("snes/roms")."""
    parts = [p for p in (rom.get("fs_path") or "").replace("\\", "/").split("/") if p]
    sub: list = []
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].casefold() == (fs_slug or "").casefold():
            sub = parts[i + 1:]
            break
    if sub and sub[0] == "roms":
        sub = sub[1:]
    return "/".join(sub + [rom.get("fs_name") or ""])


class Index:
    """One platform's gamelist entries, looked up like RomM does."""

    def __init__(self):
        self.by_path: dict = {}      # path inside the ROM folder -> (name, gamelist file)
        self.by_file: dict = {}      # bare file name -> (name, gamelist file)
        self.ambiguous: set = set()  # file names more than one entry has
        self.used: set = set()       # paths a RomM ROM matched

    def add(self, entries: dict, source: str, prefix: str = ""):
        for rel, name in entries.items():
            rel = f"{prefix}/{rel}" if prefix else rel
            if rel in self.by_path:      # the first gamelist read for a platform wins
                continue
            self.by_path[rel] = (name, source)
            base = rel.rsplit("/", 1)[-1]
            if base in self.by_file:
                self.ambiguous.add(base)
            else:
                self.by_file[base] = (name, source, rel)

    def find(self, rel: str) -> Optional[tuple]:
        """-> (name, gamelist file) or None."""
        hit = self.by_path.get(rel)
        if hit:
            self.used.add(rel)
            return hit
        base = rel.rsplit("/", 1)[-1]
        if base in self.ambiguous or base not in self.by_file:
            return None
        name, source, path = self.by_file[base]
        self.used.add(path)
        return name, source


def compare(platforms: list, found: dict, roms: list, ignored: dict) -> dict:
    """Every RomM ROM whose name differs from its gamelist entry.

    found: collect() - the gamelists per platform, the platform folder's own first. roms: RomM ROMs (id, name, fs_name, fs_path, platform_id).
    ignored: {str(rom id): gamelist name} the user chose to keep RomM's name for - shown again
    once the gamelist name changes. -> {rows, gamelists, summary}."""
    plat = {p["id"]: p for p in platforms}
    indexes: dict = {}
    gamelists = []
    missing = []
    for pid, files in found.items():
        idx = Index()
        if not files:
            missing.append(pid)
        for f, prefix in files:
            try:
                entries = read_gamelist(f)
            except ValueError as e:
                gamelists.append({"platform_id": pid, "file": f, "games": 0, "error": str(e)})
                continue
            idx.add(entries, f, prefix)
            gamelists.append({"platform_id": pid, "file": f, "games": len(entries), "error": None})
        if idx.by_path:
            indexes[pid] = idx

    rows, same, unmatched, hidden = [], 0, 0, 0
    for rom in roms:
        idx = indexes.get(rom.get("platform_id"))
        if idx is None:
            continue
        p = plat.get(rom["platform_id"]) or {}
        rel = rom_rel_path(rom, p.get("fs_slug") or p.get("slug") or "")
        hit = idx.find(rel)
        if not hit:
            unmatched += 1
            continue
        g_name, source = hit
        r_name = rom.get("name") or ""
        if g_name == r_name:
            same += 1
            continue
        is_ignored = ignored.get(str(rom["id"])) == g_name
        hidden += is_ignored
        rows.append({"id": rom["id"], "platform_id": rom["platform_id"],
                     "platform": p.get("display_name") or p.get("custom_name") or p.get("name") or p.get("slug", ""),
                     "file": rel, "romm_name": r_name, "gamelist_name": g_name, "gamelist": source,
                     "ignored": is_ignored, "case_only": g_name.casefold() == r_name.casefold()})
    rows.sort(key=lambda r: (r["platform"].casefold(), r["file"].casefold()))
    for g in gamelists:
        g["platform"] = (plat.get(g["platform_id"]) or {}).get("display_name") or \
            (plat.get(g["platform_id"]) or {}).get("name") or ""
    not_in_romm = sum(len(i.by_path) - len(i.used) for i in indexes.values())
    def pname(pid):
        p = plat.get(pid) or {}
        return p.get("display_name") or p.get("name") or p.get("slug") or str(pid)

    return {"rows": rows, "gamelists": gamelists, "no_gamelist": sorted((pname(pid) for pid in missing), key=str.casefold),
            "summary": {"gamelists": sum(1 for g in gamelists if not g["error"]),
                        "platforms": len(indexes), "different": len(rows) - hidden, "ignored": hidden,
                        "same": same, "romm_not_in_gamelist": unmatched, "gamelist_not_in_romm": not_in_romm}}


def check_name(name) -> str:
    """A name to give a ROM in RomM, tidied; ValueError when it can't be one."""
    if not isinstance(name, str):
        raise ValueError("the name must be text")
    n = " ".join(name.split())
    if not n:
        raise ValueError("the name is empty")
    if len(n) > MAX_NAME:
        raise ValueError(f"the name is longer than {MAX_NAME} characters")
    return n
