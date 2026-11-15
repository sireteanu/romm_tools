# Notice & credits

romm_tools brings two projects together in one container and one web page. Their full git
histories are part of this repository, so every original commit keeps its author.

## Save sync - based on romm_syncthing_sync by amn-96

The save sync part is based on **[romm_syncthing_sync](https://github.com/amn-96/romm_syncthing_sync)**
by **[amn-96](https://github.com/amn-96)**, released under the MIT License.

All of the original design and code - the library scanner, RomM matching, platform mapping,
watch/periodic sync modes, save-state screenshot handling and Docker packaging - is amn-96's work.
The original copyright notice and license text are kept in [`LICENSE`](LICENSE), as the MIT License
requires. Their commits are in this repository's history up to `1d08deb`, the last upstream commit
the fork is based on, and their architecture write-up is kept as
[`docs/IMPLEMENTATION_SUMMARY.md`](docs/IMPLEMENTATION_SUMMARY.md).

### What the fork changed (sireteanu/romm_syncthing_sync)

Modifications by [sireteanu](https://github.com/sireteanu), first made in the fork
[sireteanu/romm_syncthing_sync](https://github.com/sireteanu/romm_syncthing_sync) (up to 2.11.0, its
[changelog](docs/history/romm_sync-CHANGELOG.md)), also under the MIT License:

| Area | Files |
|---|---|
| Web dashboard (progress, systems, games, RomM covers and state screenshots, approvals, conflict resolution) | `src/web.py`, `src/web_static/index.html` |
| Two-way sync engine with sync history, approvals, conflict detection and backups | `src/sync_engine.py`, `src/sync_state.py` |
| Integration with the original sync loop, RomM poller, rename-event fix | `src/sync_orchestrator.py`, `romm_tools.py` (was `romm_sync.py`) |
| New config options, API-token validation fix | `src/config.py`, `src/romm_api_func.py` (now `src/romm_client.py`), `.env.example` |
| Unraid template, Docker/compose updates, auto-release workflow | `unraid/`, `Dockerfile`, `docker-compose.yml`, `.github/workflows/release.yml` |
| Platform catalog from RomM's GitHub, Platforms page, automatic platform resolution | `src/platforms.py`, `src/library_classes.py` |
| Settings page, notifications (Discord, ntfy, Gotify, Pushbullet, webhook) | `src/settings.py`, `src/notify.py` |
| Version display and update check | `src/version.py` |
| Deletion sync and recycle bin | `src/recycle.py`, `src/sync_engine.py` |
| Saves page (inventory, bulk actions, version history, zip export, automatic version pruning) | `src/manage.py` |
| Syncthing integration | `src/syncthing.py` |
| Tests, mock RomM server and demo data | `tests/` |

Lines changed in files that came from the original project are listed in the git history
(`git log 1d08deb..` shows everything after the last upstream commit).

## ROM folders - from ROM Mapper

The *Frontend links* and *RomM library* pages are **[ROM Mapper](https://github.com/sireteanu/rom-mapper)**
by [sireteanu](https://github.com/sireteanu) (up to 1.0.14, its
[changelog](docs/history/rom-mapper-CHANGELOG.md)), moved here with its history:

| Was (rom-mapper) | Is (romm_tools) |
|---|---|
| `app/server.py`, `app/links.py`, `app/romm.py`, `app/romm_slugs.py` | `src/mapper/` (same names) |
| `app/static/index.html` | `src/mapper/static/index.html` |
| `tests/` | `tests/mapper/` |
| `docs/user-guide.md` | `docs/user-guide.md` (now covers both parts) |
| `README.md` | `docs/rom-folders.md` |

## romm_tools

Bringing the two together (sireteanu, MIT): one entry point and process (`romm_tools.py`), ROM
folders mounted into the save sync web server under `/roms/` (`src/web.py`), a shared menu, look and
password, the `SAVE_SYNC` / `ROM_FOLDERS` switches, ROM folders logging into the shared log, link
ownership for a root container (`src/mapper/links.py`), the platform picker using save sync's
platform catalog, and `tests/test_romm_tools.py`.

Added in romm_tools (sireteanu, MIT): the **Game names** page (`src/mapper/gamelists.py`, its routes
now in `src/mapper/names.py`, `RommClient.rename_rom` in `src/romm_client.py`, `tests/mapper/test_gamelists.py`).
Its matching of `gamelist.xml` entries to RomM's games follows how RomM's own gamelist metadata
source does it (`backend/handler/metadata/gamelist_handler.py` in `rommapp/romm`); it is written
anew, no RomM code is copied. The `gamelist.xml` format is EmulationStation's
([GAMELISTS.md](https://github.com/Aloshi/EmulationStation/blob/master/GAMELISTS.md)).

Added in romm_tools 2.0 (sireteanu, MIT):

| Area | Files |
|---|---|
| One RomM client for both parts (replaces amn-96's `src/romm_api_func.py`, whose request logic it grew from) | `src/romm_client.py` |
| romm_tools as a RomM device, pairing by code | `src/devices.py`, Settings page |
| Standalone emulators (DuckStation, PCSX2, Dolphin, PPSSPP) | `src/emusaves.py`, `tests/test_emusaves.py` |
| Devices page | `src/device_overview.py` |
| RetroArch Cloud Sync per system, emulator per system | `src/settings.py`, `src/sync_engine.py`, Platforms page |
| gamelist.xml through RomM | `src/mapper/romm.py` (`config.yml`), `src/mapper/names.py` (export) |
| One platform list, shared stylesheet, smaller modules, ROM folders on FastAPI | `src/platforms.py`, `src/web_static/common.css`, `src/sync_rules.py`, `src/sync_files.py`, `src/sync_errors.py`, `src/mapper/names.py` |

Added in romm_tools 2.1 (sireteanu, MIT):

| Area | Files |
|---|---|
| Grout and NextUI save names: one game's save under several names (`Game.srm`, `Game.gba.sav`, `Game.sav`), save names per system folder, Grout as a *Synced by* choice | `src/sync_files.py`, `src/sync_engine.py`, `src/settings.py`, `src/device_overview.py`, `tests/test_save_names.py` |
| Grouped menu, phone menu, getting-started list, Platforms options, Settings tabs | `src/web_static/common.js`, `src/web_static/index.html`, `src/mapper/static/index.html` |

The save name styles follow how NextUI names its saves (its *Save format* setting, see NextUI's
[Managing saves](https://nextui.loveretro.games/getting-started/managing-saves/)) and how
[Grout](https://grout.romm.app/usage/save-sync/) uploads them; no code from either is used.

The PPSSPP save name (`PSP-<folder>.zip`) and the parsing of `PARAM.SFO` titles follow RomM's own
RetroArch PSP handling (`backend/handler/sync/retroarch/psp.py` in `rommapp/romm`), so both name the
same folders the same way; the code is written anew, no RomM code is copied.

## Third-party

- The pages' colours, font stack, sizes and corner radii follow RomM's published design tokens (`frontend/src/v2/styles/tokens.css` in `rommapp/romm`) so they look at home next to RomM. Buttons, text fields, selects, checkboxes, tables and tags are styled to look like RomM's own components (`RBtn`, `RTextField`, `RSelect`, `RCheckbox`, `RTable`, `RTag` in `frontend/src/lib`): the CSS is written anew from their sizes, colours and effects, no RomM code is copied. RomM's logo and artwork are **not** used, and this project is not made by, affiliated with, or endorsed by the RomM project, in line with RomM's [brand guidelines](https://docs.romm.app/latest/About/Brand-Guidelines/).
- [RomM](https://github.com/rommapp/romm) - this tool talks to RomM's API and, at runtime, downloads RomM's public platform list and folder aliases from the `rommapp/romm` and `rommapp/docs` GitHub repositories. `src/mapper/romm_slugs.py` is a list of RomM's platform slugs and names taken from `rommapp/romm` (`platform_slugs.py` and its IGDB/LaunchBox/ScreenScraper tables). It doesn't bundle any other RomM code.
- Python packages listed in `requirements.txt` (requests, watchdog, loguru, PyYAML, python-dotenv, FastAPI, Uvicorn), each under its own license.
- The game names and artwork in `docs/screenshots/` and `tests/` are invented and procedurally generated by `tests/mock_romm.py`.
