"""Sentences a person can act on, for errors during save sync."""
from __future__ import annotations

import re

from .config import get_config
from .sync_state import PendingAction

def explain_error(e: Exception, action: PendingAction) -> str:
    """Turn an exception into a sentence a person can act on."""
    import requests
    from .romm_client import RommAuthError, RommConflict, RommUnreachable
    text = str(e)
    where = "RomM" if action.kind.startswith("push") or action.kind == "conflict" else "your sync folder"
    if isinstance(e, PermissionError) or "Permission denied" in text or "Read-only file system" in text:
        return ("Couldn't write to your sync folder (permission denied / read-only). Make sure the saves and "
                "states folders are mounted read-write (no ':ro') and that PUID/PGID can write there.")
    if isinstance(e, OSError) and "No space left" in text:
        return "The disk is full, so the file couldn't be written."
    if isinstance(e, RommConflict):
        return ("RomM's copy changed since this app last synced it, so RomM refused to overwrite it. It's "
                "listed as a conflict for you to choose.")
    if isinstance(e, RommAuthError):
        return ("RomM refused this request. The login or API token probably lacks permission to "
                + ("write saves/states (assets.write)." if where == "RomM" else "read saves/states (assets.read)."))
    if isinstance(e, (RommUnreachable, requests.exceptions.ConnectionError)) or "Can't reach RomM" in text:
        return f"Couldn't reach RomM at {get_config().ROMM_CREDENTIALS.url}. It will be retried on the next sync."
    if isinstance(e, requests.exceptions.Timeout):
        return "RomM took too long to respond. It will be retried on the next sync."
    m = re.search(r"RomM returned (\d{3})", text) or re.search(r"(\d{3}) (?:Client|Server) Error", text)
    code = int(m.group(1)) if m else None
    if code in (401, 403):
        return ("RomM refused this request. The API token probably lacks permission to "
                + ("write saves/states (assets.write)." if where == "RomM" else "read saves/states (assets.read)."))
    if code == 404:
        return "RomM couldn't find this game or file any more (it may have been removed from RomM)."
    if code == 413:
        return "RomM rejected the file as too large. Check the upload size limit of RomM or your reverse proxy."
    if code == 409:
        return "RomM reported a conflict with an existing file. It will be re-checked on the next sync."
    missing = re.search(r"Table '[^.']+\.(\w+)' doesn't exist|relation \"(\w+)\" does not exist", text)
    if missing:
        table = missing.group(1) or missing.group(2)
        return (f"RomM's database is missing the '{table}' table, so RomM can't save or delete files. Its database "
                "update (migration) didn't finish when RomM was last updated. Look for \"Failed to run database "
                "migrations\" in RomM's container log, fix the cause, and restart RomM; it retries the update on "
                "every start. Nothing was changed on either side.")
    if code and code >= 500:
        return f"RomM had an internal error ({code}). Check RomM's logs; it will be retried on the next sync."
    if "back up" in text:
        return "Couldn't make a backup of the RomM copy first, so nothing was overwritten. " + text
    return text
