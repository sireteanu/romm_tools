"""The one RomM API client used by both parts of romm_tools (save sync and ROM folders).

Every request goes through RommClient._request: one requests.Session, timeouts on every call, and
plain-language errors (RommUnreachable, RommAuthError, RommConflict, RuntimeError with RomM's answer).

What it covers (RomM 4.5+; newer endpoints are used only when the server has them):
- library: /api/roms (paged, per platform), /api/platforms, /api/platforms/supported, renaming a ROM
- saves/states: list, download, upload/replace (with device_id + content_hash on RomM 5.4+, which makes
  RomM refuse a stale upload with 409), delete, "downloaded" receipts
- devices (RomM 5.4+): register this app as a device, list devices, pair by code (no API token needed)
- memory cards (RomM 5.4+): whole-card images for emulators with one card shared by many games
- gamelist.xml export (RomM 4.x+)
"""
from __future__ import annotations

import io
import os
import socket
import threading
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth
from loguru import logger

CLIENT_NAME = "romm_tools"
# Scopes romm_tools asks for when it is paired with RomM (device login).
PAIR_SCOPES = ["me.read", "roms.read", "roms.write", "platforms.read", "platforms.write", "assets.read",
               "assets.write", "devices.read", "devices.write"]


class RommUnreachable(RuntimeError):
    """RomM could not be contacted (wrong URL, network, firewall, RomM down)."""


class RommAuthError(RuntimeError):
    """RomM refused the login or the token lacks a permission."""


class RommConflict(RuntimeError):
    """RomM refused an upload because its copy changed since this app last synced it (409)."""

    def __init__(self, message: str, detail=None):
        super().__init__(message)
        self.detail = detail


def _version_tuple(v: Optional[str]) -> tuple:
    out = []
    for part in (v or "").lstrip("v").split("-")[0].split("."):
        try:
            out.append(int(part))
        except ValueError:
            break
    return tuple(out)


