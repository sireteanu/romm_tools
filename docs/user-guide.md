# romm_tools user guide

Step by step: install romm_tools, set up save sync between your handhelds and RomM, then build
the frontend folders of links and show your ROM folders in RomM. You can use either part on its
own - skip the steps of the part you don't need. For the full reference see the
[README](../README.md), [save sync](save-sync.md) and [ROM folders](rom-folders.md).

- [1. Install and open it](#1-install-and-open-it)
- **Save sync**
  - [2. A RomM API token](#2-a-romm-api-token)
  - [3. Your saves and states folders](#3-your-saves-and-states-folders)
  - [4. The dashboard: what needs you](#4-the-dashboard-what-needs-you)
  - [5. Platforms, settings and notifications](#5-platforms-settings-and-notifications)
- **ROM folders**
  - [6. Choose your source folders](#6-choose-your-source-folders)
  - [7. Add frontends](#7-add-frontends)
  - [8. Map folders](#8-map-folders)
  - [9. Save and resync](#9-save-and-resync)
  - [10. Keep it up to date automatically](#10-keep-it-up-to-date-automatically)
  - [11. RomM library](#11-romm-library)
- [12. Troubleshooting](#12-troubleshooting)

---

## 1. Install and open it

Follow [Install](../README.md#install) in the README. Two things to get right:

- **Save sync:** mount your saves and states folders at `/syncdata/saves` and `/syncdata/states`,
  and `/data` to a persistent app data folder (it holds the sync history that tells changes on
  each side apart).
- **ROM folders:** mount **one** folder that contains all your ROM folders and the mapping folder,
  at the **same path** inside the container (for example `/path/to/shares:/path/to/shares`). After
  that you never need to change the container to use another folder.

Open `http://YOUR-SERVER:8080/`. The menu at the top has both parts: **Dashboard**, **Saves**,
**Platforms** and **Recycle bin** for save sync, **Frontend links** and **RomM library** for ROM
folders, and **Logs** and **Settings**. The version you're running is next to the name; click it to
see what changed. When only ROM folders is set up, the page opens on **Frontend links** and the save
sync items are hidden.

## 2. A RomM API token

In RomM, click your profile picture → **Client API Tokens** → **Create**. Give it read access to
ROMs and platforms and **read + write for saves/states (assets)** - nothing else is needed. Put it
in `ROMM_API_TOKEN` (Unraid: *RomM API token*) with `ROMM_URL` set to RomM's address, and restart
the container. The [save sync reference](save-sync.md#romm) has a picture of a token that works.

## 3. Your saves and states folders

Save sync expects one subfolder per system (`snes`, `gba`, `Nintendo 64`, ...) in your saves and
states folders - RetroArch's *Sort saves/states by content directory*. If they're in one folder,
use `ALL_SYNC_FOLDER` instead (see [Sync folders](save-sync.md#sync-folders)). The log says at
startup how many system folders it found; an empty folder usually means the host path is wrong.

## 4. The dashboard: what needs you

The first sync starts as soon as the container is up. Anything that changed on only one side syncs
by itself. **Needs your attention** lists what doesn't:

- **Conflicts** - a file changed in your folder *and* on RomM. Click **Resolve…** to compare them
  side by side and keep the folder version, the RomM version, or both.
- **Errors** - files that failed, with the reason in plain words, **Retry** and **Dismiss**.
- **Deletions**, **RomM → Folder**, **Folder → RomM** - only when you chose to approve those (or
  more than 10 deletions came at once, which looks like an unmounted share).

Everything that is overwritten or deleted is kept first: backups in `/data/backups`, deleted files
in the **Recycle bin**. The **Saves** page lists every save and state on both sides, with version
history, bulk actions and *Link to a RomM game…* for saves whose names don't match a ROM.

## 5. Platforms, settings and notifications

- **Platforms** shows which RomM platform each system folder of your saves matches. Most match by
  themselves; pick one for the rest (the number on the menu item counts them), or switch a system's
  sync off.
- **Settings** changes how sync behaves (ask first or automatic, deletions, intervals, backups,
  dry run, password) without restarting the container.
- **Settings → Notifications** sends questions, failures and sync problems to Discord, ntfy,
  Gotify, Pushbullet or a webhook. **Send test** checks it.
- **Settings → Syncthing** (optional) waits for Syncthing to finish receiving a file before syncing
  it, and shows your devices on the dashboard.

## 6. Choose your source folders

Open **Frontend links** in the menu and click **Source folders**. Add each folder that holds ROMs, for example `/path/to/roms` and
`/path/to/downloads`. For each one, pick a **depth**:

- **1** - the folders directly inside it become rows (`roms/snes`, `roms/psx`).
- **2** - also the folders inside those (`downloads/Nintendo/Super Famicom`). Use this for
  collections sorted by maker or category.
- Higher numbers go deeper still.

Click **Save & scan**. Every folder found appears in the grid as *New*, with the source folder's
name in front so you can tell collections apart. Folders named `media` are skipped (see step 7).

## 7. Add frontends

Click **+ Frontend** and name it - the name becomes a folder inside the mapping folder (e.g. `rgs`,
`retrobat`, `knulli`). Tick **link media/ folders** if that frontend should also get each system's
`media` folder; the box below sets where they go (default `MEDIA_FULL`). Remove a frontend with ✕
next to its name.

## 8. Map folders

In each cell, type the folder name that frontend should see:

- `snes` -> the frontend gets `<mapping folder>/rgs/snes`, a link to that row's folder.
- `SDCARD/snes` -> a link inside a sub-folder (`<mapping folder>/knulli/SDCARD/snes`).
- Leave a cell blank for no link. **Double-click** an empty cell to fill in the folder's own name.

Rows are marked *New* (not saved yet), *Unmapped* (no names yet) and *Missing* (the folder is gone
from disk - its links come back when it does). Use the chips to filter, the search box to find a
folder, and **Remove missing rows** to tidy up. If two rows give the same name to one frontend,
the second turns orange: only the first row gets that link.

**+ Folder** adds a row for a folder that doesn't exist yet (type it as `<source name>/<path>`).

## 9. Save and resync

- **Save** stores the mapping in the app.
- **Resync all** makes the mapping folder match the saved mapping: missing links are created, wrong
  ones corrected, unused ones removed. Links that are already right aren't touched, so frontends
  keep working while it runs. Your own files in the mapping folder are left alone.
- **Save & resync** does both.

**Last resync** shows the result; click *view output* for details (links created, corrected,
removed, and any problems).

## 10. Keep it up to date automatically

In **Schedule**:

- **Scan every N** looks for new and removed folders. With **Auto-add new folders** they're
  added to the mapping (unmapped, so nothing changes until you give them names).
- **Resync every N** keeps the links in line with the mapping.

Pick **min**, **hours** or **days** next to each number. Scans can run every minute; resyncs at
most every 5 minutes. The card shows when each runs next. Turning a schedule on runs it right away
if it's already due.

## 11. RomM library

Open **RomM library** in the menu (or go to `http://YOUR-SERVER:8080/roms/#romm`). Each folder you give a platform is
mounted into RomM's container under the platform's name, by Docker - nothing is moved.

1. **Download folders** - add your ROM folders. Use **2 levels** if systems have subfolders like
   `+translations` (they become categories). Folders you never want in RomM (`media`, `Extras`) go in
   **Never read folders named**.
2. **Pick the platforms** - folders named like a RomM platform are done already. Click another
   folder's platform and type to search (`commodore`, `sega`…), or **exclude** it. For a platform
   RomM doesn't have (`wiiware`), type the name and choose *Use "…" as a custom platform*. Subfolders of a
   platform show *category of …*; exclude the ones that aren't categories (like `images`).
3. **RomM volumes** - copy them into RomM's compose file (the RomM service's `volumes:`), replacing
   its own `.../romm/library/roms` line, and **Compose Up** RomM. Docker mounts each folder as
   `roms/<platform>` every time RomM starts.
4. **config.yml** - copy it into RomM's `config.yml`, restart RomM and scan its library.

After a change, paste the volumes (and the config, if it changed) again and Compose Up RomM.

Upgrading from a version that made platform links? **Remove old platform links** at the top removes
them (only the links ROM Mapper made).

**RomM platforms list** shows every platform RomM knows, with a search box.

### Game names

Open **Game names** in the menu (`http://YOUR-SERVER:8080/roms/#names`). It reads the `gamelist.xml`
in each platform folder of the RomM library page (and its subfolders) and lists every game whose name
in RomM is different.

1. Renaming needs write access to ROMs: give your RomM API token **roms.write** too (or use a RomM
   login), then restart the container.
2. Are your gamelists somewhere else (ES-DE keeps them in `ES-DE/gamelists/<system>/`)? Mount that
   folder into the container at the same path and add it under **Extra gamelist folders**.
3. For each game: **Rename** gives RomM the gamelist's name - edit the *New name* box first to use
   your own. **Keep** leaves RomM's name and hides the game. Tick several games to do them at once.
4. Changed your mind? **Undo last rename** puts the names back.

## 12. Troubleshooting

**"Source folder not found" / "Folder not found".** The folder isn't inside the folder mounted into
the container, or the path has a typo. Paths must be the same as on the host.

**A link isn't created.** Check the resync output: the folder may be *Missing*, the name may be
used twice for that frontend, or a real file or folder may already be in the way.

**Permission denied.** The container needs write access to the mapping folder and the app data
folder. Set `PUID` / `PGID` (Unraid: 99 / 100) so links and folders it makes belong to your share's
user.

**Save sync isn't running.** A banner on the ROM folders page (and the log) says which setting is
missing - usually `ROMM_URL`, `ROMM_API_TOKEN` or a sync folder. Fix it and restart the container.
To use only ROM folders, set `SAVE_SYNC=false`.

**RomM unreachable / token rejected.** The dashboard says so, failing syncs are retried, and the
container turns *unhealthy* after 15 minutes. Check `ROMM_URL` from inside the container (a
container name only works on the same Docker network) and the token's permissions.

**Something else?** **Logs** shows the whole log - save sync and ROM folders - with a filter and a
download button; the **Activity** card on Frontend links shows that part's recent events.
