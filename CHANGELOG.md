# Changelog

What changed in each romm_tools release. The section for a version becomes the text of its GitHub
release. Newest first.

romm_tools continues two projects; their own changelogs are kept as they were:
[romm_sync (save sync)](docs/history/romm_sync-CHANGELOG.md), up to 2.11.0, and
[ROM Mapper (ROM folders)](docs/history/rom-mapper-CHANGELOG.md), up to 1.0.14.

## [Unreleased]

## [2.1.1] - 2026-11-15

### Fixed
- The dashboard's *Finish setting up* list couldn't be closed while a step was left. **✕ Hide** now
  always closes it; it comes back only when a different step is left to do.

## [2.1.0] - 2026-11-15

Works alongside Grout on handhelds (NextUI, Knulli, Batocera, muOS), and an easier page to find your
way around. Existing setups keep working: settings, data folder and stored files are unchanged.

### New
- **Grout and NextUI save names.** A handheld with Grout uploads its saves to RomM under its own
  name: NextUI's `Game (USA).gba.sav` where RetroArch uses `Game (USA).srm`. romm_tools now treats
  `Game.srm`, `Game.sav` and `Game.gba.sav` of one game as the same save: a download is named the way
  the folder expects, and an upload updates the save the handheld made instead of adding a second one.
- **Save names per system** (Platforms → Options): Automatic (like the saves already in the folder),
  RetroArch (`.srm`), MinUI / NextUI (`.gba.sav`), Generic (`.sav`) or RomM's name.
- **Grout** as a *Synced by* choice on the Platforms page, for a handheld whose saves folder is also
  shared with this app through Syncthing. The dashboard shows a note when RomM knows a Grout device.
- **Getting started**: on a new install the dashboard lists what's left to do (RomM connected, system
  folders found and matched, plus the optional device registration and Syncthing), each with a button.
- **Settings tabs**: Sync, RomM, Emulators, Syncthing, Notifications and Access (`#settings/romm` opens
  one directly).

### Improved
- **Menu**: grouped into Dashboard, Saves ▾ (Saves, Platforms, Devices, Recycle bin), ROMs ▾ (Frontend
  links, RomM library, Game names), Logs and Settings. On a phone it's one ☰ button instead of a row
  that scrolled off the screen. The ROM folders pages have the same top bar, with the connection and
  **Sync now**.
- **Dashboard**: shorter. The game cards moved to the Saves page (**Cards**); clicking a system opens
  the Saves page for it, and the counts (*unmatched*, *in sync*, *conflicts*, *failed*) open the
  matching list.
- **Saves page**: opens on *Not in sync* when anything isn't, and a file marked *Different* says what the
  next sync does with it (uploads, downloads, or asks you).
- **Platforms page**: folders without a platform come first; who syncs a folder, its save names and its
  emulator are under one **Options** button, with a chip on the row when they're not the default.
- **Settings**: times are a number and a unit (10 minutes) instead of seconds; fields for the other sync
  mode are hidden; notifications are saved with **Save settings** like everything else.
- **Devices page**: each device is labelled (this app, Grout, RetroArch), and one game's save is one row
  even when devices name it differently.
- **ROM folders**: with no frontend yet, the grid explains how to add one; the storage paths are folded
  into one line.
- Built-in folder names for NextUI: `mgba`, `supa`, `sgb`, `gg`, `sms`, `pce`, `pkm`, `ws`/`wsc`,
  `lynx`, `p8`.

### Fixed
- PC Engine folders (`pcengine`, `pc-engine`, `tg16`, `turbografx`…) were mapped to the PC Engine **CD**
  platform; they now point at TurboGrafx-16/PC Engine (`tg16`), and `pcenginecd` at the CD system. A
  saved mapping that still has the old entries is fixed at startup.
- The RetroArch Cloud Sync check could skip RomM's device list during the first hour after the host
  started.

## [2.0.0] - 2026-11-15

Ready for RomM's own device sync and RomM 5.5, saves of standalone emulators, and a tidier app
underneath. Existing setups keep working: settings, data folder and stored files are unchanged.

### New
- **romm_tools is a RomM device** (RomM 5.4+). It registers itself as *romm_tools on <host>* and sends
  its device id with uploads and downloads. RomM then knows which version this app last synced: if a
  save changed on RomM in the meantime, RomM refuses the upload and you're asked instead of anything
  being overwritten. Settings → RomM connection; `DEVICE_SYNC=off` turns it off.
- **Pair with RomM instead of an API token** (RomM 5.4+): Settings → RomM connection → *Pair with RomM*,
  then approve the short code in RomM. RomM issues a token for this device; *Forget pairing* goes back
  to the login from the container settings.
- **Standalone emulators** (Settings → Standalone emulators): DuckStation memory cards, PCSX2 memory
  cards, Dolphin GameCube saves and PPSSPP save folders. Per-game saves sync as RomM saves (matched
  by title, or linked by hand); cards shared by many games sync as RomM memory cards. PPSSPP folders
  use RomM's own `PSP-<folder>.zip` name, so RetroArch Cloud Sync and romm_tools share them.
- **Devices page**: for each save, which device last synced it and whether it has the newest version
  (from RomM), plus your Syncthing devices.
- **RetroArch Cloud Sync**: each system on the Platforms page can be synced by romm_tools, left to
  RetroArch Cloud Sync, or not synced. The dashboard warns when RetroArch Cloud Sync also uploads
  saves for games romm_tools syncs, which can make saves bounce back and forth.
- **Emulator per system** (Platforms page): sent to RomM with uploads; the Saves page shows which
  emulator wrote RomM's copy, and a download written by a different emulator waits for your approval.
