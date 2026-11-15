"""The pure two-way sync rule: what to do with one file, given both sides and the last synced state.
docs/TWO_WAY_SYNC.md describes it; tests/test_sync_engine.py covers it. No I/O in here."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .sync_files import LocalFile, parse_dt, same_time  # noqa: F401

@dataclass
class Decision:
    kind: Optional[str]      # None = nothing to do, "adopt" = record baseline only, else ACTION_KINDS
    auto: bool = False
    reason: str = ""
# endregion


def decide(local: Optional[LocalFile], remote: Optional[dict], baseline: Optional[dict],
           push_new_mode: str = "auto", pull_mode: str = "auto", force: bool = False,
           delete_mode: str = "auto", remote_ids: Optional[set] = None) -> Decision:
    """Pure decision function — see module docstring. Kept free of I/O so it is easy to test.

    remote_ids: ids of every RomM save/state for this ROM. A file only counts as deleted on RomM when the
    RomM entry it was synced with is really gone (not just renamed or re-mapped)."""
    pull_on = pull_mode != "off"
    pull_auto = pull_mode == "auto"

    if local and not remote:
        if baseline and baseline.get("romm_id"):
            gone = remote_ids is None or baseline["romm_id"] not in remote_ids
            if gone and delete_mode != "off" and local.hash == baseline.get("local_hash"):
                return Decision("delete_local", delete_mode == "auto",
                                "Deleted on RomM since the last sync, so the copy in your sync folder is moved "
                                "to the recycle bin.")
            return Decision("push_new", False, "This file was synced before but is now missing on RomM. "
                                               "Upload it again, or skip if it was deleted on purpose.")
        return Decision("push_new", push_new_mode == "auto", "New in your sync folder; not on RomM yet.")

    if remote and not local:
        if baseline and delete_mode != "off" and remote.get("id") == baseline.get("romm_id") \
                and same_time(remote.get("updated_at"), baseline.get("romm_updated_at")):
            return Decision("delete_romm", delete_mode == "auto",
                            "Deleted from your sync folder since the last sync, so RomM's copy is moved to the "
                            "recycle bin.")
        if not pull_on:
            return Decision(None)
        if baseline:
            return Decision("pull_new", False, "This file was synced before but is now missing from your sync folder. "
                                               "Download it again, or skip if it was deleted on purpose.")
        return Decision("pull_new", pull_auto, "On RomM but not in your sync folder yet.")

    if not local and not remote:
        return Decision(None)

    r_hash = remote.get("content_hash")
    r_time = parse_dt(remote.get("updated_at"))

    if r_hash and r_hash == local.hash:
        return Decision("adopt", True, "Identical content")

    if force:
        return Decision("push_update", True, "FORCE_PUSH_SYNC")

    if baseline is None:
        # First time we see both copies (fresh install / upgrade from 1.x). No history to compare,
        # so fall back to the original timestamp rule and don't invent conflicts.
        if r_time is None or local.mtime > r_time:
            return Decision("push_update", True, "Local copy is newer")
        if r_hash and pull_on:  # RomM 5.x saves: we *know* contents differ and RomM is newer
            # Ambiguous: no sync history, so we can't tell which copy holds the real progress. Always ask.
            return Decision("pull_update", False, "Both copies exist but are different, and there's no sync history "
                                                  "for this file yet, so it isn't clear which one has your latest "
                                                  "progress. RomM's copy is newer.")
        return Decision("adopt", True, "Assumed in sync (no previous sync record)")

    local_changed = local.hash != baseline.get("local_hash")
    remote_changed = (remote.get("id") != baseline.get("romm_id")
                      or not same_time(remote.get("updated_at"), baseline.get("romm_updated_at"))
                      # a different content hash is a change even within the same second
                      or bool(r_hash and baseline.get("romm_hash") and r_hash != baseline.get("romm_hash")))
    if remote_changed and r_hash and baseline.get("romm_hash") and r_hash == baseline.get("romm_hash"):
        remote_changed = False  # metadata touched, content identical

    if not local_changed and not remote_changed:
        return Decision(None)
    if local_changed and not remote_changed:
        return Decision("push_update", True, "Changed locally since last sync")
    if remote_changed and not local_changed:
        if not pull_on:
            return Decision(None)
        return Decision("pull_update", pull_auto, "Changed on RomM since the last sync.")
    return Decision("conflict", False, "Changed both in your sync folder and on RomM since the last sync, "
                                       "so either version could be the one you want.")
