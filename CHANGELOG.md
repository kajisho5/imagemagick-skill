# Changelog

Releases are cut automatically when a PR merges (see CONTRIBUTING.md, "Releasing"): the
version comes from the merged PRs' labels and a section is added below "Unreleased". Notes written
under "Unreleased" in a PR move into that release's section.

## Unreleased

- New: every tool takes `--timeout SECONDS` (default 300; MCP: `timeout`). It is one
  wall-clock budget for the whole run. ImageMagick now runs as the leader of its own
  process group, so when the budget runs out the whole group - delegates such as
  Ghostscript or ffmpeg included - is killed (POSIX `killpg`, Windows `taskkill /T`),
  an output file the run had started is removed, and the tool fails with
  `{"ok": false, "code": "timeout", "timeout": N}` and exit status 124. `batch` applies
  it per file. The contract declares `timeout` on every tool and adds
  `result_shapes.timeout`. The fixed 120 s per-command ceiling is gone.

## 0.7.2

_Automated release: version and notes generated from pull requests merged since 0.7.1._

- fix: provides[] in the contract (OS registry shape) (#28)
- ci: pin the ImageMagick 6 job to ubuntu-24.04; add ECOSYSTEM_ROADMAP.md (#27)
- ci: autolabel with release-drafter v7's autolabeler action; setup-node v7 (#23)
- chore(deps): Bump actions/checkout from 4 to 7 (#8)

## 0.7.1

_Automated release: version and notes generated from pull requests merged since 0.7.0._

- Fix: `doctor` reported HEIC as readable on a machine with only libheif's encoder plugin
  (x265) and no decoder (libde265). ImageMagick's format list says `rw+` either way, and
  every HEIC read then failed with "Unsupported codec". When the list says HEIC is
  writable, doctor now writes a 16x16 HEIC to a temporary folder and reads it back.
  `heic.read`, `heic.write` and `heic.usable` follow that result, and `heic.verified`
  reports it. The failing case names the package to install. The temporary folder is
  always removed.

- fix: doctor verifies HEIC by writing and reading back a tiny file (#22)

## 0.7.0

_Automated release: version and notes generated from pull requests merged since 0.6.2._

- New: ImageMagick 6 without a `magick` command (Debian/Ubuntu's apt package) is used
  directly: the tools run its `convert`, and `identify` for what `magick identify` did.
  No shim is needed any more. `doctor --json` reports `backends.magick.kind` as `"magick"`
  or `"imagemagick6"`. A `convert` that is not ImageMagick 6, and any `convert` on Windows,
  is never used. CI's Ubuntu job now runs the whole suite on IM6 with no `magick`
  command.
- Roadmap rows marked `| done | main |` get the version of the release that ships them
  (`bump_roadmap_md.py`).
(nothing yet)

- feat: use ImageMagick 6 directly when there is no magick command (#21)

## 0.6.2

_Automated release: version and notes generated from pull requests merged since 0.6.1._

- Fix: package metadata points at the renamed repository, `kajisho5/imagemagick-skill`
  (npm provenance rejects a `repository.url` that does not match the repository that
  builds the package). A CI test now pins `package.json` and `.claude-plugin/plugin.json`
  to `$GITHUB_REPOSITORY`, so the next rename fails CI instead of `npm publish`.
- Docs: `docs/roadmap.md` is now 100 numbered items (RM-001 ... RM-100), each `done`
  (with the release it shipped in), `planned` or `idea`, one line each; a test holds the
  numbering, states and release references.
- Docs: README rewritten in the shape of ffmpeg-skill's, with a 2x2 grid of demo GIFs,
  agent request examples, a tools table with the `sips` fallback for each tool, MCP and
  plugin-marketplace install, an ImageMagick 6 / 7 / sips compatibility table and the
  `magick` shim Ubuntu's ImageMagick 6 needs.
- `demos/build.py` rebuilds `docs/demos/*.gif`, `docs/demos.md` and `assets/logo.png`
  from inputs it draws itself. Every number on a frame is read from the `--json` result of
  the command shown with it. Development only.
- `.github/scripts/check_readme.py` runs every README command in a throwaway HOME against
  an `npm pack` tarball, including install -> doctor -> `--uninstall`.
- Tests: every tool is run for real and must leave its inputs byte-identical; every
  writing tool's `--dry-run` must create no file; the README must name every tool and
  show demo GIFs that exist.

- fix: point package metadata at the renamed kajisho5/imagemagick-skill (#20)
- docs: roadmap as 100 numbered items (#19)
- docs: rewrite README with reproducible demo GIFs (#18)

## 0.6.1

_Automated release: version and notes generated from pull requests merged since 0.6.0._

- Fix: `probe` reported `has_gps: false` for HEIC photos that carry GPS. ImageMagick 6
  attaches a HEIC's EXIF as a bare TIFF block and never parses it into `exif:*`
  properties, so the old `%[EXIF:GPSLatitude]` check missed it. GPS detection now reads
  the raw EXIF block itself (standard library only) for every format, and `strip`
  refuses (and removes) an output whose EXIF still has GPS or cannot be parsed.
- Fix: `package.json` / `.claude-plugin/plugin.json` point at the repository's current
  name, `kajisho5/image-skill` (renamed from `Image-skill`). npm provenance compares
  `repository.url` case-sensitively, so the old casing would have failed `npm publish`.

- fix: detect GPS in HEIC EXIF that ImageMagick 6 does not parse (#17)

## 0.6.0

_Automated release: version and notes generated from pull requests merged since 0.5.0._

- New: MCP server (`mcp/server.py`, standard library only), installed next to the
  skill and shipped in the npm package. Tools, descriptions and input schemas are
  generated from the contract; argument mapping back to argv too. Serves the
  `initialize` handshake (2024-11-05 - 2025-11-25) and 2026-07-28's per-request
  versioning with `server/discover`. `--list` / `--call` for shells. Config examples for
  Claude Code, Claude Desktop and Cursor in the README.

- feat: add a stdio MCP server generated from the contract (#16)

## 0.5.0

_Automated release: version and notes generated from pull requests merged since 0.4.0._

- New tools: `overlay.py` (logo or literal text - `%`, backslashes and a leading `@`
  escaped - at a position with margin/opacity; CJK text picks a CJK font or fails),
  `adjust.py` (explicit levels/brightness/contrast/saturation/blur/sharpen), `montage.py`
  (row/grid with a required background, gap, captions), `icons.py` (favicon.ico with
  16/32/48, PNG 32/192/512, apple-touch-icon 180, plus HTML and manifest entries; square
  source only, never upscales), `preset.py` (named sizes from `scripts/presets.json`, each
  with the platform documentation it comes from; no X/Twitter preset because X no longer
  documents one). `batch.py` runs all of them (`montage` once per folder, `icons` one
  folder per image).
- The release-drafter-era `bump-version.js` and `prepend-changelog.js` are removed: the
  label-driven pipeline cut 0.4.0 end to end (bump commit, tag, Release, CHANGELOG).

- feat: add overlay, adjust, montage, icons and preset tools (#15)

## 0.4.0

_Automated release: version and notes generated from pull requests merged since 0.3.0._

- New tools: `look.py` (labelled preview sheet / before-after pair for the agent to
  open), `compare.py` (SSIM, PSNR, changed-pixel share, optional heatmap, `--fail-below`
  gate), `optimize.py` (fit a `--max-kb` budget by quality search, same dimensions, fails
  with the smallest size reached), `crop.py` (exact rectangle or aspect ratio by gravity,
  never clips), `pad.py` (aspect or canvas with a required colour, transparency-aware,
  never shrinks), `rotate.py` (rotate, flip, or bake EXIF orientation). sips covers
  centred crop/pad, single 90-degree rotations or flips, and JPEG/HEIC optimize.
- `batch.py` runs the new per-file tools, makes one `look` sheet per folder, and pairs
  files for `compare` with `--against DIR`.
- `doctor --json` reports the fonts labels and text would use (`fonts.default`,
  `fonts.cjk`).
- Release automation moved to label-driven `resolve_version.py` (same design as
  ffmpeg-skill): no release for chore/ci/docs/test-only merges, no automatic major,
  `package.json` / `.claude-plugin/plugin.json` / `docs/contract.md` / `docs/roadmap.md`
  bumped together, npm publish with provenance when `NPM_TOKEN` is set.
- The contract derives every tool's `input_schema` from its own argparse parser and adds
  `id`, `role`, `backends`, `requires_magick`, `supports_json`, `supports_dry_run`,
  `mutates_input`, `verify`, `output_schema`, plus top-level `contract_version`, `skill`,
  `execution` and `result_shapes`. Every existing key is unchanged.
- New: `docs/contract.md` (tools section generated from the contract and checked in CI),
  `docs/design-decisions.md`, `docs/roadmap.md`, `.claude-plugin/plugin.json` and
  `marketplace.json`, `AGENTS.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `evals/agent_prompts.json`.
- `package.json`'s `repository.url` uses the repository's real casing (`Image-skill`):
  npm provenance compares it case-sensitively.

- feat: add look, compare, optimize, crop, pad and rotate tools (#14)
- chore: align repo structure and release automation with ffmpeg-skill (#13)

## 0.3.0

- **Renamed to `imagemagick-skill`.** The npm name `image-skill` belongs to an unrelated
  package by another author, so `npx image-skill` never installed this skill. Install with
  `npx imagemagick-skill`; the skill directory is now `imagemagick-skill`.
- Installing or uninstalling removes an old `image-skill` copy next to the target only when
  its contents prove it came from this repository (SKILL.md name, file layout, the
  `_contract.py` marker every release carried, `package.json` repository). Anything else is
  left in place with a warning that says why.
- `--codex` installs to `~/.agents/skills/imagemagick-skill`, where Codex reads user skills;
  0.2.x's `~/.codex/skills` copy was never seen by Codex and is migrated away.
- CI installs the packed tarball through `npx` (install, doctor, uninstall) on every PR.

## 0.2.2

- The PR autolabeler no longer applies `breaking` from a title pattern: a major bump only
  happens when a person applies the label (#11).

## 0.2.1

- Release workflow fix (#10). Correction recorded in 0.3.0's PR: release-drafter v6 has no
  `dry-run` input; the change made it run live, which left a stray draft release.

## 0.2.0

- **Breaking:** `bin/cli.js` replaced by `bin/install.js` with a new install
  UX: default target is now global (`~/.claude/skills/image-skill`), plus
  `--cursor`, `--codex`, `--all`, `--dir <parent>`, `--project`, and
  `--uninstall`. Writing `.cursor/rules/*.mdc` and appending to `AGENTS.md`
  is removed entirely in favor of real `~/.cursor/skills/` and
  `~/.codex/skills/` copies. Reinstalling now wipes the target directory
  first so no stale scripts survive an upgrade. A missing backend prints a
  warning with the same install guidance as the README.
- Fixed `resize.py`'s sips `fit` mode: it used to size only by the longer
  edge (`sips -Z`), which could overflow the other dimension on a
  non-square box. It now computes the proportional box-fit size itself and
  asks sips for that exact size, matching magick's guarantee that neither
  dimension exceeds the requested box.
- Fixed a design gap present since the initial release: a malformed
  invocation (missing/invalid flags) used to bypass the `ok:false`/`--json`
  contract entirely, printing argparse's raw usage text and exiting 2. All
  scripts (including `batch.py`'s per-file re-use of another tool's parser)
  now report this the same way as any other failure - and a bad per-file
  argument in a batch run is recorded as that one file failing instead of
  aborting the whole batch.
- `_contract.py`'s reported `version` now reads `package.json` instead of a
  second hardcoded version string, so the two can no longer drift apart.
- Doc fixes: `SKILL.md` no longer claims `check.py` supports `--dry-run`
  (it doesn't - it writes nothing).
- Added GitHub Actions CI (`.github/workflows/test.yml`): the test suite now
  runs on every push/PR against Ubuntu with and without ImageMagick, and on
  macOS - the first time the sips-only code paths have actually executed
  anywhere rather than being validated by arithmetic/mocking alone. A
  separate job exercises every `bin/install.js` target end to end.
- Fixed a real, verified correctness bug found by testing against an actual
  HEIC photo: when the local `magick` build has no *encode* delegate for a
  target format (e.g. HEIC read-only, no libheif encoder), `magick` can exit
  0 while silently writing the *input* format's bytes under the requested
  output name - a single stderr warning, no error. `convert`/`resize`/
  `thumb`/`strip`/`trim` now verify the output's actual format matches its
  extension right after writing it, and remove + fail (`ok:false`) instead of
  reporting success for a mislabeled file.
- `doctor`'s `heic`/`webp` fields now parse ImageMagick's actual read/write
  mode flags (e.g. `r--` vs `rw+`) instead of just checking whether the
  format's name appears in `magick -list format` at all - the previous check
  couldn't tell a read-only HEIC delegate from a fully working one. Both now
  report `read`/`write` explicitly, with `fix` guidance when write is
  missing.
- New tests: a real downloaded HEIC sample (not committed - see below) was
  run through the full probe/convert/resize/thumb/strip/check pipeline by
  hand to find the bug above; a dynamically-generated HEIC round-trip test
  (`tests/test_heic_roundtrip.py`) now runs automatically wherever a real
  backend can write HEIC (e.g. macOS `sips` in CI), skipping everywhere else
  - no binary fixture is committed to the repo.

## 0.1.0

Initial release.

- `probe`, `convert`, `resize`, `thumb`, `strip`, `trim`, `check`, `batch`
- `_contract.py` with `contract` (machine-readable tool spec) and `doctor`
  (environment check) subcommands
- ImageMagick (`magick`) as the primary backend; macOS `sips` as a partial
  fallback for `convert`/`resize`/`thumb`
- `npx image-skill` installer for Claude Code, Cursor, and Codex
- unittest suite covering overwrite protection, fit-resize aspect ratio,
  GPS stripping, border trim, and doctor's no-backend/sips-only cases
