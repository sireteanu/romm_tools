# romm_tools

RomM companion tools in one container, one process and one web page (port 8080):
- **Save sync** (`src/`, from sireteanu/romm_syncthing_sync, a fork of amn-96/romm_syncthing_sync,
  MIT): saves/states between Syncthing folders (`/syncdata/...`) and RomM, both ways. FastAPI +
  uvicorn, loguru, watchdog; page `src/web_static/index.html`.
- **ROM folders** (`src/mapper/`, from sireteanu/rom-mapper): per-frontend folders of links into ROM
  folders, and which folders are which RomM platform (volume lines for RomM's compose file - Docker
  mounts them). Its own FastAPI app (`src/mapper/server.py`, Game names in `src/mapper/names.py`)
  mounted at `/roms/` in the main server; page `src/mapper/static/index.html`.
Python 3.10+, no build step, Docker (Unraid). README.md is the overview; docs/save-sync.md and
docs/rom-folders.md are the full references; docs/user-guide.md is step by step.

**Linux + Docker only.** Paths are POSIX (`/`, no drive letters, no `os.sep` juggling) and the code
and tests create real symlinks - run the tests on Linux (CI: `.github/workflows/tests.yml`).

## Commands
- Install (dev): `pip install -r requirements.txt -r requirements-dev.txt`
- Tests: `python -m pytest tests` (temporary folders and a mock RomM only); lint:
  `python -m pyflakes romm_tools.py src tests`
- Demo: `python -m tests.mock_romm --port 8099` + `python -m tests.demo_setup /tmp/demo` (README)
- Run: `python romm_tools.py` with the env vars from `.env.example`; one-off ROM folders resync:
  `python romm_tools.py --resync`
- Docker: `docker compose up -d` (reads `.env`)

## Credit (keep it)
- amn-96 wrote the original save sync. Keep their copyright line in LICENSE, the credit in README,
  docs/save-sync.md, NOTICE.md and the dashboard footer, and their history in git. NOTICE.md lists
  what the fork and romm_tools changed - update it when an area is added.
- docs/IMPLEMENTATION_SUMMARY.md is amn-96's write-up and docs/history/ the old changelogs: keep them
  as they are (notes on top are fine).

## Rules - both parts
- `romm_tools.py` decides which parts run (`SAVE_SYNC` auto/true/false, `ROM_FOLDERS`); missing save
  sync settings must never stop the container (`Config.problems()`, `load_config()`; only
  `get_config()` callers inside save sync may assume a valid config). `cfg.FEATURES` feeds
  `/api/features`; both pages hide the other part's menu items from it.
- One web server: new save sync routes go in `src/web.py`; ROM folders routes stay in
  `src/mapper/server.py` (served under `/roms/`). The ROM folders page uses **relative** addresses
  (`api/...`, `../api/...`) - never `"/api/...`; the menus link `roms/#links`, `roms/#romm` and
  `../#saves` etc. Basic auth covers everything but `/api/health`.
- Both pages share RomM's design tokens and the top bar from `src/web_static/common.css` (served at
  `/common.css`; the ROM folders page links `../common.css`), the menu script `src/web_static/common.js`
  (`/common.js`: the menu groups, the phone menu button, `RT.syncControls` for the ROM folders page's
  Sync now) and the `rs-theme` localStorage key; keep the menu the same on both (Dashboard, Saves ▾,
  ROMs ▾, Logs, Settings - `tests/test_romm_tools.py` checks it). Settings tabs: `#settings/<tab>`.
- RomM is reached only through `src/romm_client.py` (`RommClient`, alias `RommUser`): one session,
  timeouts, `RommUnreachable` / `RommAuthError` / `RommConflict`. Newer RomM endpoints are used only
  when the server has them (`at_least`, 404/405 tolerated); the mock RomM (`tests/mock_romm.py`,
  shared `romm` fixture in `tests/conftest.py`) mirrors RomM 5.4 and RomM 5.5's held saves.
- One platform list: `src/platforms.py` `known_platforms()` = built-in `romm_slugs.py` + RomM's GitHub
  catalog + the user's RomM (`/api/platforms/supported`).
- Logging: loguru everywhere (ROM folders' `log()` also feeds its Activity card); the Logs page shows
  both parts.
- Version: `VERSION` (and `APP_VERSION` in the image) via `src/version.py`; ROM folders reports the
  same version.

## Rules - save sync
- Stored files in `/data` keep their names (`romm_sync_state.json`, `platform_mapping.yaml`,
  `settings.json`, backups, recycle bin, `game_links.json`) so a romm_sync data folder carries on.
- Never overwrite or delete without a backup / recycle-bin copy first; deletions only when the other
  side is unchanged since the last sync, and more than 10 in one sync wait for approval.
- The RomM check must not read the sync folders unless RomM changed (disks sleep); full folder reads
  only at startup, on Sync now and every `FULL_SCAN_INTERVAL_HOURS`.
- Decisions follow docs/TWO_WAY_SYNC.md (`src/sync_rules.py`); a change to them updates that file and
  `tests/test_sync_engine.py`.
- RomM device (RomM 5.4+, `src/devices.py`): uploads send `device_id` + `content_hash`; a 409 means
  RomM's copy changed - never force it, let the next sync offer a conflict (`overwrite` only when the
  user chose "keep mine"). A 409 on replacing (RomM 5.5 snapshot) -> upload as a new version.
  The paired token lives in `/data/romm_device.json` (mode 600).
