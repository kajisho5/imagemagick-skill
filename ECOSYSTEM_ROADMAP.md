# Roadmap — imagemagick-skill

Part of the [AI Video Production OS](https://github.com/kajisho5/AI-video-production-OS/blob/main/docs/ecosystem/ROADMAP.md) ecosystem: department **補助 (Utility)**, status `active`.
Written from a read-only audit of this repository on 2026-10-30. Each step below is meant to be one pull request; tick it off by linking the PR.

## Where it stands

v0.8.1. 19 tools (probe, convert, resize, thumb, strip, trim, check, look, compare, optimize, crop, pad, rotate, adjust, overlay, montage, icons, preset, batch); npm installer + MCP. 173 tests; CI on Ubuntu (no IM / IM6), macOS (sips / IM7) and Windows with IM7 (step 2); SkillPact L2 on every PR.

## What this repository owns

`ecosystem.json` gives each job to exactly one repository. Work outside this list belongs to its owner and is handed over, not re-implemented.

| Owned job | Status | Note |
|---|---|---|
| 静止画編集 | done |  |

## Wiring

The agent prepares overlay images with `strip` / `resize` / `pad` (step 4, video-production-agent#92, pinned 0.8.1); `still_image_edit` and thumbnail sources stay a handoff. `provides[]` in the contract since step 1.

## Steps

- [x] **1. provides[] in the contract** — image.convert -> imagemagick-skill/convert, ...
  - Done when: OS registry conformance lists it
- [x] **2. Windows CI with IM7 (RM-051)** — [#30](https://github.com/kajisho5/imagemagick-skill/pull/30)
  - Done when: CI green on Windows
- [x] **3. --timeout on every tool (RM-070)** — [#29](https://github.com/kajisho5/imagemagick-skill/pull/29)
  - Done when: test
- [x] **4. (agent side) SkillSpec image_prepare** — resize/pad/strip overlay assets for video-editing overlay and thumbnail — done in [video-production-agent#92](https://github.com/kajisho5/video-production-agent/pull/92) (ADR-077: image_strip / image_prepare / image_pad before edit.overlay; thumbnail sources not wired yet)
  - Done when: plan step selects imagemagick-skill/resize

---
Engine for every media operation: [ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) (3.x, 42 tools, contract_version 2.0; treated as complete, proposals go to Velisa's ROADMAP). Orchestrator: [video-production-agent](https://github.com/kajisho5/video-production-agent).
