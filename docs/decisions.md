# Architecture decisions

Each entry records one decision, why it was taken, and what it changes. Behaviours that look
like bugs but are decisions are in [design-decisions.md](design-decisions.md) instead.

## ADR-001: 1.0.0, and which tools are STABLE

Status: Accepted (2026-11-21). Follows Velisa ADR-031 (decision D46), which defines what 1.0
means for a Skill of the AI Video Production OS and the order the Skills get there. The
owner approved the 1.0 transition for this skill.

### Context

Up to 0.10.2 every `provides[]` entry was `EXPERIMENTAL`, so the contract promised nothing
about any tool, and a dependent could not tell from the version whether a release broke it.
Velisa ADR-031 ranked this skill fourth of the 0.x Skills:

- no breaking change in the contract tag diffs (v0.10.1, v0.10.2) or in the `contract:*`
  labels of the merged pull requests;
- no open roadmap step that changes the contract. All six steps of `ECOSYSTEM_ROADMAP.md`
  are done, and the planned items in `docs/roadmap.md` (RM-052 to RM-084) only add flags or
  output keys;
- video-production-agent pins the contract and gates the version, so its re-pin proves the
  release end to end;
- 18 releases;
- the only known defects were the behaviour follow-ups in #44 (`contract --json` not
  byte-identical to `contract/contract.json`, a brandkit `OSError` outside the JSON error
  path, a partial PNG after a brandkit timeout). They were fixed in #49 (0.10.2), without
  a contract change.

### Decision

**STABLE** (a change `si contract-diff` calls breaking ships only in a major release):

| Tool | Why it is ready |
|---|---|
| `probe`, `convert`, `resize`, `thumb`, `strip`, `trim`, `check` | In the skill since 0.1.0 (RM-001 to RM-007) and listed in the OS capability matrix. Their flags and output keys have only grown since then. |
| `resize`, `pad`, `strip` | video-production-agent runs them to prepare overlay images (agent ADR-077). It reads their flags, enums and defaults from the pinned contract. |
| `crop`, `optimize` (and `resize`, `convert`, `strip`) | The agent's still-image job names them (agent ADR-115). In the skill since 0.4.0. |

**EXPERIMENTAL** (may still change in a minor release, named in the CHANGELOG):

- `look`, `compare`, `rotate`, `adjust`, `overlay`, `montage`, `icons` and `preset`. No
  dependent runs them yet. `overlay` and `icons` have planned extensions (RM-064 to RM-067),
  and `preset`'s size table follows outside sources (RM-062, RM-063).
- `alpha` and `brandkit`: the newest tools (0.9.0, 0.10.0). `brandkit` had behaviour fixes in
  0.10.2.
- `batch`: it runs EXPERIMENTAL tools too (`look`, `montage`, `icons`, `compare`), and
  RM-068 and RM-069 (parallel jobs, a content-hash cache) may change how it reports.

The promise also covers what every tool shares:

- the `result_shapes` (failure, dry run, timeout) and the exit codes 1 and 124;
- the `rules`;
- the top-level contract fields;
- the `usable` and `backend` row of each STABLE tool in `doctor --json`.

`contract_version` stays 1.0. It is the shape of the contract document, a separate axis from
the release version.

**Deprecation.** To retire a STABLE tool, or a flag or output key of one:

1. Mark it deprecated in a minor release. For a tool, set `lifecycle: DEPRECATED` in
   `provides`. For a flag or output key, which has no lifecycle field, say so in the tool's
   `description`. The CHANGELOG and the README name the replacement, or say there is none.
2. Keep it working for at least one more minor release and at least 30 days.
3. Remove it only in the next major release.

An EXPERIMENTAL tool may be removed in a minor release, with a CHANGELOG line. Promoting one
to STABLE is metadata only (si's `lifecycle-promoted` rule classifies it as `none`), so it can
happen in any release.

**Release.** This repository's release flow has no `major` label: `resolve_version.py`
refuses `major`/`breaking`, and `auto_bump.py` refuses to cross a major boundary. Its way to
make a major release is a pull request that bumps `package.json` by hand and writes its own
CHANGELOG section (CONTRIBUTING.md, "Releasing"; design-decisions.md, "Releasing").
`release.yml` then tags and publishes that version as it is. So the 1.0 pull request bumps
the version files (`package.json`, `.claude-plugin/plugin.json`, `skill.contract.json`,
`docs/contract.md`, `docs/roadmap.md`, `contract/contract.json`) and adds `## 1.0.0` to the
CHANGELOG. No workflow change is needed.

### Consequences

- The contract diff of 1.0.0 against 0.10.2 is the version and ten `lifecycle-promoted`
  entries, which `si contract-diff` classifies as `none`. The agent's re-pin can therefore
  widen its version gate to `1.0.` on its own (agent ADR-117).
- After 1.0, a pull request that contract-diff labels `contract:breaking` needs a reviewer
  check before merging: either it is a major release (a hand bump to 2.0.0), or every
  breaking change is in an EXPERIMENTAL tool. This repository does not run Velisa's
  `major-label-check` yet (it has no `release_gate.py`), so that check is by review.
- `tests/test_contract.py::test_provides_lifecycle_is_the_1_0_promise` pins the STABLE set.
  Changing it takes a new entry here and a CHANGELOG line.
- `tests/test_stable_snapshot.py` (roadmap RM-074) compares every STABLE tool with
  `tests/stable_tools_snapshot.json`, written from the 1.0.0 contract. A removed or renamed
  argument or required output key, or a newly required argument, fails it before
  contract-diff runs. Additions pass.
