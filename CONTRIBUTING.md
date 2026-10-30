# Contributing to imagemagick-skill

Thanks for considering a contribution. This project has one job: execute explicit,
agent-given image operations deterministically, safely and verifiably, with ImageMagick
(or macOS `sips`) on the user's own machine. Read `SKILL.md`'s rules before proposing
anything - they define the boundary this project holds deliberately.

## Before you start

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).

- **Read `docs/contract.md` and `scripts/_contract.py` first.** The contract
  (`contract --json`) is the single source of truth for tool schemas. Argument schemas are
  derived from each script's `build_parser()`; everything else a tool promises (role,
  backends, output keys) lives in `TOOL_META`. Don't hand-duplicate a schema anywhere.
- **Read `docs/design-decisions.md`** before "fixing" something that looks wrong.
- **Every change needs a reproduction.** For a bug, show the failing case before the fix
  and the passing case after, as a test.

## Scope

This project intentionally does **not**:

- edit video, GIF animation or extract frames (use a video skill such as ffmpeg-skill)
- do face recognition, AI background removal, generative/AI editing, RAW development or
  print ICC work
- call the network, need an API key, or add a pip/npm runtime dependency
- write to an input file, or call `mogrify`
- choose sizes, crops, colours or "what looks good" for the caller: every value is an
  argument

## Development

```bash
git clone https://github.com/kajisho5/imagemagick-skill
cd imagemagick-skill
npm test                                      # python3 -m unittest discover -s tests -v
python3 scripts/_contract.py doctor --json    # what this machine can run
python3 .github/scripts/contract_md.py --check
node bin/install.js --dir /tmp/skills         # try the installer without touching ~/.claude
```

Python 3.9+ standard library only. Tests that need ImageMagick or `sips` skip themselves
when the binary is missing; CI runs them on Ubuntu (with and without ImageMagick), on
macOS (with `sips`, and with Homebrew's ImageMagick 7) and on Windows (ImageMagick 7).

## Adding or changing a tool

A tool is `scripts/<name>.py` with `build_parser()` (a `JSONArgumentParser`),
`run_<name>(args)` returning a dict, and `main()`. It must:

- require `-o/--output` when it writes, refuse the input path and an existing output
  (unless `--overwrite`), and support `--json` and `--dry-run`
- verify what it wrote (`verify_output_format`, plus dimensions when it promised any)
  and report a broken result as `ok: false`
- have a `TOOL_META` entry (`description`, `role`, `backends`, `verify`,
  `output_schema`, `output_required`); `tests/test_contract.py` fails otherwise and holds
  the tool's real `--json` output to that schema
- have tests that skip cleanly without a backend

Then regenerate the contract page with `python3 .github/scripts/contract_md.py --write`
and update `SKILL.md`, `README.md` and `CHANGELOG.md` ("Unreleased").

## Demos and README commands

```bash
python3 demos/build.py                 # rebuild docs/demos/*.gif, docs/demos.md, assets/logo.png
python3 .github/scripts/check_readme.py
```

`demos/build.py` draws its own inputs, a synthetic landscape and a synthetic logo. Never
add a photograph, a person or anyone else's artwork to it. Every number on a frame must
come from the `--json` result of the command shown with it. It needs ImageMagick, plus
`heif-enc` (libheif-examples) or a HEIC-writing ImageMagick. The skill itself must never
depend on either, or on ffmpeg.

`check_readme.py` runs every ```bash block in `README.md`, in order, in a throwaway HOME.
`npx imagemagick-skill` points at an `npm pack` tarball of the checkout. Run it after
changing a README command, and paste its summary into the PR.

## Pull requests

- Keep PRs focused - one fix or one small feature per PR - and explain *why*.
- Run `npm test` locally before opening; CI must be green.
- Titles follow Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `ci:`,
  `test:`, `refactor:`). The PR labeler turns them into labels, and labels decide the
  release (below). Adjust the label by hand if the title's type is wrong.

## Releasing

Releases are automatic: a PR does not need to touch `package.json`, `docs/contract.md` or
`CHANGELOG.md`'s version sections. When a PR merges, `.github/workflows/release.yml`:

1. resolves the next version with `.github/scripts/resolve_version.py` from the labels of
   every PR merged since the last `vX.Y.Z` tag - `feature`/`minor`/`enhancement` → minor,
   `fix`/`patch`/`bug` → patch, unlabeled → patch, only `chore`/`ci`/`docs`/`test`/
   `refactor`/`dependencies` → **no release**, `major`/`breaking` → **refused**;
2. bumps `package.json`, `.claude-plugin/plugin.json`, `docs/contract.md` and the
   "released version today" sentence in `docs/roadmap.md`, moves `CHANGELOG.md`'s
   "Unreleased" notes into a new section with the merged PR titles, and pushes that
   commit to `main`;
3. tags `vX.Y.Z`, publishes a GitHub Release with that CHANGELOG section, and publishes
   to npm with provenance when the `NPM_TOKEN` secret exists (without it, only the npm
   step is skipped).

A PR may bump `package.json` by hand and write its own CHANGELOG section instead; that
version is then used as-is. A **major** version is only ever such a hand-made bump.

## Reporting issues

Include the exact command, actual vs. expected output, and
`python3 scripts/_contract.py doctor --json`. Security issues go through
[SECURITY.md](SECURITY.md), not a public issue.