- **gamelist.xml through RomM**: on the RomM library page, `config.yml` can tell RomM to take names
  from your gamelists first and to write gamelists after scans; the Game names page can ask RomM to
  write `gamelist.xml` files now.

### Improved
- **RomM 5.5**: saves held by RomM 5.5's save snapshots can't be replaced in place; romm_tools then
  uploads the new copy as the next version instead of failing.
- RomM's download receipts are sent after each download, so RomM's device list stays right.
- **One platform list** for both parts: the built-in list, RomM's GitHub, and your own RomM's list of
  supported platforms (always right for your RomM version).
- A different content hash on RomM counts as a change even within the same second.
- The menu moves to its own row on narrower screens instead of being cut off.

### Changed
- ROM folders runs on the same web framework as the rest of the app (FastAPI); Flask and a2wsgi
  are no longer needed. Addresses and behaviour are unchanged.
- Under the hood: one RomM client for both parts, one shared stylesheet, the save sync engine and the
  ROM folders server split into smaller modules, and unused code from the original one-way sync removed.

## [1.0.3] - 2026-10-31

### Improved
- **Looks like RomM.** Buttons, text fields, drop-downs, checkboxes, tables and tags on every page
  now look and behave like RomM's own: RomM's checkboxes with the purple fill, fields with RomM's
  hover and focus glow, RomM's drop-down arrow, tables with RomM's small uppercase headers and row
  highlight, and RomM's flat buttons. The Frontend links, RomM library and Game names pages now
  match the save sync pages.

### Changed
- Example addresses in the settings, Unraid template and docs read `http://YOUR-SERVER:8384`.

## [1.0.2] - 2026-10-31

### New
- **Game names** page (menu: *Game names*, `/roms/#names`): RomM's name for each game next to the
  name in your frontend's `gamelist.xml` (ES-DE, Batocera, RetroBat, Knulli). Where they differ, give
  RomM the gamelist's name, type your own, or keep RomM's - one game or many at once, with
  **Undo last rename**. Only the name shown in RomM changes; files and gamelists aren't touched, and
  RomM keeps the new name when it scans again.
- The gamelists are read from the platform folders of the RomM library page and their subfolders
  (a gamelist in `snes/Hacks/` counts for the games in `Hacks/`); folders without one are skipped and
  listed. Gamelists kept elsewhere (ES-DE's `gamelists` folder) can be added on the page.
- Renaming needs a RomM API token with write access to ROMs (`roms.write`) or a RomM login.

## [1.0.1] - 2026-10-27

### Fixed
- Runs on Python 3.10 and 3.11 outside Docker, as the README says: a log line in save sync needed
  Python 3.12. The Docker image (Python 3.13) wasn't affected.

## [1.0.0] - 2026-10-27

The first romm_tools release: **romm_sync** (save sync, sireteanu/romm_syncthing_sync 2.11.0, based
on [romm_syncthing_sync](https://github.com/amn-96/romm_syncthing_sync) by amn-96) and **ROM Mapper**
(ROM folders, sireteanu/rom-mapper 1.0.14) in one container. Everything both did before works the
same.

### New
- **One container, one web page.** Save sync's pages (Dashboard, Saves, Platforms, Recycle bin) and
  ROM Mapper's (now **Frontend links** and **RomM library**, at `/roms/`) share one menu, one port
  (8080), one look (RomM's colours, light and dark) and the theme switch.
- **Use either part on its own.** `SAVE_SYNC` (`auto`, `true`, `false`) and `ROM_FOLDERS` (`true`,
  `false`). With `auto`, save sync runs once a RomM address or sync folder is set; a container set up
  only for ROM folders opens on Frontend links and hides the save sync menu items.
- **Missing save sync settings no longer stop the container.** The problem is shown on the ROM
  folders page and in the log, and ROM folders keeps running.
- **The password covers everything.** `WEB_USERNAME` / `WEB_PASSWORD` (or the Settings page) now
  also protect the ROM folders pages.
- **One log.** ROM folders' scans and resyncs appear on the **Logs** page and in
  `/data/logs/romm_tools.log`, next to save sync.
- **Newer RomM platforms in the RomM library picker**, from the platform catalog save sync downloads
  from RomM's GitHub, on top of ROM Mapper's built-in list.
- **Frontend links belong to your share's user.** The container runs as root (for save sync); with
  `PUID` / `PGID` set, every link and folder ROM folders makes is handed to that user.
- **Unraid:** one template, `unraid/romm-tools.xml`, with the emulation folder and ROM folders
  settings added; or `unraid/docker-compose.yml` for Compose Manager.
- Docker image `ghcr.io/sireteanu/romm_tools` (amd64 + arm64). Every push to `main` is tested and
  released; the release text comes from this changelog.

### Changed
- ROM folders' settings and mapping live in the app data folder (`/data`) with save sync's;
  `CONFIG_DIR` still points them elsewhere. The page moved from port 8085 to `/roms/` on port 8080,
  and the one-off resync is `docker exec romm-tools python romm_tools.py --resync`.
- `SRC_BASE` and `DEST_PATH` have no defaults any more: set them, or the source folders in the page.
- Notification titles, the log file and the zip download are named romm_tools. Save sync's stored
  files (`romm_sync_state.json`, `platform_mapping.yaml`, backups, recycle bin) keep their names, so
  an existing `/data` folder carries on.

### Moving over
- From **romm_sync**: point `/data` at its app data folder - history, approvals, backups, recycle
  bin, settings and platform mapping are picked up as they are.
- From **ROM Mapper**: copy `rom-mapper-mapping.json`, `rom-mapper-state.json` and `romm-mapper.json`
  into the app data folder (or set `CONFIG_DIR` to the old config folder) and mount the same
  emulation folder at the same path.
