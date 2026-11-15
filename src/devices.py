"""This app as a RomM device (RomM 5.4+).

Two things live here:
- **Device registration.** Save sync registers romm_tools as a device ("romm_tools on <host>") and sends its id
  with uploads, downloads and RomM's download receipts. RomM then knows which version this app last synced, refuses
  an upload over a copy that changed since (409, turned into a conflict for you to choose), and shows romm_tools in
  its own device list. Older RomM versions, or a token without devices.write, simply sync without a device.
- **Pairing.** Instead of pasting an API token, start a pairing on the Settings page and approve the code in RomM.
  RomM issues a token bound to this device; it's kept in DATA_DIR/romm_device.json (readable by this app only).

DEVICE_SYNC (Settings page / env): auto (default) | off.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid
from typing import Optional

from loguru import logger

from .sync_state import data_dir, utcnow_iso

_lock = threading.Lock()
_pairing: dict = {"status": "idle"}   # idle | waiting | paired | failed


def _file():
    return data_dir() / "romm_device.json"


def load() -> dict:
    try:
        return json.loads(_file().read_text())
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"romm_device.json unreadable ({e}); ignoring it.")
        return {}


def _save(data: dict) -> None:
    f = _file()
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    try:
        os.chmod(tmp, 0o600)   # holds a RomM token
    except OSError:
        pass
    os.replace(tmp, f)


def identifier() -> str:
    """A stable id for this installation (kept in romm_device.json)."""
    with _lock:
        data = load()
        if not data.get("identifier"):
            data["identifier"] = f"romm_tools-{uuid.uuid4().hex[:12]}"
            _save(data)
        return data["identifier"]


def device_name() -> str:
    return f"romm_tools on {socket.gethostname()}"


def apply_saved(client) -> None:
    """At startup: use the paired token (if any) instead of the configured login."""
    data = load()
    if data.get("token") and data.get("url") in (None, "", client.url):
        client.use_token(data["token"])
        client.device_id = data.get("device_id")


def has_paired_token() -> bool:
    return bool(load().get("token"))


def register(client, version: str, mode: str = "auto") -> Optional[str]:
    """Register this app as a RomM device (or find it again) and remember the id on the client. Never raises."""
    if (mode or "auto") == "off" or not getattr(client, "url", None):
        client.device_id = None
        return None
    if client.device_id:          # paired: the token is already bound to a device
        return client.device_id
    if not client.at_least("5.4.0"):
        return None
    try:
        device_id = client.register_device(device_name(), version)
    except Exception as e:  # noqa: BLE001
        logger.info(f"Couldn't register with RomM as a device ({e}); syncing without one.")
        return None
    client.device_id = device_id
    if device_id:
        with _lock:
            data = load()
            data.update(device_id=device_id, registered_at=utcnow_iso(), url=client.url)
            _save(data)
        logger.info(f"Registered with RomM as device '{device_name()}'.")
    return device_id


# region pairing
def pairing_status() -> dict:
    out = {k: v for k, v in _pairing.items() if k != "device_code"}
    out["paired"] = has_paired_token()
    return out


def start_pairing(client, version: str) -> dict:
    """Start RomM's device login and poll for the approval in the background."""
    if _pairing.get("status") == "waiting":
        return pairing_status()
    res = client.pair_start(identifier(), device_name(), version)
    link = client.absolute(res.get("verification_path_complete") or res.get("verification_path") or "/pair/device")
    _pairing.clear()
    _pairing.update(status="waiting", user_code=res["user_code"], link=link, device_code=res["device_code"],
                    expires_at=time.time() + int(res.get("expires_in", 600)), started_at=utcnow_iso())
    interval = max(int(res.get("interval", 5)), 2)
    threading.Thread(target=_poll, args=(client, interval), name="romm-pairing", daemon=True).start()
    return pairing_status()


def _poll(client, interval: int) -> None:
    code = _pairing.get("device_code")
    while _pairing.get("status") == "waiting" and _pairing.get("device_code") == code:
        if time.time() > _pairing.get("expires_at", 0):
            _pairing.update(status="failed", error="The code expired before it was approved. Start again.")
            return
        time.sleep(interval)
        try:
            got = client.pair_poll(code)
        except Exception as e:  # noqa: BLE001
            _pairing.update(status="failed", error=str(e))
            return
        if got:
            with _lock:
                data = load()
                data.update(token=got["access_token"], device_id=got.get("device_id"), url=client.url,
                            scopes=got.get("scopes"), paired_at=utcnow_iso())
                _save(data)
            client.use_token(got["access_token"])
            client.device_id = got.get("device_id")
            _pairing.update(status="paired", paired_at=utcnow_iso())
            logger.info("Paired with RomM: romm_tools now uses the token RomM issued for this device.")
            return


def cancel_pairing() -> dict:
    _pairing.clear()
    _pairing.update(status="idle")
    return pairing_status()


def forget(client, env_login) -> dict:
    """Drop the paired token and go back to the login from the container settings."""
    with _lock:
        data = load()
        for k in ("token", "scopes", "paired_at", "device_id", "registered_at"):
            data.pop(k, None)
        _save(data)
    auth_type, token = env_login
    client.auth_type, client.api_token = auth_type, token
    client.device_id = None
    _pairing.clear()
    _pairing.update(status="idle")
    return pairing_status()
# endregion
