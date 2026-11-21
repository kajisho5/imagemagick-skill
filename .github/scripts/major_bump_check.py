#!/usr/bin/env python3
"""From 1.0.0, a contract:breaking change ships only in a major release, made by a hand bump (ADR-002).

docs/decisions.md ADR-002 (Velisa ADR-031 section 5, decision D46), adapted to this repository's release flow:
resolve_version.py refuses `major`/`breaking` and auto_bump.py refuses to cross a major boundary, so a major release
is only ever a pull request that bumps package.json's major version by hand (ADR-001, CONTRIBUTING.md "Releasing").
A `major` label therefore cannot make a breaking change releasable here; only that hand bump can.

Rule, once the latest `vX.Y.Z` tag is 1.0.0 or later:

    labelled contract:breaking, package.json's major above the tag's  -> passes (a major release)
    labelled contract:breaking, any other package.json version        -> fails
    not labelled contract:breaking                                    -> passes

Before 1.0.0 (or with no tag yet) it always passes: si contract-diff's rule there is that a breaking change needs only
a minor bump (Velisa ADR-020).

Two modes:

    --check-pr N [--head-sha SHA]   the pull request check (.github/workflows/major-bump-check.yml). With --head-sha it
                                    first waits for contract-diff's run on that commit, since contract-diff labels with
                                    GITHUB_TOKEN and a label set that way starts no workflow. It fails when that run did
                                    not succeed, never came, or left no contract:* label (a fork's token cannot write
                                    one): whether the pull request is breaking is then not known.
    --release                       the same rule for release.yml, over every pull request merged since the latest tag,
                                    before anything is bumped or tagged. In auto mode package.json equals the tag, so
                                    any merged contract:breaking pull request stops the release.

Pure logic lives in pr_verdict() and release_blockers(); the rest wraps it with `git` and `gh api`. Only label names,
commit subjects and package.json's version are read, and nothing read is run or spliced into a shell command.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PACKAGE_JSON = os.path.join(ROOT, "package.json")
CONTRACT_DIFF_WORKFLOW = "contract-diff.yml"
BREAKING_LABEL = "contract:breaking"
CONTRACT_LABEL_PREFIX = "contract:"
PR_NUMBER = re.compile(r"\(#(\d+)\)\s*$")
HOW_TO_FIX = ("Velisa ADR-031 / docs/decisions.md ADR-002: from 1.0.0 a breaking change ships only in a major release, "
              "which in this repository is a hand bump of package.json's major version (with its own CHANGELOG section). "
              "Bump the major version, or remove the breaking change. A 'major' label does not count here: "
              "resolve_version.py refuses it.")


def parse_version(text):
    """'v1.2.3' or '1.2.3' (a pre-release or build suffix is ignored) -> (1, 2, 3); None when it is not one."""
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return tuple(int(part) for part in m.groups()) if m else None


def package_version(path=PACKAGE_JSON):
    try:
        with open(path, encoding="utf-8") as fh:
            version = json.load(fh).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return version if isinstance(version, str) else None


def is_stable(tag_version):
    parsed = parse_version(tag_version)
    return parsed is not None and parsed[0] >= 1


def bumps_major(tag_version, version):
    """True when `version` (package.json) has a higher major than `tag_version` (the latest release tag)."""
    current, new = parse_version(tag_version), parse_version(version)
    return current is not None and new is not None and new[0] > current[0]


def pr_verdict(labels, tag_version, version, need_contract_label=False):
    """(ok, message) for one pull request with these labels, the latest tag and package.json's version on the PR.

    `need_contract_label`: contract-diff ran and succeeded on this commit, so a pull request with no contract:* label
    at all was not classified (a fork's token cannot label) and fails.
    """
    names = sorted({name.lower() for name in labels})
    if not is_stable(tag_version):
        return True, f"{tag_version or 'no release tag'} is before 1.0.0: a contract:breaking change needs no major bump"
    if need_contract_label and not any(name.startswith(CONTRACT_LABEL_PREFIX) for name in names):
        return False, ("contract-diff put no contract:* label on this pull request (a fork's token cannot write one), "
                       "so whether it is breaking is not known. A maintainer reads contract-diff's summary and adds "
                       "contract:none, contract:additive or contract:breaking; the check then runs again")
    if BREAKING_LABEL not in names:
        return True, f"not labelled {BREAKING_LABEL}"
    if version is None:
        return False, f"labelled {BREAKING_LABEL} on {tag_version}, and package.json's version cannot be read"
    if bumps_major(tag_version, version):
        return True, f"labelled {BREAKING_LABEL}, and package.json is bumped by hand to {version}: a major release"
    return False, (f"labelled {BREAKING_LABEL}, but package.json says {version}, not a major release after "
                   f"{tag_version}. {HOW_TO_FIX}")


def release_blockers(tag_version, version, pulls):
    """pulls: [(subject, label names)] merged since the tag -> the reasons the release must stop (empty: it may go)."""
    if not is_stable(tag_version) or bumps_major(tag_version, version):
        return []
    return [f"{BREAKING_LABEL} in a release of {version or '(unreadable package.json)'} after {tag_version}, "
            f"not a major: {subject}"
            for subject, labels in pulls if BREAKING_LABEL in {name.lower() for name in labels}]


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def _gh_json(path):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=True).stdout
    return json.loads(out or "null")


def _latest_tag():
    tags = _git("tag", "--list", "v*", "--sort=-v:refname").split()
    return tags[0] if tags else ""


def _wait_for_contract_diff(repo, sha, appear=120, finish=1500, every=15):
    """Wait for contract-diff's run on `sha` -> "ok", "absent" (no contract-diff.yml here) or the reason it is not."""
    if not os.path.exists(os.path.join(ROOT, ".github", "workflows", CONTRACT_DIFF_WORKFLOW)):
        return "absent"
    start = time.monotonic()
    time.sleep(every)  # the run this same event starts may not be listed yet
    while True:
        runs = _gh_json(f"repos/{repo}/actions/workflows/{CONTRACT_DIFF_WORKFLOW}/runs"
                        f"?head_sha={sha}&event=pull_request&per_page=50")
        runs = sorted((runs or {}).get("workflow_runs", []),
                      key=lambda run: (run.get("created_at") or "", run.get("id") or 0))
        waited = time.monotonic() - start
        if runs and all(run.get("status") == "completed" for run in runs):
            conclusion = runs[-1].get("conclusion")
            return "ok" if conclusion == "success" else f"the newest contract-diff run on {sha[:12]} ended {conclusion}"
        if not runs and waited >= appear:
            return f"no contract-diff run on {sha[:12]} after {appear}s"
        if waited >= finish:
            return f"contract-diff on {sha[:12]} has not finished after {finish}s"
        time.sleep(every)


def check_pr(repo, number, head_sha=None):
    tag = _latest_tag()
    if not is_stable(tag):
        print(f"{tag or 'no release tag'} is before 1.0.0: nothing to check")
        return 0
    waited = None
    if head_sha:
        waited = _wait_for_contract_diff(repo, head_sha)
        if waited == "absent":
            base = os.environ.get("GITHUB_BASE_REF") or "main"
            try:
                _git("cat-file", "-e", f"origin/{base}:.github/workflows/{CONTRACT_DIFF_WORKFLOW}")
                print(f"::error::this pull request removes {CONTRACT_DIFF_WORKFLOW}, which {base} has, "
                      f"so it is not classified")
                return 1
            except subprocess.CalledProcessError:
                print(f"no {CONTRACT_DIFF_WORKFLOW} here: the labels are read as they are")
        elif waited != "ok":
            print(f"::error::{waited}, so this pull request's contract:* label is not known. "
                  f"Re-run contract-diff, then this check.")
            return 1
    labels = [label["name"] for label in _gh_json(f"repos/{repo}/issues/{number}/labels?per_page=100") or []]
    version = package_version()
    ok, message = pr_verdict(labels, tag, version, need_contract_label=waited == "ok")
    print(f"labels: {', '.join(sorted(labels)) or '(none)'}; latest tag: {tag}; package.json: {version}")
    print(message if ok else f"::error::{message}")
    return 0 if ok else 1


def check_release(repo):
    tag = _latest_tag()
    version = package_version()
    if not is_stable(tag):
        print(f"{tag or 'no release tag'} is before 1.0.0: nothing to check")
        return 0
    if bumps_major(tag, version):
        print(f"package.json is bumped by hand to {version} after {tag}: a major release")
        return 0
    pulls = []
    for subject in _git("log", f"{tag}..HEAD", "--format=%s").splitlines():
        m = PR_NUMBER.search(subject)
        if m:
            pull = _gh_json(f"repos/{repo}/pulls/{m.group(1)}") or {}  # release.yml's token has pull-requests: read
            pulls.append((subject, [label["name"] for label in pull.get("labels", [])]))
    blockers = release_blockers(tag, version, pulls)
    for reason in blockers:
        print(f"::error::{reason}")
    if blockers:
        print(f"since {tag}: no release. {HOW_TO_FIX}")
        return 1
    print(f"since {tag}: no {BREAKING_LABEL} pull request")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-pr", type=int, metavar="NUMBER", help="check one pull request")
    mode.add_argument("--release", action="store_true", help="check every pull request merged since the latest tag")
    parser.add_argument("--head-sha", help="with --check-pr: wait for contract-diff's run on this commit first")
    args = parser.parse_args(argv)
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        print("major_bump_check.py: GITHUB_REPOSITORY is required to read pull request labels", file=sys.stderr)
        return 2
    if args.release:
        return check_release(repo)
    return check_pr(repo, args.check_pr, args.head_sha)


if __name__ == "__main__":
    sys.exit(main())
