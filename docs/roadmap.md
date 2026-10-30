# Roadmap

The released version today is **0.8.0** (notes in CHANGELOG.md); **0.6.1** — GPS detection reads the raw EXIF block (HEIC
included, which ImageMagick 6 never parses), and `strip` refuses an output that may
still carry GPS.

"On the roadmap" does not mean "in the released package". `docs/contract.md` and
`contract --json` are the authority on what exists today. Every item below has one
state:

- **done** — merged. The *Since* column names the release it shipped in, or `main`
  when it is merged but not released yet; the release automation replaces `main` with the
  version it cuts.
- **planned** — agreed to be in scope. Not started, or started on a branch only.
- **idea** — worth writing down. Not decided, and it may conflict with a design rule
  (no network, standard library only, the user decides every value); that has to be
  settled before it becomes planned.

Item IDs never change and are never reused. A dropped item stays in the table as
`idea` with the reason given.

| ID | State | Since | Item |
| --- | --- | --- | --- |
| RM-001 | done | 0.1.0 | `probe`: width, height, format, colorspace, alpha and GPS presence as JSON |
| RM-002 | done | 0.1.0 | `convert` between formats (HEIC→JPEG/PNG/WebP, …), input never touched |
| RM-003 | done | 0.1.0 | `resize` with `fit` / `fill` / `exact`, sizes always given by the caller |
| RM-004 | done | 0.1.0 | `thumb` by the long edge, never upscales |
| RM-005 | done | 0.1.0 | `strip` GPS/EXIF, baking EXIF orientation into the pixels first |
| RM-006 | done | 0.1.0 | `trim` a solid border, refusing to trim the whole image away |
| RM-007 | done | 0.1.0 | `check`: output opens, matches promised size/format, is not the input |
| RM-008 | done | 0.1.0 | `batch` a tool over every image in a folder |
| RM-009 | done | 0.1.0 | `contract --json` and `doctor` |
| RM-010 | done | 0.1.0 | macOS `sips` fallback for convert / resize / thumb / probe / check |
| RM-011 | done | 0.2.0 | Installer targets: Claude Code, `--cursor`, `--codex`, `--all`, `--dir`, `--project`, `--uninstall` |
| RM-012 | done | 0.2.0 | Malformed flags return `ok:false` JSON like every other failure, also inside `batch` |
| RM-013 | done | 0.2.0 | Output format read back after writing; a build that writes the wrong bytes is caught |
| RM-014 | done | 0.2.0 | `doctor` reports HEIC/WebP read and write separately from ImageMagick's mode flags |
| RM-015 | done | 0.2.0 | `sips` fit mode bounded by both dimensions |
| RM-016 | done | 0.2.0 | CI on Ubuntu (with and without ImageMagick) and macOS (`sips`) |
| RM-017 | done | 0.2.2 | The PR autolabeler never applies `major`/`breaking` from title or body text |
| RM-018 | done | 0.3.0 | npm package renamed to `imagemagick-skill` (`image-skill` belongs to another author) |
| RM-019 | done | 0.3.0 | Old `image-skill` installs removed only when provably this project's; anything else warned about and kept |
| RM-020 | done | 0.3.0 | `--codex` installs to `~/.agents/skills`, where Codex reads user skills |
| RM-021 | done | 0.3.0 | CI installs the packed tarball through `npx` and runs doctor and `--uninstall` |
| RM-022 | done | 0.4.0 | Label-driven releases: version, CHANGELOG, tag, GitHub Release, npm; major refused |
| RM-023 | done | 0.4.0 | Every tool's `input_schema` derived from its own argparse parser |
| RM-024 | done | 0.4.0 | `docs/contract.md` tools section generated from the contract and drift-checked in CI |
| RM-025 | done | 0.4.0 | Claude Code plugin manifest; the repository is its own plugin marketplace |
| RM-026 | done | 0.4.0 | Agent eval prompts (`evals/`), 39 prompts incl. refusals and Japanese |
| RM-027 | done | 0.4.0 | `docs/design-decisions.md`, every entry citing the test that pins it |
| RM-028 | done | 0.4.0 | AGENTS.md, CONTRIBUTING.md and CODE_OF_CONDUCT.md |
| RM-029 | done | 0.4.0 | `look`: labelled preview sheet or before/after pair for the agent to open |
| RM-030 | done | 0.4.0 | `compare`: pure-Python SSIM (matches scikit-image), PSNR, changed pixels, heatmap, `--fail-below` |
| RM-031 | done | 0.4.0 | `optimize` to a `--max-kb` budget at the same size; fails with the smallest size reached |
| RM-032 | done | 0.4.0 | `crop` to a rectangle or an aspect ratio by gravity; never clips silently |
| RM-033 | done | 0.4.0 | `pad` to an aspect or canvas with a required colour (or transparency) |
| RM-034 | done | 0.4.0 | `rotate`: clockwise degrees, mirror, or bake EXIF orientation |
| RM-035 | done | 0.4.0 | `doctor` reports the fonts labels and text would use (Latin and CJK) |
| RM-036 | done | 0.5.0 | `overlay` a logo, or literal text (`%`, `\` and a leading `@` cannot reach ImageMagick escapes) |
| RM-037 | done | 0.5.0 | `adjust` with explicit levels / brightness / contrast / saturation / blur / sharpen, no "auto" |
| RM-038 | done | 0.5.0 | `montage` row or grid with an explicit background, gap and labels |
| RM-039 | done | 0.5.0 | `icons`: favicon.ico, PNG icons, apple-touch-icon, plus `<link>` and manifest entries |
| RM-040 | done | 0.5.0 | `preset`: named published sizes, each with its source URL and a quote |
| RM-041 | done | 0.5.0 | `batch` runs per-file tools, `look`/`montage` sheets, `icons` folders and `compare --against` pairs |
| RM-042 | done | 0.6.0 | stdio MCP server generated from the contract, legacy and 2026-07-28 protocol eras |
| RM-043 | done | 0.6.1 | GPS detection from the raw EXIF block, including HEIC on ImageMagick 6 |
| RM-044 | done | 0.6.1 | `strip` deletes and fails an output that still has, or may have, GPS |
| RM-045 | done | 0.6.1 | Package metadata follows the renamed `kajisho5/image-skill` (npm provenance is case-sensitive) |
| RM-046 | done | 0.6.2 | README with reproducible demo GIFs (`demos/build.py`) and a command-checked README (`check_readme.py`) |
| RM-047 | done | 0.6.2 | Tests: every tool leaves its inputs byte-identical; `--dry-run` never creates a file |
| RM-048 | done | 0.7.0 | ImageMagick 6 (`convert`/`identify`, Debian/Ubuntu apt) used directly, no `magick` shim needed |
| RM-049 | done | 0.7.1 | `doctor` proves HEIC read and write with a real round-trip (an encoder-only libheif passes the mode flags) |
| RM-050 | done | 0.6.2 | Published to npm with provenance (`NPM_TOKEN` secret; repository renamed to `kajisho5/imagemagick-skill`) |
| RM-051 | planned | | Windows CI job with ImageMagick 7 |
| RM-052 | planned | | `doctor` field for AVIF read/write, and AVIF in `convert`/`optimize` where the build has it |
| RM-053 | planned | | `probe` reports the EXIF orientation value and pixel density |
| RM-054 | planned | | `probe` reports whether an ICC profile is embedded (report only, no colour management) |
| RM-055 | planned | | `check --expect-max-kb` to verify a file-size budget |
| RM-056 | planned | | `check --expect-no-gps` so the privacy promise is verified in the same call |
| RM-057 | planned | | `look` labels show the file size next to dimensions and format |
| RM-058 | planned | | `compare --region` to limit the comparison to a rectangle |
| RM-059 | planned | | `compare` reports the bounding box of the changed area |
| RM-060 | planned | | `optimize` reports the SSIM of the chosen encode against the original |
| RM-061 | planned | | `optimize --palette N` for PNG, an explicit colour count, never chosen automatically |
| RM-062 | planned | | `preset`: an X (Twitter) card size once an official source can be cited (omitted today) |
| RM-063 | planned | | `preset`: more platform sizes, each added only with an official source |
| RM-064 | planned | | `icons`: maskable PWA icon with an explicit safe-zone padding argument |
| RM-065 | planned | | `icons --write-manifest` writes `site.webmanifest` next to the icons |
| RM-066 | planned | | `overlay`: several lines of text, each passed explicitly |
| RM-067 | planned | | `overlay`: a text background box with an explicit colour and padding |
| RM-068 | planned | | `batch --jobs N` to process files in parallel |
| RM-069 | planned | | `batch` content-hash cache to skip unchanged inputs |
| RM-070 | done | 0.8.0 | `--timeout` for every tool so a hung ImageMagick is killed and reported |
| RM-071 | planned | | `doctor` reports ImageMagick `policy.xml` limits (memory, disk, blocked coders) |
| RM-072 | planned | | MCP `prompts`: canned recipes (OG image, favicon set, privacy strip) naming real tool calls |
| RM-073 | planned | | Contract fields `mutates_input: false` and an idempotency hint per tool |
| RM-074 | planned | | Stability guarantee in `docs/contract.md` with an argument-name snapshot test |
| RM-075 | planned | | Eval runs recorded per iteration in `evals/results/`, graded against `evals/agent_prompts.json` |
| RM-076 | planned | | `references/scripts.md` per-flag reference generated from the contract |
| RM-077 | planned | | SKILL.md two-tier split into `references/` before it nears the 30 KB budget |
| RM-078 | planned | | SECURITY.md with a private reporting channel |
| RM-079 | planned | | GitHub Actions moved off Node 20 (checkout, setup-python), Dependabot PRs merged |
| RM-080 | planned | | `check_readme.py` in CI (heif-enc installed, `claude` steps skipped when absent) |
| RM-081 | planned | | More demos in `docs/demos.md`: crop, pad, overlay, montage, adjust, trim |
| RM-082 | planned | | `--json-brief` output trimmed to what a caller acts on |
| RM-083 | planned | | README "Tested on real files" table, from a real-device corpus run by hand |
| RM-084 | planned | | `strip --keep` for an explicit list of tags to keep (e.g. copyright), everything else removed |
| RM-085 | idea | | Rasterise the first page of a PDF at an explicit DPI (ImageMagick policy often blocks PDF) |
| RM-086 | idea | | Rasterise an SVG at an explicit size |
| RM-087 | idea | | Perceptual-hash duplicate finder for a folder (report only) |
| RM-088 | idea | | Screenshot regression recipe: `compare --fail-below` as a CI gate, documented end to end |
| RM-089 | idea | | Dominant colours report (analysis only; the agent still does not choose colours) |
| RM-090 | idea | | Text contrast ratio report for `overlay` (WCAG), with no automatic colour change |
| RM-091 | idea | | Vertical Japanese text in `overlay` |
| RM-092 | idea | | A GitHub Action wrapping `check`/`optimize` for repositories |
| RM-093 | idea | | pre-commit hook that refuses images carrying GPS |
| RM-094 | idea | | Docker image with ImageMagick 7 and HEIC for reproducible runs |
| RM-095 | idea | | Japanese trigger phrases in SKILL.md's description, measured with the evals first |
| RM-096 | idea | | `sips` fallback for `strip`, only if `sips` can be shown to remove GPS completely |
| RM-097 | idea | | WebAssembly ImageMagick when no binary exists (conflicts with "no runtime dependency") |
| RM-098 | idea | | Contact sheet labels from EXIF capture date (read only) |
| RM-099 | idea | | Animated GIF/WebP input kept as its first frame with a warning in `probe` (animation stays out of scope) |
| RM-100 | idea | | Cross-skill recipe with ffmpeg-skill: a video still from ffmpeg-skill, then `preset`/`optimize` here |
