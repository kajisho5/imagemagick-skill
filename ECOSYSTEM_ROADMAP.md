# Roadmap — imagemagick-skill

Part of the [AI Video Production OS](https://github.com/kajisho5/AI-video-production-OS/blob/main/docs/ecosystem/ROADMAP.md) ecosystem: department **補助 (Utility)**, status `active`.
Written from a read-only audit of this repository on 2026-10-30. Each step below is meant to be one pull request; tick it off by linking the PR.

## Where it stands

v0.7.1. 19 tools (probe, convert, resize, thumb, strip, trim, check, look, compare, optimize, crop, pad, rotate, adjust, overlay, montage, icons, preset, batch); npm installer + MCP. 173 tests; CI on Ubuntu (no IM / IM6) and macOS (sips / IM7), no Windows.

## What this repository owns

`ecosystem.json` gives each job to exactly one repository. Work outside this list belongs to its owner and is handed over, not re-implemented.

| Owned job | Status | Note |
|---|---|---|
| 静止画編集 | done |  |

## Wiring

Not reachable from the agent. Contract fits via skill.id but has no provides[].

## Steps

- [x] **1. provides[] in the contract** — image.convert -> imagemagick-skill/convert, ...
  - Done when: OS registry conformance lists it
- [x] **2. Windows CI with IM7 (RM-051)** — [#30](https://github.com/kajisho5/imagemagick-skill/pull/30)
  - Done when: CI green on Windows
- [x] **3. --timeout on every tool (RM-070)** — [#29](https://github.com/kajisho5/imagemagick-skill/pull/29)
  - Done when: test
- [ ] **4. (agent side) SkillSpec image_prepare** — resize/pad/strip overlay assets for video-editing overlay and thumbnail
  - Done when: plan step selects imagemagick-skill/resize

---
Engine for every media operation: [ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) (42 tools, treated as complete). Orchestrator: [video-production-agent](https://github.com/kajisho5/video-production-agent).