- Save names (`src/sync_files.py` `save_style` / `name_in_style` / `remote_local_name`): a game's
  in-game save is one file whether it's `Game.srm`, `Game.gba.sav` (NextUI, what Grout uploads) or
  `Game.sav`; downloads follow the folder's style (Platforms → Options → Save names, stored as
  `folder_save_names` in settings.json), updates keep RomM's name. Grout is a folder mode like `cloud`
  (`grout_folders`). States and other save types are never renamed.
- Standalone emulators (`src/emusaves.py`): per-game units -> RomM saves (PPSSPP as RomM's
  `PSP-<folder>.zip`), shared cards -> RomM memory cards; baseline keys `emu:<folder id>:<name>`;
  deletions are not carried over for these units.

## Rules - ROM folders
- The mapping lives in `<config>/rom-mapper-mapping.json` (+ `.bak`); state in
  `rom-mapper-state.json`; RomM in `romm-mapper.json`. `<config>` is `CONFIG_DIR`, default `DATA_DIR`
  (`/data`). Always write through `atomic_write`, under `csv_lock` (mapping/state) or `romm_lock` (RomM).
- Row keys are `<source label>/<path>`; labels are stored per source path and never change when the
  list is reordered. A key without a known label belongs to the first source (older data) - keep
  that working (`split_key`, `full_key`).
- `links.py` only ever removes **symlinks** inside the mapping folder and folders left empty; never
  delete real files. `check_dest` must refuse dangerous mapping folders (also `/data`, `/syncdata`).
  New links and folders go to `PUID`/`PGID` when running as root (`_owner`, `_makedirs`, `_symlink`).
- RomM (`romm.py`): every folder with a platform is a volume of RomM's container at
  /romm/library/roms/<slug> - the app only generates the lines (`Mapping.volumes`; long syntax when a
  path has ":"); Docker mounts them. The container must not mount or control Docker. No
  platform links (apply_links with no targets only removes old ones), no system.platforms /
  exclude.platforms. Categories are automatic: a platform with a MERGE child that has files gets
  both templates in filesystem.structure, keyed by slug. Rows are `<root>/<path>`; RULES are keyed
  by the path inside a root (`inner()`); a user "exclude" covers the subtree unless a subfolder has
  its own choice. RomM facts it relies on are in the module docstring.
- Older files must keep working: any change to stored formats gets a conversion and a case in
  `tests/mapper/test_upgrades.py` (rows without labels, the minutes/hours schedule, one-folder and Rom
  Sync `romm-mapper.json`). There is no CSV import or export for the frontend grid (removed in
  ROM Mapper 1.0.3) - don't add one back without asking. The only CSV import is the owner-requested
  one-time RomM import (`POST /roms/api/romm/import`, Rom_Mapping_RomM.csv).
- RomM reads never block the page: any read `romm_view` needs (full, or the quick re-check after
  30 s - `romm_read_due`) runs in the background (`start_romm_read`, `/api/romm/progress`) and the
  answer is `{reading}` meanwhile.
  JSON answers over 4 KB are gzipped when the browser accepts it (`GZipMiddleware`); answers go out
  through the module's `jsonify(obj, status)` (a plain `JSONResponse`). Tests set `server.ROMM_BACKGROUND = False` (conftest) to get rows directly.
  Per-download-folder levels are `depths` in `romm-mapper.json` (missing = all levels).
  The folder cache is never reset by saving: its key (`romm_setup`) covers what changes the folders;
  choices/options pass `reuse=True` (no disk access at all). Excluded folders without a choice below
  them are not read inside (`romm_stops` -> `stop`). The cache is stamped when a read ends.
  `skip_names` (default `["media"]`, fnmatch, case-insensitive) is applied while reading
  (`romm.skipped`), is part of the folder cache key, and goes into config.yml's exclude names.
- Disk reads: RomM folder counts (`romm.folders_from_disk`) re-list only folders whose mtime changed,
  with a full read every hour and on Refresh (Unraid shares don't always update a folder's date);
  the page doesn't refresh while its tab is hidden; RomM's platform list comes from
  `/roms/api/romm/platforms` once (`src/platforms.py` `known_platforms()`).
- The container sees one host folder at the same path; frontend links are absolute; RomM's platform
  folders are volumes of RomM's container (host paths).
- Schedule settings are `scan_every`/`scan_unit` and `sync_every`/`sync_unit` (minutes, hours,
  days); `convert_schedule` upgrades the older `scan_interval_minutes`/`sync_interval_hours`.

## Releases
- Every push to `main` is released (`release.yml`): tests, then `VERSION` or the next patch, tag,
  GitHub release (text = the `## [x.y.z]` section of CHANGELOG.md, if there is one), and the GHCR
  image. Add a CHANGELOG.md section for the version a push will get (New / Improved / Fixed /
  Changed, plain words). Raise `VERSION` only for a minor/major, and ask the owner first.
- Docs (README, docs/save-sync.md, docs/rom-folders.md, docs/user-guide.md, CHANGELOG, NOTICE when
  credits change) change in the same commit as the code.

## Privacy
- Docs, examples, tests, screenshots and commit messages use placeholder paths (`/path/to/roms`,
  `/path/to/mapping`, `/path/to/appdata`), never the owner's real folders, shares, IPs or names.
  Screenshots come from the mock RomM (`tests/mock_romm.py`) and invented demo folders.