class RommClient:
    """Address, login and API calls for one RomM user."""

    def __init__(self,
                 romm_url: str = os.getenv("ROMM_URL", ""),
                 romm_username: str = os.getenv("ROMM_USERNAME", ""),
                 romm_password: str = os.getenv("ROMM_PASSWORD", ""),
                 romm_base_dir: Path = Path(os.getenv("ROMM_BASE_DIR", "")),
                 romm_container_name: str = os.getenv("ROMM_CONTAINER_NAME", "rommapp"),
                 api_limit: int = int(os.getenv("ROMM_API_LIMIT", "500")),
                 auth_type: str = os.getenv("ROMM_AUTH_TYPE", "http"),
                 romm_api_token: str = os.getenv("ROMM_API_TOKEN", "")):
        self.url = romm_url.rstrip("/") if romm_url else romm_url
        self.user = romm_username
        self.password = romm_password
        self.romm_base_dir = romm_base_dir
        self.romm_container_name = romm_container_name
        self.api_limit = api_limit
        self.auth_type = auth_type.split("#")[0].strip().lower()  # tolerate "api  # comment" from .env files
        self.api_token = romm_api_token
        # Set when this app is registered as a RomM device (src/devices.py); sent with uploads/downloads.
        self.device_id: Optional[str] = None
        self._version: Optional[str] = None
        self._session = requests.Session()
        # {(kind, id): updated_at} of saves/states this app created or replaced itself (None = deleted). The quiet
        # RomM check uses it so our own uploads don't look like "something changed on RomM". The timestamp makes
        # sure a later change by another device to the same file still counts.
        self.own_changes: dict = {}
        self._own_lock = threading.Lock()

    # region plumbing
    def use_token(self, token: str) -> None:
        """Switch to a bearer token (e.g. the one RomM issued when this app was paired)."""
        self.auth_type, self.api_token = "api", token

    def _auth_kwargs(self) -> dict:
        if self.auth_type == "api":
            return {"headers": {"Authorization": f"Bearer {self.api_token}"}}
        return {"auth": HTTPBasicAuth(self.user, self.password)}

    def absolute(self, path: str) -> str:
        """Turn a RomM-relative path (/assets/..., /api/raw/...) into a full URL."""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{(self.url or '').rstrip('/')}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, *, timeout=60, auth: bool = True, ok=(), **kw) -> requests.Response:
        """One RomM request. Raises RommUnreachable / RommAuthError / RommConflict / RuntimeError for errors,
        except status codes listed in `ok`, which are returned to the caller."""
        url = self.absolute(path)
        if auth:
            for k, v in self._auth_kwargs().items():
                if k == "headers":
                    kw["headers"] = {**v, **kw.get("headers", {})}
                else:
                    kw.setdefault(k, v)
        try:
            response = self._session.request(method, url, timeout=timeout, **kw)
        except requests.exceptions.RequestException as e:
            raise RommUnreachable(f"Can't reach RomM at {self.url} ({type(e).__name__}). "
                                  "Check ROMM_URL is reachable from inside this container.") from e
        logger.debug(f"{method} {url} - {response.status_code}")
        if response.status_code in ok or response.status_code < 400:
            return response
        if response.status_code in (401, 403):
            raise RommAuthError(f"RomM refused the request ({response.status_code}). Check the login or API "
                                f"token and its permissions. RomM said: {response.text[:200]}")
        if response.status_code == 409:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = response.text[:300]
            raise RommConflict(f"RomM returned 409: {detail}", detail)
        raise RuntimeError(f"RomM returned {response.status_code}: {response.text[:300]}")

    def _json(self, method: str, path: str, **kw):
        return self._request(method, path, **kw).json()
    # endregion

    # region server
    def heartbeat(self) -> Dict:
        return self._json("GET", "/api/heartbeat", timeout=10, auth=False)

    def version(self, refresh: bool = False) -> Optional[str]:
        """RomM server version from the heartbeat, e.g. '5.4.1' (cached)."""
        if self._version is None or refresh:
            try:
                hb = self.heartbeat()
                self._version = (hb.get("SYSTEM") or {}).get("VERSION") or hb.get("VERSION")
            except Exception:  # noqa: BLE001
                return None
        return self._version

    def at_least(self, version: str) -> bool:
        """True when the server is this version or newer (unknown/dev versions count as new)."""
        v = self.version()
        if not v or not _version_tuple(v):
            return True
        return _version_tuple(v) >= _version_tuple(version)

    def get_raw(self, path_or_url: str, timeout: int = 20) -> requests.Response:
        """Authenticated GET of any RomM asset (covers, screenshots, platform icons) for the image proxies."""
        return self._session.get(self.absolute(path_or_url), timeout=timeout, **self._auth_kwargs())
    # endregion

    # region library
    def list_platforms(self) -> List[Dict]:
        """Platforms in this RomM library (slug, fs_slug, name, rom_count...)."""
        return self._json("GET", "/api/platforms", timeout=30)

    def supported_platforms(self) -> List[Dict]:
        """Every platform this RomM version knows (slug, name, ...). Empty on servers without the endpoint."""
        r = self._request("GET", "/api/platforms/supported", timeout=30, ok=(404, 405, 422))
        return r.json() if r.status_code < 400 else []

    def rename_rom(self, rom_id: int, name: str) -> Dict:
        """Give a ROM a new name in RomM (Game names page). Only `name` is sent, as a form field:
        RomM keeps every other field, derives the sort name again, and keeps this name on later
        scans. The file on disk is not touched (that would be fs_name). -> the updated ROM."""
        r = self._request("PUT", f"/api/roms/{int(rom_id)}", files={"name": (None, name)}, ok=(401, 403, 404))
        if r.status_code in (401, 403):
            raise RommAuthError("RomM refused the change - the user or API token needs write access to roms "
                                "(roms.write)")
        if r.status_code == 404:
            raise RuntimeError("RomM doesn't have this game any more")
        return r.json()

    def export_gamelists(self, platform_ids: List[int], local_paths: bool = True) -> None:
        """Ask RomM to write gamelist.xml files into these platforms' folders (merged into existing ones on
        RomM 5.x)."""
        params = [("platform_ids", int(p)) for p in platform_ids] + [("local_export", str(local_paths).lower())]
        self._request("POST", "/api/export/gamelist-xml", params=params, timeout=600)

    def _validate_library_response(self, response) -> dict:
        try:
            data = response.json()
        except ValueError as e:
            raise RuntimeError(f"Invalid JSON from ROMM API: {e}")
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise RuntimeError("ROMM API response missing 'items' list")
        return data

    def _get_rom_page(self, params: dict):
        try:
            response = self._request("GET", "/api/roms", params=params, timeout=(10, 180), ok=(400, 404, 422))
        except RommAuthError as e:
            raise RuntimeError("RomM rejected the credentials. Check ROMM_AUTH_TYPE / ROMM_API_TOKEN (needs roms "
                               "+ platforms read access).") from e
        if response.status_code in (400, 404, 422):
            logger.critical(f"RomM returned {response.status_code}: {response.text[:500]}")
            raise RuntimeError(f"ROMM API returned {response.status_code}")
        return self._validate_library_response(response)

    def _fetch_roms(self, extra: dict, label: str, trim, on_progress) -> list:
        """Page through /api/roms. Pages are trimmed as they arrive to keep memory low."""
        items, offset, total = [], 0, None
        limit = self.api_limit
        while True:
            params = {
                "limit": limit, "offset": offset,
                # Ask RomM not to compute the gallery extras on every page (RomM 5.x; ignored by older versions).
                "with_char_index": "false", "with_filter_values": "false", "with_rom_id_index": "false",
                **extra,
            }
            if offset:
                params["with_total"] = "false"
            data = self._get_rom_page(params)
            if total is None and isinstance(data.get("total"), int):
                total = data["total"]
            page = data.get("items") or []
            items.extend(trim(page) if trim else page)
            if on_progress:
                on_progress(label, len(items), total)
            if len(page) < limit:
                break
            offset += limit
        return items

    def get_full_library(self, platform_ids: list | None = None, trim=None, on_progress=None) -> dict:
        """The ROMs in RomM, page by page. platform_ids: [(id, label)] to read only those platforms;
        trim: applied to each page; on_progress: callback(label, fetched, total)."""
        if not platform_ids:
            return {"items": self._fetch_roms({}, "all platforms", trim, on_progress)}
        all_items = []
        for pid, label in platform_ids:
            # 4.x takes platform_id, 5.x platform_ids; send both, then verify RomM really filtered.
            page_items = self._fetch_roms({"platform_id": pid, "platform_ids": pid}, label, trim, on_progress)
            if any(i.get("platform_id") not in (pid, None) for i in page_items):
                logger.warning("RomM ignored the platform filter; reading the whole library instead.")
                return {"items": self._fetch_roms({}, "all platforms", trim, on_progress)}
            all_items.extend(page_items)
        return {"items": all_items}
    # endregion

    # region saves and states
    def list_all(self, kind: str) -> List[Dict]:
        """All saves or states owned by this user, in ONE request. kind: 'saves' or 'states'."""
        data = self._json("GET", f"/api/{kind}", timeout=60)
        if isinstance(data, dict) and "items" in data:  # tolerate a paginated shape
            data = data["items"]
        return data if isinstance(data, list) else []

    def get_asset(self, kind: str, romm_id: int) -> Optional[Dict]:
        """One save/state, or None when RomM no longer has it."""
        r = self._request("GET", f"/api/{kind}/{romm_id}", timeout=30, ok=(404,))
        return None if r.status_code == 404 else r.json()

    def download_asset(self, kind: str, item: Dict) -> bytes:
        """A save/state's content. RomM 5.x: /api/{kind}/{id}/content; older: the item's download_path."""
        r = self._request("GET", f"/api/{kind}/{item['id']}/content", timeout=120, ok=(404, 405))
        if r.status_code in (404, 405):
            if not item.get("download_path"):
                raise RuntimeError(f"RomM returned {r.status_code}: this {kind[:-1]} is gone")
            r = self._request("GET", item["download_path"], timeout=120)
        return r.content

    def confirm_downloaded(self, kind: str, romm_id: int, content_hash: Optional[str]) -> None:
        """Tell RomM this device now holds that save (RomM 5.4+ with a registered device; saves only)."""
        if not self.device_id or kind != "saves":
            return
        try:
            self._request("POST", f"/api/saves/{romm_id}/downloaded", timeout=30, ok=(404, 405, 422),
                          json={"device_id": self.device_id, "content_hash": content_hash})
        except Exception as e:  # noqa: BLE001 - a receipt must never fail a sync
            logger.debug(f"Download receipt for save {romm_id} not recorded: {e}")

    def upload(self, kind: str, local_path: Path, rom_id: int, romm_id: int | None = None,
               screenshot: Path | None = None, upload_name: str | None = None, content: bytes | None = None,
               content_hash: Optional[str] = None, emulator: Optional[str] = None,
               overwrite: bool = False) -> Dict:
        """Create (romm_id=None) or replace (romm_id set) a save/state. content: send these bytes instead of the
        file (folder saves zipped on the fly). With a registered device, RomM refuses an upload over a copy that
        changed since this device last synced it: RommConflict. overwrite=True is a choice made by the user."""
        field_name = "saveFile" if kind == "saves" else "stateFile"
        name = upload_name or local_path.name
        handles = []
        params: Dict[str, object] = {}
        if emulator:
            params["emulator"] = emulator
        if self.device_id and kind == "saves":
            params["device_id"] = self.device_id
            if content_hash:
                params["content_hash"] = content_hash
            if overwrite:
                params["overwrite"] = "true"
        try:
            if content is None:
                fh = open(local_path, "rb")
                handles.append(fh)
                files = {field_name: (name, fh)}
            else:
                files = {field_name: (name, io.BytesIO(content))}
            if screenshot and Path(screenshot).exists():
                sh = open(screenshot, "rb")
                handles.append(sh)
                shot_name = f"{name}.png" if upload_name else Path(screenshot).name
                files["screenshotFile"] = (shot_name, sh)
            if romm_id is None:
                data = self._json("POST", f"/api/{kind}", params={"rom_id": rom_id, **params}, files=files,
                                  timeout=300)
            else:
                put_params = {k: v for k, v in params.items() if k in ("device_id", "content_hash")}
                data = self._json("PUT", f"/api/{kind}/{romm_id}", params=put_params, files=files, timeout=300)
            if isinstance(data, dict):
                self.mark_own(kind, {romm_id, data.get("id")} - {None}, data.get("updated_at") or "")
            return data
        finally:
            for h in handles:
                h.close()

    def delete_assets(self, kind: str, ids: List[int]) -> None:
        """Delete saves/states on RomM (POST /api/{kind}/delete)."""
        if not ids:
            return
        self._request("POST", f"/api/{kind}/delete", json={kind: list(ids)}, timeout=60)
        self.mark_own(kind, ids, None)

    def mark_own(self, kind: str, ids, updated_at) -> None:
        with self._own_lock:
            for i in ids:
                if i is not None:
                    self.own_changes[(kind, i)] = updated_at

    def take_own(self, snapshot: dict) -> None:
        """Forget own changes that are covered by a fingerprint taken after `snapshot` was copied."""
        with self._own_lock:
            for k, v in snapshot.items():
                if self.own_changes.get(k, object()) == v:
                    del self.own_changes[k]

    def fingerprint(self) -> Dict[tuple, tuple]:
        """{(kind, id): (updated_at, rom_id)} for every save and state. Two network requests, no disk access."""
        out = {}
        for kind in ("saves", "states"):
            for it in self.list_all(kind):
                out[(kind, it.get("id"))] = (str(it.get("updated_at")), it.get("rom_id"))
        return out
    # endregion

    # region devices (RomM 5.4+)
    def register_device(self, name: str, client_version: str) -> Optional[str]:
        """Register (or find again) this app as a RomM device -> device id, or None on servers without devices
        or when the token lacks devices.write."""
        payload = {"name": name, "client": CLIENT_NAME, "client_version": client_version,
                   "platform": "docker", "hostname": socket.gethostname(), "sync_mode": "api",
                   "allow_existing": True}
        r = self._request("POST", "/api/devices", json=payload, timeout=30, ok=(401, 403, 404, 405, 422))
        if r.status_code >= 400:
            logger.info(f"RomM didn't register this app as a device ({r.status_code}); syncing without one.")
            return None
        return r.json().get("device_id")

    def list_devices(self) -> List[Dict]:
        r = self._request("GET", "/api/devices", timeout=30, ok=(401, 403, 404, 405))
        return r.json() if r.status_code < 400 else []

    def pair_start(self, identifier: str, name: str, client_version: str) -> Dict:
        """Start RomM's device login: -> {device_code, user_code, verification_path_complete, interval, ...}."""
        payload = {"client_device_identifier": identifier, "name": name, "client": CLIENT_NAME,
                   "platform": "docker", "client_version": client_version, "requested_scopes": PAIR_SCOPES}
        r = self._request("POST", "/api/auth/device/init", json=payload, timeout=30, auth=False, ok=(404, 405, 422))
        if r.status_code in (404, 405):
            raise RuntimeError("This RomM version can't pair devices (RomM 5.4 or newer is needed). "
                               "Use an API token instead.")
        if r.status_code == 422:
            raise RuntimeError(f"RomM refused the pairing request: {r.text[:200]}")
        return r.json()

    def pair_poll(self, device_code: str) -> Optional[Dict]:
        """None while waiting; {access_token, device_id, scopes} once approved; raises when denied/expired."""
        r = self._request("POST", "/api/auth/device/token", json={"device_code": device_code}, timeout=30,
                          auth=False, ok=(400,))
        if r.status_code == 400:
            try:
                why = r.json().get("detail")
            except ValueError:
                why = ""
            if why in ("authorization_pending", "slow_down"):
                return None
            raise RuntimeError({"access_denied": "The pairing was denied in RomM.",
                                "expired_token": "The pairing code expired. Start again."}.get(why, f"Pairing failed: {why}"))
        return r.json()
    # endregion

    # region memory cards (RomM 5.4+)
    def list_cards(self, emulator: Optional[str] = None) -> List[Dict]:
        r = self._request("GET", "/api/memory-cards", params={"emulator": emulator} if emulator else None,
                          timeout=30, ok=(404, 405))
        return r.json() if r.status_code < 400 else []

    def create_card(self, name: str, emulator: str, platform_id: Optional[int] = None) -> Dict:
        return self._json("POST", "/api/memory-cards", json={"name": name, "emulator": emulator,
                                                            "platform_id": platform_id}, timeout=30)

    def card_versions(self, card_id: int) -> List[Dict]:
        return self._json("GET", f"/api/memory-cards/{card_id}/versions", timeout=30)

    def download_card_version(self, version_id: int) -> bytes:
        return self._request("GET", f"/api/memory-cards/versions/{version_id}/content", timeout=120).content

    def upload_card_version(self, card_id: int, file_name: str, data: bytes) -> Dict:
        """RomM only takes card images inside a zip; `data` is the raw card, zipped here under `file_name`."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(file_name, data)
        return self._json("POST", f"/api/memory-cards/{card_id}/versions",
                          files={"cardFile": (file_name + ".zip", buf.getvalue())}, timeout=300)
    # endregion


# The name the rest of the code (and older modules) use.
RommUser = RommClient
