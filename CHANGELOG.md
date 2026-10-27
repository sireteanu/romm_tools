# Changelog

What changed in each romm_tools release. The section for a version becomes the text of its GitHub
release. Newest first.

romm_tools continues two projects; their own changelogs are kept as they were:
[romm_sync (save sync)](docs/history/romm_sync-CHANGELOG.md), up to 2.11.0, and
[ROM Mapper (ROM folders)](docs/history/rom-mapper-CHANGELOG.md), up to 1.0.14.

## [Unreleased]

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
