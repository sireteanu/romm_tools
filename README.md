# romm_tools

Companion tools for [RomM](https://romm.app/) in one Docker container with one web page:

- **Save sync** - keeps emulator saves and save states in your Syncthing folder in sync with RomM,
  **both ways**, with a dashboard, approvals when it's unclear, side-by-side conflict resolution, a
  recycle bin and notifications.
- **ROM folders** - builds a folder of **links** per emulation frontend (Batocera/RGS, RetroBat,
  Knulli, ...) into your ROM folders, and decides which of your folders is which **RomM platform**
  (volume lines for RomM's compose file and a `config.yml`). Nothing is copied or moved.

Use both, or either one on its own. Made for Unraid; runs on any Linux Docker host.

> **Credits.** Save sync is based on **[romm_syncthing_sync](https://github.com/amn-96/romm_syncthing_sync)**
> by **[amn-96](https://github.com/amn-96)** (MIT) - the library scanner, RomM matching, platform
> mapping and sync modes are their work; the web GUI and two-way sync were added in the fork
> [sireteanu/romm_syncthing_sync](https://github.com/sireteanu/romm_syncthing_sync). ROM folders is
> [sireteanu/rom-mapper](https://github.com/sireteanu/rom-mapper). Both histories are in this
> repository. See [NOTICE.md](NOTICE.md) for exactly who wrote what.

<picture>
  <source media="(prefers-color-scheme: light)" srcset="docs/screenshots/dashboard-light.png">
  <img alt="romm_tools dashboard: sync progress, items waiting for approval, systems and games with RomM covers and save-state screenshots; the menu has Dashboard, Saves, Platforms, Recycle bin, Frontend links, RomM library, Logs and Settings" src="docs/screenshots/dashboard-dark.png">
</picture>

| Frontend links | RomM library | Conflict resolution |
|---|---|---|
| ![Frontend links grid: one row per ROM folder, one column per frontend](docs/screenshots/frontend-links.png) | ![RomM library: platforms per download folder and the volume lines for RomM's compose file](docs/screenshots/romm-library.png) | ![Resolve conflict dialog showing local and RomM versions side by side](docs/screenshots/conflict.png) |

- **New here?** Follow the [user guide](docs/user-guide.md).
- **Full reference:** [save sync](docs/save-sync.md) and [ROM folders](docs/rom-folders.md).
- **What changed?** See the [changelog](CHANGELOG.md) and the [releases](../../releases). The running
  version is shown next to the name at the top of the page.
- **Working on the code (people or AI assistants)?** This README is the overview; coding rules are in
  [CLAUDE.md](CLAUDE.md).

---

## Contents

1. [Features](#features)
2. [Install](#install)
3. [Configure](#configure)
4. [Moving over from romm_sync or ROM Mapper](#moving-over-from-romm_sync-or-rom-mapper)
5. [How the two parts fit together](#how-the-two-parts-fit-together)
6. [HTTP API](#http-api)
7. [Code map](#code-map)
8. [Development, tests and releases](#development-tests-and-releases)
9. [Credits & license](#credits--license)

---

## Features

### Save sync ([reference](docs/save-sync.md))

| Area | What it does |
|---|---|
| Two-way sync | Saves and states that changed on one side sync by themselves, in both directions. You're only asked when a file changed on both sides, was deleted on one side but changed on the other, or two copies differ with no history. |
| Dashboard | Live progress, every system with a status bar, every game with its RomM cover and latest save-state screenshot, and what needs your attention. |
| Conflicts | Nothing is overwritten: compare both versions side by side, keep one or both. Backups are made before any overwrite. |
| Saves page | Every save and state on both sides with filters, bulk delete/download/upload, version history (put back any copy), `.zip` export, and linking saves to RomM games by hand. |
| Deletions | Synced both ways through a recycle bin, with safety rails (only unchanged files, never more than 10 at once). |
| Platforms | Each system folder of your saves matched to a RomM platform, using RomM's own platform list and folder aliases. |
| Settings, notifications | Change behaviour from the page; Discord, ntfy, Gotify, Pushbullet or webhook notifications; optional Syncthing integration. |
| Disks sleep | RomM is polled through its API; your folders are only re-read when something changed. |

### ROM folders ([reference](docs/rom-folders.md))

| Area | What it does |
|---|---|
| Frontend links | A grid with one row per folder in your source folders and one column per frontend. Type the name a frontend should see; **Resync** makes `<mapping folder>/<frontend>/<name>` links, optionally with each system's `media/` folder. |
| Status, schedule | Rows marked *New*, *Unmapped*, *Missing*; duplicate names highlighted. Scans and resyncs on their own schedule; a resync changes only what differs. |
| RomM library | Pick the RomM platform for any of your download folders (nested too); get the **volume lines** for RomM's compose file (each folder mounted as `roms/<platform>`) and a `config.yml` with categories for platforms with subfolders. One-time import of an old RomM mapping CSV. |
| Game names | RomM's name for each game next to the `<name>` in your frontends' `gamelist.xml` (also gamelists in subfolders). Where they differ: give RomM the gamelist's name, type your own, or keep RomM's - one game or many at once, with **Undo**. Only the name shown in RomM changes. |

### Shared

One port, one menu, RomM's look in light and dark, one optional password, one log (**Logs**
page), one app data folder, a Docker health check, an Unraid template, and a release with a Docker
image for every change.

---

## Install

romm_tools needs these mounts - leave out the ones of a part you don't use:

| Container path | What | Part |
|---|---|---|
| `/data` | App data: sync history, approvals, backups, recycle bin, logs, ROM folders mapping and settings. **Keep it persistent.** | both |
| `/syncdata/saves`, `/syncdata/states` (or `/syncdata` for one folder) | Your saves and states folders, one subfolder per system | save sync |
| **the same path as on the host** | ONE folder containing your ROM folders, the frontend links folder and RomM's download folders (Unraid: `/mnt/user`). Links are absolute, so they must resolve the same way outside the container. | ROM folders |

### Unraid (template)

1. Add the template. Open the Unraid terminal (**>_** in the top bar) and run:
   ```bash
   wget -O /boot/config/plugins/dockerMan/templates-user/my-romm-tools.xml \
     https://raw.githubusercontent.com/sireteanu/romm_tools/HEAD/unraid/romm-tools.xml
   ```
2. Go to **Docker → Add Container**, pick **romm-tools** from the **Template** dropdown, and fill in:
   - **App data**: `/mnt/user/appdata/romm-tools`
   - Save sync: **Saves folder** / **States folder** (e.g. `/mnt/user/syncthing/saves`), **RomM URL**
     and **RomM API token**
   - ROM folders: **Emulation folder (same path)** (default `/mnt/user`), **ROM source folders** and
     **Frontend links folder**
3. **Apply**, then click the container icon → **WebUI**.

Only ROM folders? Set **Save sync** (advanced view) to `false` and remove the saves/states paths.
Only save sync? Set **ROM folders** to `false` and remove the emulation folder path.
Saves and states in **one** folder: switch to **Advanced View**, remove the States folder path and the
`SAVE_SYNC_FOLDER` / `STATE_SYNC_FOLDER` variables, change the Saves folder's container path to
`/syncdata`, and add a variable `ALL_SYNC_FOLDER` = `/syncdata`.

### Unraid (Compose Manager)

Docker > Compose > Add New Stack `romm-tools` > Edit Stack, paste
[`unraid/docker-compose.yml`](unraid/docker-compose.yml), set the paths and RomM settings, then
**Compose Up**. Every Compose Up pulls the latest image.

### Docker Compose (any Linux host)

Download [`docker-compose.yml`](docker-compose.yml) and [`.env.example`](.env.example) to a folder, then:

```bash
cp .env.example .env     # set the paths, RomM address and token
docker compose up -d
```

Open `http://<server>:8080`. Remove the volume lines (and switch off the part in `.env`) of a part you
don't use - compose refuses an empty path.

### Without Docker (Linux)

```bash
pip install -r requirements.txt
DATA_DIR=/path/to/appdata/romm-tools SRC_BASE=/path/to/roms DEST_PATH=/path/to/mapping \
  ROMM_URL=http://romm:8080 ROMM_API_TOKEN=... SAVE_SYNC_FOLDER=1 STATE_SYNC_FOLDER=1 \
  python romm_tools.py
```

Save sync reads its folders from the fixed paths `/syncdata/saves` and `/syncdata/states`, so create
those (or links to your folders) first. One-off ROM folders resync without the page:
`python romm_tools.py --resync` (in Docker: `docker exec romm-tools python romm_tools.py --resync`).

**Update:** pull the new image (`docker compose pull && docker compose up -d`, or *Check for updates*
on Unraid). Settings, history and mapping are kept in `/data`.

---

## Configure

All settings are environment variables (`.env.example`, or the Unraid template). Most save sync
settings can also be changed on the **Settings** page; ROM folders' source folders, frontends,
schedule and RomM choices are set in its pages.

### Which parts run

| Variable | Default | |
|---|---|---|
| `SAVE_SYNC` | auto | `auto`: on as soon as `ROMM_URL` or a sync folder is set. `true` / `false` |
| `ROM_FOLDERS` | true | `false` hides Frontend links and RomM library and stops their schedule |

When save sync is on but a required setting is missing, the container keeps running: the log and a
banner on the ROM folders page say what's missing.

### Shared

| Variable | Default | |
|---|---|---|
| `DATA_FOLDER` → `/data` | `./data` | app data on the host (compose) |
| `WEB_HOST_PORT` | 8080 | host port of the web page (compose) |
| `WEB_USERNAME` / `WEB_PASSWORD` | empty | optional basic auth for the whole page, both parts. Also on the Settings page |
| `PUID` / `PGID` | - | owner of files written into the sync folders and of the frontend links and their folders (Unraid: `99` / `100`) |
| `FILE_MODE` | 0777 | permissions for files written into the sync folders and backups |
| `TZ` | UTC | log timestamps and the ROM folders schedule |
| `LOG_LEVEL` | INFO | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `WEB_UI` | true | `false` turns the web page off (both parts keep running) |

There is no other login: don't expose the port to the internet without a password or a reverse proxy
with authentication.

### Save sync

`ROMM_URL`, `ROMM_AUTH_TYPE` (`api` recommended), `ROMM_API_TOKEN` (or `ROMM_USERNAME` /
`ROMM_PASSWORD`), and `SAVE_SYNC_FOLDER` + `STATE_SYNC_FOLDER` (or `ALL_SYNC_FOLDER`) are required;
everything else - sync mode, two-way behaviour, deletions, backups, RomM versions, Syncthing,
notifications - is explained in [Save sync → Configure](docs/save-sync.md#configure).

### ROM folders

| Variable | Compose `.env` | |
|---|---|---|
| (volume) | `EMULATION_ROOT` | the one folder mounted at the same path |
| `SRC_BASE` | `ROMS_PATH` | first source folder(s), `;`-separated, until set in the page |
| `DEST_PATH` | `MAPPING_PATH` | the frontend links folder, one sub-folder per frontend. A folder of its own |
| `ROMM_SOURCE` | `ROMM_SOURCE` | RomM download folders, `;`-separated, until set in the page |
| `CONFIG_DIR` | - | where ROM folders keeps its files (default: `/data`) |

See [ROM folders → Settings and files](docs/rom-folders.md#settings-and-files).

---

## Moving over from romm_sync or ROM Mapper

- **romm_sync** (sireteanu/romm_syncthing_sync): use the same app data folder for `/data` and the
  same saves/states mounts. Sync history, approvals, backups, recycle bin, Settings-page values and the
  platform mapping are picked up as they are; nothing is synced again. Old images were
  `ghcr.io/sireteanu/romm_syncthing_sync`; the new one is `ghcr.io/sireteanu/romm_tools`.
- **ROM Mapper** (sireteanu/rom-mapper): copy `rom-mapper-mapping.json`, `rom-mapper-state.json` and
  `romm-mapper.json` from its config folder into the app data folder (or mount the old folder and
  set `CONFIG_DIR` to it), and mount the same emulation folder at the same path. The links, schedule
  and RomM choices carry on unchanged. Its page moved from port 8085 to `http://SERVER:8080/roms/`.
  ROM Mapper ran as `99:100`; romm_tools runs as root for save sync, so set `PUID=99` / `PGID=100`
  to keep new links owned by your share's user.
- Running both old containers? Stop them after romm_tools is up, so two apps don't sync or resync
  the same folders.

---

## How the two parts fit together

```
                        romm_tools container (one process)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  web server :8080 (FastAPI)       optional password, one menu, one log       │
 │   ├─ /            save sync pages ── src/web.py, src/web_static/             │
 │   └─ /roms/       ROM folders pages ─ src/mapper/ (Flask app, mounted)       │
 │                                                                              │
 │  save sync loop (watch / periodic)   ROM folders scheduler (scan / resync)   │
 │   /syncdata ⇄ RomM API               source folders → links in DEST_PATH     │
 │                                       download folders → RomM volume lines   │
 │  /data: history, backups, recycle bin, logs, platform catalog, ROM mapping   │
 └──────────────────────────────────────────────────────────────────────────────┘
```

- `romm_tools.py` reads the settings, decides which parts run, starts the ROM folders scheduler and
  the web server, then runs save sync (or just waits, when it's off).
- The two parts share the platform catalog (`/data/romm_platforms.json`, RomM's platform list from
  GitHub): save sync uses it to match save folders, the RomM library picker adds its newer platforms.
- Everything else stays separate: save sync never reads your ROMs (the game list comes from RomM's
  API) and ROM folders never talks to RomM.

---

## HTTP API

JSON throughout; the pages use nothing else. With a password set, every path except `/api/health`
needs it.

**Shared**

| Method & path | Purpose |
|---|---|
| `GET /api/features` | `{save_sync, rom_folders, save_sync_problem}`: which parts run |
| `GET /api/health` | Docker health check (503 once syncs have failed for 15 minutes) |

**Save sync** (`/`)

| Method & path | Purpose |
|---|---|
| `GET /api/status` · `POST /api/sync` | Everything the dashboard shows · sync now |
| `POST /api/actions/{id}` · `POST /api/actions/bulk` | Approve / reject / resolve pending items |
| `POST /api/errors/retry` · `POST /api/errors/dismiss` | Failed files |
| `GET /api/platforms` · `POST /api/platforms/refresh` · `PUT /api/platforms/mapping` · `PUT /api/platforms/enabled` | Platforms page |
| `GET /api/saves` · `POST /api/saves/action` · `GET /api/saves/job` · `GET /api/saves/{id}/versions` (`/download`, `/restore`) · `POST /api/saves/zip` | Saves page |
| `GET /api/romm/search` · `PUT /api/links` | Link a save to a RomM game by hand |
| `GET /api/recycle` · `POST /api/recycle/empty` · `POST /api/recycle/{id}/restore` · `/delete` · `GET /api/recycle/{id}/download` | Recycle bin |
| `GET /api/settings` · `PUT /api/settings` · `PUT /api/notifications` · `POST /api/notifications/test` | Settings page |
| `GET /api/syncthing` · `GET /api/syncthing/folders` | Syncthing integration |
| `GET /api/logs` · `GET /api/logs/download` | Logs page (both parts) |
| `GET /img/romm`, `/img/local`, `/img/platform/{slug}` | Covers, state screenshots, platform icons |

**ROM folders** (`/roms/`)

| Method & path | Purpose |
|---|---|
| `GET /roms/api/state` | Mapping (frontends, rows with status), `version` (for saving), `app_version`, source folders, paths, settings, last scan/resync, `sync_running` |
| `PUT /roms/api/mapping` `{version, frontends, rows, resync?, force?}` | Save (409 if the mapping changed since `version`; `force` overrides); 400 with details on invalid names |
| `PUT /roms/api/sources` `{sources: [{path, depth}]}` | Set the source folders (labels are kept per path) |
| `POST /roms/api/scan` · `POST /roms/api/sync` · `GET /roms/api/sync` | Scan now · start a resync (409 when running) · resync status |
| `PUT /roms/api/settings` | Schedule settings |
| `GET /roms/api/activity` | Recent events |
| `GET /roms/api/romm/platforms` | RomM's platform list (`slugs`), loaded once by the page |
| `GET /roms/api/romm` · `PUT /roms/api/romm/options` · `PUT /roms/api/romm/map {path, action}` · `POST /roms/api/romm/links` · `POST /roms/api/romm/import` | RomM library data, options (download folders, `depths`, `skip_names`), a folder's choice, remove old platform links, one-time CSV import. While the folders are read in the background the answer is `{reading: {...}}` |
| `GET /roms/api/romm/progress` | The background read: `running`, `source` / `sources`, `path`, `done` / `total`, `current`, `error` |
| `GET /roms/api/names[?fresh=1]` · `GET /roms/api/names/progress` | Game names: rows where RomM's name differs from the gamelist's, gamelists read, platforms without one, summary (`{reading}` while gamelists and RomM are read in the background) |
| `PUT /roms/api/names/options {folders}` · `PUT /roms/api/names/ignore {ids, ignore}` | Extra gamelist folders · keep RomM's name for games (until the gamelist name changes) |
| `POST /roms/api/names/apply {changes: [{id, name}]}` · `POST /roms/api/names/undo` | Rename in RomM (only `name` is sent) · put back the last batch |

---

## Code map

```
romm_tools.py            entry point: settings, which parts run, web server, save sync loop;
                         --resync = one-off ROM folders resync
src/web.py               the web server (FastAPI): save sync API, /api/features, mounts ROM folders
src/web_static/          save sync pages (one HTML file, no build step)
src/config.py            settings from the environment, SAVE_SYNC / ROM_FOLDERS switches
src/sync_orchestrator.py save sync loop: watch / periodic, RomM poller      (amn-96, extended)
src/sync_engine.py       two-way decisions, transfers, backups               (fork)
src/sync_state.py        sync history, pending approvals, log sink           (fork)
src/library_classes.py   local library scan and RomM matching                (amn-96, extended)
src/games_class.py       per-game save/state handling                        (amn-96)
src/romm_api_func.py     RomM API client                                     (amn-96, extended)
src/platforms.py         RomM platform catalog from GitHub, platform mapping (fork)
src/manage.py            Saves page: inventory, bulk actions, history, zip   (fork)
src/recycle.py           recycle bin                                         (fork)
src/settings.py          Settings page values                                (fork)
src/notify.py            notifications                                       (fork)
src/syncthing.py         Syncthing integration (read-only)                   (fork)
src/version.py           version and update check
src/mapper/server.py     ROM folders (Flask): mapping storage, source folders, scan, resync,
                         scheduler, RomM library endpoints                   (ROM Mapper)
src/mapper/links.py      link engine: desired links, apply only the differences (ROM Mapper)
src/mapper/romm.py       RomM library: folder roles, platforms as mounts, categories, config.yml
src/mapper/romm_slugs.py RomM's platform list (vendored)
src/mapper/gamelists.py  Game names: read gamelist.xml files, match them to RomM's games
src/mapper/static/       ROM folders page (one HTML file, no build step)
tests/                   save sync tests, mock RomM and demo data; test_romm_tools.py = the glue
tests/mapper/            ROM folders tests (test_mapping, test_romm, test_upgrades, test_gamelists)
unraid/                  Unraid template and Compose Manager file
.github/workflows/       tests.yml (every push), release.yml (a release per push to main)
docs/                    user guide, references, design notes, old changelogs, screenshots
```

---

## Development, tests and releases

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests                       # everything runs on temporary folders
python -m pyflakes romm_tools.py src tests
python -m tests.mock_romm --port 8099        # fake RomM 5.4 API with demo games
python -m tests.demo_setup /tmp/demo         # matching demo sync folders
```

To run against the mock: link `/syncdata/saves` and `/syncdata/states` to `/tmp/demo/saves` and
`/tmp/demo/states`, then

```bash
ROMM_URL=http://127.0.0.1:8099 ROMM_AUTH_TYPE=api ROMM_API_TOKEN=x \
SAVE_SYNC_FOLDER=1 STATE_SYNC_FOLDER=1 DATA_DIR=/tmp/demo/data SYNC_MODE=watch \
SRC_BASE=/tmp/demo/roms DEST_PATH=/tmp/demo/mapping python romm_tools.py
```

**Releases.** Every push to `main` is released automatically
([`.github/workflows/release.yml`](.github/workflows/release.yml)):

1. the tests run;
2. the version is `VERSION` if that tag doesn't exist yet, otherwise the next patch number
   (1.0.0 → 1.0.1 → …);
3. a git tag and GitHub release are created; the release text is that version's `## [x.y.z]`
   section of [CHANGELOG.md](CHANGELOG.md), or notes generated from the commits if there is none;
4. `ghcr.io/sireteanu/romm_tools:{version}`, `:{major.minor}` and `:latest` are published (amd64 + arm64);
5. correcting a changelog section later updates that release's text.

Raise `VERSION` for a new minor/major. Add `[skip release]` to a commit message to push without
releasing. The **Tests** workflow runs on every push. Every behaviour change gets a test, anything
that reads older files gets a case in `tests/mapper/test_upgrades.py` (ROM folders) or keeps save
sync's stored file names, and documentation (this README, the references, the user guide, the
changelog) is updated in the same commit.

---

## Credits & license

- Save sync: original project **[romm_syncthing_sync](https://github.com/amn-96/romm_syncthing_sync)
  by [amn-96](https://github.com/amn-96)**. Thank you!
- Save sync's web GUI and two-way sync: [sireteanu](https://github.com/sireteanu), first in
  [sireteanu/romm_syncthing_sync](https://github.com/sireteanu/romm_syncthing_sync).
- ROM folders: [sireteanu/rom-mapper](https://github.com/sireteanu/rom-mapper).
- [RomM](https://github.com/rommapp/romm) by the RomM team. This project only uses its public API
  and its public platform list. It isn't made by, affiliated with, or endorsed by the RomM project.

MIT License. See [LICENSE](LICENSE) (original copyright retained) and [NOTICE.md](NOTICE.md).
