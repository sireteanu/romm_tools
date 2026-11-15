"""Settings editable from the dashboard (GUI fork).

Stored in DATA_DIR/settings.json. A value saved here overrides the container environment; "reset"
removes the override. Connection settings (RomM URL/token, sync folders, sync mode) stay in the
container config because changing them needs a restart anyway.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict

from loguru import logger

from .sync_state import data_dir

_lock = threading.RLock()

# key -> spec. "attr" is the Config attribute the value is applied to.
FIELDS: Dict[str, dict] = {
    "DEVICE_SYNC": {"type": "choice", "choices": ["auto", "off"], "group": "romm",
                    "labels": {"auto": "Register as a device", "off": "Don't register"},
                    "label": "romm_tools as a RomM device (RomM 5.4+)",
                    "help": "RomM then knows which version this app last synced: it refuses to overwrite a copy that "
                            "changed meanwhile (you're asked instead) and lists romm_tools among your devices. "
                            "Applies at the next start."},
    "PUSH_NEW_MODE": {"type": "choice", "choices": ["auto", "confirm"], "group": "sync",
                      "label": "New files in your sync folder → RomM",
                      "help": "auto: upload right away. confirm: ask before uploading any new file."},
    "PULL_MODE": {"type": "choice", "choices": ["auto", "confirm", "off"], "group": "sync",
                  "label": "New or changed files on RomM → sync folder",
                  "help": "auto: download right away. confirm: ask first. off: never write to the sync folder."},
    "DELETE_MODE": {"type": "choice", "choices": ["auto", "ask", "off"], "group": "sync",
                    "labels": {"auto": "Recycle bin", "ask": "Ask first", "off": "Never"},
                    "label": "When a synced file is deleted on one side",
                    "help": "Recycle bin: remove it on the other side too, keeping a copy in the recycle bin. "
                            "Ask first: wait for your decision. Never: offer to bring it back instead."},
    "ROMM_POLL_INTERVAL_SECONDS": {"type": "int", "min": 0, "max": 86400, "unit": "seconds", "group": "timing",
                                   "label": "Check RomM for changes every", "mode": "watch",
                                   "help": "How often changes made on RomM (other devices) are picked up. "
                                           "0 = only when you press Sync now. Applies from the next check. "
                                           "This only asks RomM; your sync folders are read only when RomM has changes."},
    "FULL_SCAN_INTERVAL_HOURS": {"type": "int", "min": 0, "max": 720, "unit": "hours", "group": "timing",
                                 "label": "Re-read the sync folders anyway every", "mode": "watch",
                                 "help": "A safety net in case a file change was missed. Each one can wake "
                                         "the disks the folders live on. 0 = only at startup and when you press Sync now."},
    "WATCHDOG_DELAY_SECONDS": {"type": "int", "min": 0, "max": 3600, "unit": "seconds", "group": "timing",
                               "label": "Wait after a file changes", "mode": "watch",
                               "help": "Quiet time after Syncthing writes a file before syncing it. With the "
                                       "Syncthing integration on, the app also waits until Syncthing reports it's done, "
                                       "so this can be short (e.g. 5 s)."},
    "SYNC_INTERVAL_SECONDS": {"type": "int", "min": 60, "max": 604800, "unit": "seconds", "group": "timing",
                              "label": "Full sync every", "mode": "periodic",
                              "help": "Reads your sync folders and RomM and syncs everything."},
    "BACKUP_RETENTION_DAYS": {"type": "int", "min": 0, "max": 3650, "unit": "days", "group": "backups",
                              "label": "Keep backups of overwritten files for",
                              "help": "0 = keep forever. Backups are in /data/backups."},
    "RECYCLE_RETENTION_DAYS": {"type": "int", "min": 0, "max": 3650, "unit": "days", "group": "backups",
                               "label": "Empty the recycle bin after",
                               "help": "Deleted files are kept this long, then removed for good. 0 = keep forever."},
    "ROMM_KEEP_VERSIONS": {"type": "int", "min": 0, "max": 1000, "unit": "versions", "group": "backups",
                           "label": "Versions to keep on RomM for each file",
                           "help": "RomM keeps a copy every time a file is uploaded. After each sync, older copies beyond "
                                   "this number are moved to the recycle bin (the copy your folder is synced with is "
                                   "always kept). 0 = keep them all."},
    "FILE_MODE": {"type": "choice", "choices": [0o777, 0o666, 0o775, 0o664], "group": "backups",
                  "labels": {"511": "0777", "438": "0666", "509": "0775", "436": "0664"},
                  "label": "Permissions for files written to your sync folders",
                  "help": "0777 (default) = everyone can read and write, the usual choice on Unraid shares. "
                          "0666 = the same without the executable bit."},
    "DRY_RUN": {"type": "bool", "group": "sync", "label": "Dry run (test mode)",
                "help": "On: nothing is uploaded, downloaded or deleted. Each sync only logs what it would do "
                        "(Logs → Recent actions). Use it to check a new setting or platform mapping."},
    "SYNCTHING_URL": {"type": "str", "group": "syncthing", "label": "Syncthing address",
                      "help": "e.g. http://YOUR-SERVER:8384. Leave empty to turn the Syncthing integration off."},
    "SYNCTHING_API_KEY": {"type": "secret", "group": "syncthing", "label": "Syncthing API key",
                          "help": "Syncthing → Actions → Settings → General → API Key."},
    "SYNCTHING_FOLDERS": {"type": "str", "group": "syncthing", "label": "Syncthing folders with your saves",
                          "help": "Folder IDs, comma separated. Pick them below once the address and key are saved."},
    "WEB_USERNAME": {"type": "str", "group": "access", "label": "Dashboard username",
                     "help": "Set both username and password to require a login. Clear both to turn it off."},
    "WEB_PASSWORD": {"type": "secret", "group": "access", "label": "Dashboard password", "help": ""},
}

NOTIFY_DEFAULTS = {
    "channels": [],          # [{"type": "discord", "webhook_url": "..."}, ...]
    "events": {"questions": True, "errors": True, "activity": False, "problems": True},
    "dashboard_url": "",     # used for "open dashboard" links in messages
}

CHANNEL_FIELDS = {
    "discord": {"label": "Discord", "fields": [("webhook_url", "Webhook URL", True)]},
    "ntfy": {"label": "ntfy", "fields": [("server", "Server", False), ("topic", "Topic", False),
                                         ("token", "Access token (optional)", True)]},
    "gotify": {"label": "Gotify", "fields": [("server", "Server URL", False), ("app_token", "App token", True)]},
    "pushbullet": {"label": "Pushbullet", "fields": [("access_token", "Access token", True)]},
    "webhook": {"label": "Webhook (JSON POST)", "fields": [("url", "URL", True)]},
}


def _file():
    return data_dir() / "settings.json"


def load() -> dict:
    with _lock:
        try:
            raw = json.loads(_file().read_text())
        except FileNotFoundError:
            raw = {}
        except Exception as e:
            logger.warning(f"Ignoring unreadable settings file: {e}")
            raw = {}
        raw.setdefault("values", {})
        n = raw.setdefault("notifications", {})
        for k, v in NOTIFY_DEFAULTS.items():
            n.setdefault(k, json.loads(json.dumps(v)))
        for k, v in NOTIFY_DEFAULTS["events"].items():
            n["events"].setdefault(k, v)
        return raw


def save(data: dict):
    with _lock:
        tmp = _file().with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        try:
            os.chmod(tmp, 0o600)  # holds tokens
        except OSError:
            pass
        os.replace(tmp, _file())


# Values the container started with, so "reset" can go back to them.
_container_values: Dict[str, Any] = {}


def apply_to_config(cfg):
    """Called once at startup: remember container values, then apply saved overrides."""
    for key in FIELDS:
        _container_values.setdefault(key, getattr(cfg, key, None))
    for key, value in load()["values"].items():
        if key in FIELDS:
            setattr(cfg, key, value)
    logger.debug("Applied dashboard settings overrides")


def validate(key: str, value: Any):
    spec = FIELDS[key]
    if spec["type"] == "choice":
        if spec["choices"] and isinstance(spec["choices"][0], int):
            try:
                value = int(value)
            except (TypeError, ValueError):
                pass
        if value not in spec["choices"]:
            raise ValueError(f"{spec['label']}: must be one of {', '.join(map(str, spec['choices']))}")
        return value
    if spec["type"] == "bool":
        if isinstance(value, bool):
            return value
        if str(value).lower() in ("true", "1", "on", "yes"):
            return True
        if str(value).lower() in ("false", "0", "off", "no", ""):
            return False
        raise ValueError(f"{spec['label']}: must be on or off")
    if spec["type"] == "int":
        try:
            v = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{spec['label']}: must be a whole number")
        if not spec["min"] <= v <= spec["max"]:
            raise ValueError(f"{spec['label']}: must be between {spec['min']} and {spec['max']}")
        return v
    return "" if value is None else str(value)


def update(cfg, changes: Dict[str, Any], reset: list) -> None:
    """Validate everything first, then apply; nothing changes if any value is invalid."""
    data = load()
    vals = data["values"]
    clean = {k: validate(k, v) for k, v in changes.items() if k in FIELDS}
    prospective = {k: getattr(cfg, k, None) for k in FIELDS}
    for k in reset:
        if k in FIELDS:
            prospective[k] = _container_values.get(k)
    prospective.update(clean)
    if bool(prospective["WEB_USERNAME"]) != bool(prospective["WEB_PASSWORD"]):
        raise ValueError("Set both a dashboard username and password, or clear both.")
    for k in reset:
        if k in FIELDS:
            vals.pop(k, None)
    vals.update(clean)
    save(data)
    for k, v in prospective.items():
        setattr(cfg, k, v)


def describe(cfg) -> dict:
    """Settings for the UI. Secrets are never sent back, only whether they are set."""
    vals = load()["values"]
    out = []
    for key, spec in FIELDS.items():
        current = getattr(cfg, key, None)
        item = {"key": key, **spec,
                "source": "dashboard" if key in vals else ("container" if os.getenv(key) is not None else "default"),
                "container_value": None if spec["type"] == "secret" else _container_values.get(key)}
        if spec["type"] == "secret":
            item["is_set"] = bool(current)
            item["value"] = ""
        else:
            item["value"] = current
        out.append(item)
    return {"fields": out}


# region per-system sync switch
def disabled_folders() -> set:
    """Folders save sync leaves alone: switched off, or synced with RomM directly (RetroArch Cloud Sync, Grout)."""
    data = load()
    return {f.lower() for f in data.get("disabled_folders", []) + data.get("cloud_sync_folders", [])
            + data.get("grout_folders", [])}


def cloud_sync_folders() -> set:
    return {f.lower() for f in load().get("cloud_sync_folders", [])}


def grout_folders() -> set:
    return {f.lower() for f in load().get("grout_folders", [])}


def set_folder_mode(folder: str, mode: str) -> None:
    """mode: 'sync' (this app syncs it), 'off', 'cloud' (RetroArch Cloud Sync syncs it with RomM directly) or
    'grout' (Grout, RomM's handheld app, syncs it with RomM directly)."""
    if mode not in ("sync", "off", "cloud", "grout"):
        raise ValueError("mode must be sync, off, cloud or grout")
    data = load()
    for key, want in (("disabled_folders", mode == "off"), ("cloud_sync_folders", mode == "cloud"),
                      ("grout_folders", mode == "grout")):
        cur = [f for f in data.get(key, []) if f.lower() != folder.lower()]
        if want:
            cur.append(folder)
        data[key] = sorted(cur, key=str.lower)
    save(data)
    invalidate_cache()


def set_folder_enabled(folder: str, enabled: bool) -> None:
    data = load()
    cur = [f for f in data.get("disabled_folders", []) if f.lower() != folder.lower()]
    if not enabled:
        cur.append(folder)
    data["disabled_folders"] = sorted(cur, key=str.lower)
    save(data)


_disabled_cache = {"at": 0.0, "v": set()}


def sync_enabled(folder: str) -> bool:
    """False for system folders switched off on the Platforms page."""
    import time
    if time.monotonic() - _disabled_cache["at"] > 5:
        try:
            _disabled_cache["v"] = disabled_folders()
        except Exception:  # noqa: BLE001
            pass
        _disabled_cache["at"] = time.monotonic()
    return (folder or "").lower() not in _disabled_cache["v"]


def invalidate_cache():
    _disabled_cache["at"] = 0.0
    _emu_cache["at"] = 0.0


# Per system folder: which emulator writes these saves (Platforms page), and whether RetroArch Cloud Sync handles
# the folder instead of this app. Stored in settings.json as "folder_emulators" / "cloud_sync_folders".
_emu_cache = {"at": 0.0, "v": {}}


def folder_emulators() -> dict:
    return {k.lower(): v for k, v in (load().get("folder_emulators") or {}).items() if v}


def set_folder_emulator(folder: str, emulator: str | None) -> None:
    data = load()
    cur = {k: v for k, v in (data.get("folder_emulators") or {}).items() if k.lower() != folder.lower()}
    if emulator:
        cur[folder] = emulator.strip()
    data["folder_emulators"] = cur
    save(data)
    invalidate_cache()


SAVE_STYLES = ("auto", "retroarch", "minui", "generic", "keep")


def folder_save_names() -> dict:
    return {k.lower(): v for k, v in (load().get("folder_save_names") or {}).items() if v and v != "auto"}


def set_folder_save_names(folder: str, style: str | None) -> None:
    """How saves downloaded into a system folder are named: auto (from the files already there), retroarch
    (Game.srm), minui (Game.gba.sav, MinUI/NextUI), generic (Game.sav) or keep (RomM's name)."""
    style = style or "auto"
    if style not in SAVE_STYLES:
        raise ValueError("save names must be one of " + ", ".join(SAVE_STYLES))
    data = load()
    cur = {k: v for k, v in (data.get("folder_save_names") or {}).items() if k.lower() != folder.lower()}
    if style != "auto":
        cur[folder] = style
    data["folder_save_names"] = cur
    save(data)
    invalidate_cache()


def emulator_for(folder: str):
    """The emulator set for a system folder on the Platforms page (sent to RomM with uploads), or None."""
    import time
    if time.monotonic() - _emu_cache["at"] > 5:
        try:
            _emu_cache["v"] = folder_emulators()
        except Exception:  # noqa: BLE001
            pass
        _emu_cache["at"] = time.monotonic()
    return _emu_cache["v"].get((folder or "").lower())
# endregion


# region notifications
def notify_public() -> dict:
    """Notification settings for the UI, with secrets masked."""
    n = load()["notifications"]
    chans = []
    for ch in n["channels"]:
        spec = CHANNEL_FIELDS.get(ch.get("type"), {"fields": []})
        c = {"type": ch.get("type")}
        for name, _, secret in spec["fields"]:
            if secret:
                c[name] = ""
                c[name + "_set"] = bool(ch.get(name))
            else:
                c[name] = ch.get(name, "")
        chans.append(c)
    return {"channels": chans, "events": n["events"], "dashboard_url": n.get("dashboard_url", ""),
            "channel_types": {k: {"label": v["label"], "fields": [{"name": f, "label": lbl, "secret": sec}
                                                                  for f, lbl, sec in v["fields"]]}
                              for k, v in CHANNEL_FIELDS.items()}}


def notify_update(body: dict) -> None:
    data = load()
    n = data["notifications"]
    old = n["channels"]
    new_channels = []
    for i, ch in enumerate(body.get("channels", [])):
        t = ch.get("type")
        if t not in CHANNEL_FIELDS:
            raise ValueError(f"Unknown notification type: {t}")
        prev = old[i] if i < len(old) and old[i].get("type") == t else {}
        c = {"type": t}
        for name, label, secret in CHANNEL_FIELDS[t]["fields"]:
            v = (ch.get(name) or "").strip()
            if secret and not v:
                v = prev.get(name, "")  # blank secret = keep the saved one
            c[name] = v
        if t == "ntfy":
            c["server"] = c.get("server") or "https://ntfy.sh"
            if not c.get("topic"):
                raise ValueError("ntfy needs a topic")
        required = {"discord": "webhook_url", "gotify": "app_token", "pushbullet": "access_token", "webhook": "url"}
        if t in required and not c.get(required[t]):
            raise ValueError(f"{CHANNEL_FIELDS[t]['label']}: {dict((f, lbl) for f, lbl, _ in CHANNEL_FIELDS[t]['fields'])[required[t]]} is required")
        if t == "gotify" and not c.get("server"):
            raise ValueError("Gotify needs a server URL")
        new_channels.append(c)
    n["channels"] = new_channels
    ev = body.get("events", {})
    n["events"] = {k: bool(ev.get(k, n["events"].get(k))) for k in NOTIFY_DEFAULTS["events"]}
    n["dashboard_url"] = (body.get("dashboard_url") or "").strip()
    save(data)


def notify_config() -> dict:
    return load()["notifications"]
# endregion
