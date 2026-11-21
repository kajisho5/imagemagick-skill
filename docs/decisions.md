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
- After 1.0, a pull request that contract-diff labels `contract:breaking` must be a major
  release (a hand bump to 2.0.0). CI enforces this since ADR-002.
- `tests/test_contract.py::test_provides_lifecycle_is_the_1_0_promise` pins the STABLE set.
  Changing it takes a new entry here and a CHANGELOG line.
- `tests/test_stable_snapshot.py` (roadmap RM-074) compares every STABLE tool with
  `tests/stable_tools_snapshot.json`, written from the 1.0.0 contract. A removed or renamed
  argument or required output key, or a newly required argument, fails it before
  contract-diff runs. Additions pass.

## ADR-002: from 1.0.0, CI fails a breaking pull request without a hand major bump

Status: Accepted (2026-11-21). Applies Velisa ADR-031 section 5 (decision D46) to this
repository's release flow. Replaces ADR-001's review-only check of
`contract:breaking` pull requests.

### Context

Velisa ADR-031 says that from a Skill's 1.0.0, a change `si contract-diff` calls breaking
ships only in a major release. The other Skills enforce it with `release_gate.py` and a
`major-label-check` workflow: a `contract:breaking` pull request needs a `major` label, and
release-drafter then resolves a major version.

That design does not fit here. `resolve_version.py` refuses `major`/`breaking`, and
`auto_bump.py` refuses to cross a major boundary. A major release is only ever a pull
request that bumps `package.json` by hand and writes its own CHANGELOG section (ADR-001,
CONTRIBUTING.md "Releasing"). A `major` label here would only make the release job fail
after the merge.

### Decision

The check is on the version, not on a label. Once the latest `vX.Y.Z` tag is 1.0.0 or later:

| The pull request | `package.json` on it | Result |
|---|---|---|
| labelled `contract:breaking` | major above the tag's (for example 2.0.0 after v1.0.0) | passes |
| labelled `contract:breaking` | anything else, `major` label or not | fails |
| `contract:additive`, `contract:none` | any | passes |

Before 1.0.0, or with no tag, it always passes. si contract-diff's rule there is that a
breaking change needs only a minor bump (Velisa ADR-020).

- `.github/scripts/major_bump_check.py` holds the rule (`pr_verdict()`, `release_blockers()`).
- `.github/workflows/major-bump-check.yml` runs it on every pull request, on `opened`,
  `synchronize`, `reopened`, `labeled` and `unlabeled`. A label a person adds or removes
  therefore runs it again. contract-diff labels with `GITHUB_TOKEN`, and that starts no
  workflow, so the check first waits for contract-diff's run on the head commit. It fails
  when that run did not succeed, never came, or left no `contract:*` label (a fork's token
  cannot write one). In those cases whether the pull request is breaking is not known.
- `release.yml` runs `major_bump_check.py --release` before it resolves, bumps, tags or
  publishes anything, over every pull request merged since the tag. In auto mode
  `package.json` equals the tag, so any merged `contract:breaking` pull request stops the
  release. A hand bump that is not a major stops it too. main and the tags stay as they are.
  This catches a pull request merged while its check was red, or relabelled after the merge.

The workflow is named `major-bump-check`, not `major-label-check`, because no label can make it
pass.

### Consequences

- A pull request that breaks only an EXPERIMENTAL tool is still labelled `contract:breaking`
  by contract-diff, and so still needs a major bump. si contract-diff does not tell the two
  apart. If that comes up, the remedy is a new ADR, not removing the label by hand. A
  maintainer removes `contract:breaking` only when the breaking change was reverted.
- `tests/test_major_bump_check.py` pins the rule: a breaking pull request without a major
  bump fails, with one it passes, additive and none pass, and before 1.0 nothing is checked.
  It also pins the workflow triggers and that the release step runs before any bump or tag.
- No contract change and no release: the change is CI only (`ci`, `docs` and `test` labels).
