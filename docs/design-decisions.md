# Deliberate behaviours (read before filing a bug)

This file lists behaviours that look like defects on a first read but are decisions,
with the reason and the test that pins each one. If one of them is wrong for your case,
say which sentence here no longer holds.

## Outputs and files

- **`-o/--output` is required and must differ from the input.** No tool has an
  "in place" mode, and `mogrify` (ImageMagick's in-place editor) is never called. An
  agent that overwrote a user's only copy of a photo cannot undo it.
  Code: `_common.check_output_not_input()`. Tests: `test_convert_rejects_same_path`,
  `test_resize_rejects_same_path`.

- **An existing output is refused unless `--overwrite` is passed.** Silently replacing a
  file from an earlier run hides mistakes; the refusal happens before anything runs.
  Code: `_common.check_output_not_exists()`. Test:
  `test_convert_rejects_existing_output_without_overwrite_flag`.

- **A written file whose real format differs from its extension is deleted and reported
  as `ok: false`.** ImageMagick exits 0 and only warns on stderr when it has no encoder
  for the requested format (e.g. HEIC read-only builds), writing the *input's* format
  under the new name. Keeping that file would report success for a mislabeled image.
  Code: `_common.verify_output_format()`. Test: `test_flags_a_silently_wrong_format`.

- **`trim` deletes its result and fails when more than `--max-trim-percent` (90%) of the
  area would go.** A uniform or near-uniform image trims to a sliver; that means the
  input was not "an image with a border", and `--fuzz` is the knob to adjust.
  Code: `trim.run_trim()`. Test: `test_refuses_over_trim_on_solid_image`.

- **`crop` refuses a rectangle that reaches outside the image** instead of clipping it.
  A silently smaller crop breaks whatever layout the caller computed.
  Test: `test_crop_never_clips`.

- **`pad` never shrinks and has no default colour.** A canvas smaller than the image is
  refused (resize first); the fill is a visual choice, so `--color` is required, and a
  transparent fill into JPEG is refused because JPEG has no alpha.
  Tests: `test_pad_never_shrinks_and_needs_a_color`,
  `test_pad_transparent_stays_transparent_and_is_refused_for_jpeg`.

- **`optimize` never changes dimensions, and writes nothing when the budget cannot be
  met** - it reports the smallest size it reached instead. Shrinking pixels is a separate,
  visible decision (`resize`). Test:
  `test_unreachable_budget_fails_with_smallest_size_and_writes_nothing`.

- **`optimize` falls back to `webp:target-size` for WebP when `-quality` has no effect.**
  Ubuntu 24.04's ImageMagick 6.9.12 writes the same WebP bytes at every quality; a
  quality search there would "succeed" at a meaningless number. `method` says which path
  was used. Tests: `test_quality_that_changes_nothing_switches_to_target_size`,
  `test_webp_fits_by_quality_or_target_size`.

- **`overlay` refuses an overlay larger than the base image** rather than cropping it,
  and never changes the base image's size. Test: `test_overlay_larger_than_base_is_refused`.

- **`icons` needs a square source at least as large as the largest icon.** Non-square
  sources would be distorted or cropped by a guess; small ones would be upscaled into blur.
  Test: `test_icons_refuse_non_square_and_upscaling`.

## Pixels

- **Every writing tool bakes EXIF orientation into the pixels (`-auto-orient`).** A
  phone photo stored sideways with an Orientation tag would otherwise come out sideways
  as soon as the tag is lost - `strip` removes it, and many web/OG consumers ignore it.
  Test: `test_exif_orientation_is_baked_into_the_pixels`.

- **`thumb` never upscales.** A thumbnail larger than its source is not a thumbnail;
  `--long-edge` is a ceiling (`-resize NxN>`). Test: `test_thumb_never_upscales`.

- **The skill never picks a size.** `resize --width/--height` and `thumb --long-edge` are
  required with no default: dimensions come from the user or the task, never from the
  skill's taste (SKILL.md rule 4). Test: `test_sizes_are_never_defaulted`.

- **`rotate` by an angle that is not a multiple of 90 needs `--background`.** The new
  corners must be filled with something, and choosing it is the caller's call.
  Test: `test_free_angle_needs_background`.

- **`compare` computes SSIM itself, after downsampling.** ImageMagick 6 has no SSIM
  metric and 7's differs by version; the Python implementation (Rec. 601 luma, 7x7
  window, scikit-image's constants) gives the same number everywhere, after Wang et al.'s
  recommended downsampling to a ~256-pixel shorter side (`ssim_scale`). Changed pixels
  and PSNR are measured at full resolution. Alpha is flattened onto white, and images of
  different sizes are refused rather than resampled. Tests:
  `test_identical_is_one`, `test_counts_changed_pixels_exactly`,
  `test_size_mismatch_is_refused`.

- **Text given to ImageMagick is escaped.** `label:` text expands `%` escapes and
  backslashes, and text starting with `@` is read from a *file* - so a caption
  "@kajisho5" would otherwise read a file named kajisho5. Test:
  `test_leading_at_is_text_not_a_file`.

- **`adjust` has no "auto" or "enhance"**, and every value is range-checked. How an
  image should look is the caller's decision; the skill only applies numbers it was given.
  Test: `test_adjust_needs_an_operation_and_valid_ranges`.

- **Every `preset.py` size cites the platform's own documentation, and a platform without
  a current official size gets no preset** (X/Twitter's docs no longer state one). A size
  from a blog post is a guess with a URL. `--mode` has no default. Tests:
  `test_every_preset_cites_a_source`, `test_no_preset_without_an_official_source`.

- **Japanese/Chinese/Korean text needs a CJK font, or `overlay` fails.** A Latin-only
  font renders those characters as empty boxes, which would otherwise be reported as
  success. Test: `test_japanese_text_picks_a_cjk_font`.

- **`look` has defaults (tile size, columns) where editing tools have none.** Its sheet
  is for the agent to inspect, never a deliverable. Test:
  `test_grid_has_the_promised_size_and_leaves_inputs_alone`.

- **GPS is detected by parsing the EXIF block, not by asking ImageMagick.** ImageMagick 6
  attaches a HEIC photo's EXIF as a bare TIFF block and never turns it into `exif:*`
  properties, so `%[EXIF:GPSLatitude]` said "no GPS" for a HEIC that had coordinates. The
  tool reads the raw block (`exif:-`) and walks the TIFF/GPS IFD itself; a block it cannot
  parse is `null` (unknown), never `false`, and `strip` fails unless the result is provably
  GPS-free. Tests: `test_every_layout_imagemagick_emits`,
  `test_unparseable_is_unknown_not_false`, `test_heic_with_gps_is_detected_and_stripped`.

## Arguments and results

- **A tool that runs out of `--timeout` kills ImageMagick's whole process group and
  fails with `"code": "timeout"`, exit 124** (RM-070). ImageMagick hands PDFs, EPS, SVG
  and video frames to delegates (Ghostscript, ffmpeg, Inkscape) that it starts as
  children; killing only `magick` would leave them running, so every command starts as
  the leader of a new process group (POSIX `start_new_session`; Windows
  `CREATE_NEW_PROCESS_GROUP`) and a timeout kills the group (`os.killpg(SIGKILL)`;
  Windows `taskkill /T /F`, which walks the tree), then reaps it before answering.
  SIGKILL without a SIGTERM first: the only thing a killed command could flush is the
  output, and a half-written output is deleted anyway. The budget is one wall-clock
  allowance per run, not per command (`optimize` encodes many times; the caller cares
  how long the tool takes); a nested budget never extends an enclosing one. The default
  is 300 s: generous for any still image (the old fixed ceiling was 120 s per command,
  now replaced), short enough that a hung delegate does not stall an agent session
  indefinitely. Exit 124 is GNU `timeout`'s status and hyperframes-skill's; `code` is
  the first failure code in this repository's `ok:false` shape, so every other failure
  keeps exit 1 and no `code`. `batch` gives each file its own budget, because one hung
  file should cost that file, not the folder (same reasoning as "batch keeps going").
  A SIGTERM to the tool itself (an MCP client giving up) kills the running group too,
  and the MCP server sends SIGTERM before SIGKILL for that reason. Same pattern as
  qc-skill ADR-019 and hyperframes-skill `lib/proc.mjs`. Tests:
  `test_timed_out_run_fails_with_the_timeout_code_and_leaves_no_child`,
  `test_batch_records_the_timeout_per_file_and_kills_each_run`,
  `test_nested_budget_never_extends_the_outer_one`.

- **A malformed invocation still answers with `ok: false` JSON under `--json`**, exit 1,
  instead of argparse's usage text and exit 2. Agents parse one shape for every failure.
  Code: `_common.JSONArgumentParser.error()`. Tests:
  `test_missing_required_flags_with_json_emits_ok_false_json`,
  `test_contract_cli_invalid_subcommand_emits_ok_false_json`.

- **`check` has no `--dry-run`.** It only reads; there is nothing to preview.
  Test: `test_check_has_no_dry_run_because_it_writes_nothing`.

- **`batch` keeps going after a file fails** and reports `all_ok: false` with a per-file
  `reason`, including a bad per-file argument. One corrupt photo should not cost the rest
  of the folder. Test: `test_per_file_argparse_error_is_recorded_not_fatal`.

## Backends

- **`strip` and `trim` have no `sips` path.** `sips` has no reliable blanket
  metadata-strip flag and no border detection; a partial strip that leaves GPS behind is
  worse than a clear "needs ImageMagick". Test:
  `test_doctor_sips_only_marks_strip_and_trim_unusable`.

- **`doctor` calls read-only HEIC "usable" but reports `write: false` with a fix.** The
  documented workflow reads HEIC (iPhone photos in) and writes something else; creating
  HEIC is reported separately so nobody assumes it. Test:
  `test_doctor_reports_heic_write_false_when_read_only`.

- **Windows CI runs ImageMagick 7's `magick.exe` only, from Chocolatey.** That is the
  official installer, the way a Windows user gets ImageMagick; there is no ImageMagick 6
  path to test there, because `convert.exe` on Windows is the system's disk-conversion
  tool and is never used. The job runs the whole suite with no Windows-only skips added,
  under Git Bash and setup-python's `python` (Windows has no reliable `python3`), and
  fails unless `magick -version` says ImageMagick 7 and `doctor` reports kind `magick`.
  Job: `windows-imagemagick7` in `.github/workflows/test.yml`. Test:
  `test_windows_convert_exe_is_never_used`.

## MCP

- **The MCP server has no tool table.** Everything it lists is generated from the
  contract at start-up, and arguments are mapped back to argv by the contract, so adding
  a flag to a script changes the MCP tool with no second edit. Test:
  `test_contract_docs_and_mcp_agree`.

- **It serves both protocol eras.** Clients in use today open with `initialize`; the
  2026-07-28 revision drops that handshake for per-request versions and
  `server/discover`. A legacy-only server would fail modern clients and a modern-only one
  would fail today's. Tests: `test_initialize_then_list`,
  `test_discover_and_per_request_version`, `test_unsupported_version_error`.

- **An unknown argument is a tool error, not a protocol error.** The model sees what was
  wrong and can retry; an unknown tool is a JSON-RPC error. Test:
  `test_unknown_argument_is_a_tool_error_the_model_can_fix`.

## Installing

- **`--codex` installs to `~/.agents/skills`, not `~/.codex/skills`.** That is where
  Codex reads user skills. Test: `test_codex_installs_where_codex_reads_user_skills`.

- **An old `image-skill` directory is removed only when it is provably this project's.**
  The npm name `image-skill` belongs to another author; a directory with that name may be
  theirs. Anything not matching the exact layout and markers is left with a warning.
  Tests: `test_own_legacy_install_is_removed`,
  `test_foreign_image_skill_is_left_alone_with_a_warning`,
  `test_own_layout_with_extra_user_file_is_left_alone`.

## Releasing

- **No release is ever cut for a major version automatically.** `major`/`breaking` labels
  make version resolution fail, and the bump step refuses to cross a major boundary. A
  major release is a hand-made `package.json` bump in a PR. Tests:
  `test_major_is_refused`, `test_major_crossing_is_refused_and_writes_nothing`.

- **A merge of only chore/ci/docs/test/refactor/dependency PRs releases nothing.**
  A version number should mean the shipped package changed. Test:
  `test_nothing_releasable`.
