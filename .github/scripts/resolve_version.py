#!/usr/bin/env python3
"""Decide the next release version from the labels of the PRs merged since the last tag.

Used by .github/workflows/release.yml (same approach as kajisho5/ffmpeg-skill). It
replaces calling release-drafter for version resolution, which on this repo either
resolved nothing (`disable-releaser: true` switches the resolver off) or ran live and
left a draft release behind (`dry-run` is not an input of release-drafter v6), and could
never answer "nothing to release" because its `default: patch` bumps regardless.

Rules (same label vocabulary as .github/release-drafter.yml's autolabeler):

  dependencies (Dependabot)          -> patch, whatever else it carries (Velisa D37 addendum;
                                        a bot's major/minor label is about the dependency)
  major / breaking                   -> refuse (exit 1): a major is a hand edit of package.json
  minor / feature / enhancement      -> minor
  patch / fix / bug                  -> patch
  only chore / ci / docs / test / refactor (or any other label) -> not releasable
  no label at all                    -> patch (a PR nobody labelled still ships)

A PR with `chore` AND `fix` is a fix. A commit on main that came from no PR is patch
unless its subject starts with chore/ci/docs/build/test/refactor. If nothing since the
last tag is releasable, the resolved version is empty and release.yml does nothing.

Pure logic lives in resolve(); main() wraps it with `git log` and `gh api`. Only label
names are read from the API, never PR text.
"""
import json
import os
import re
import subprocess
import sys

MAJOR = {"major", "breaking"}
MINOR = {"minor", "feature", "enhancement"}
PATCH = {"patch", "fix", "bug"}
NOT_RELEASABLE_TITLE = re.compile(r"^(chore|ci|docs|build|test|refactor)\b", re.I)
PR_NUMBER = re.compile(r"\(#(\d+)\)\s*$")


class MajorRefused(Exception):
    pass


def bump_for_labels(labels):
    """'major' / 'minor' / 'patch' / None (not releasable) for one PR's labels."""
    names = {label.lower() for label in labels}
    if "dependencies" in names:
        return "patch"
    if names & MAJOR:
        return "major"
    if names & MINOR:
        return "minor"
    if names & PATCH:
        return "patch"
    if not names:
        return "patch"
    return None


def resolve(last_version, subjects, labels_for):
    """Return (next_version or None, per-commit decisions).

    subjects: commit subjects on main since the last tag (git log order).
    labels_for: PR number -> list of its label names.
    """
    decisions = []
    bumps = []
    for subject in subjects:
        m = PR_NUMBER.search(subject)
        if m:
            number = int(m.group(1))
            labels = list(labels_for(number))
            bump = bump_for_labels(labels)
            decisions.append({"subject": subject, "pr": number, "labels": sorted(labels), "bump": bump})
        else:
            bump = None if NOT_RELEASABLE_TITLE.match(subject) else "patch"
            decisions.append({"subject": subject, "pr": None, "labels": [], "bump": bump})
        if bump:
            bumps.append(bump)
    if not bumps:
        return None, decisions
    if "major" in bumps:
        raise MajorRefused(
            "refusing to resolve a major version automatically; a major release is a deliberate, "
            "hand-made package.json bump in a PR"
        )
    parts = [int(p) for p in last_version.split(".")]
    while len(parts) < 3:
        parts.append(0)
    major, minor, patch = parts[:3]
    if "minor" in bumps:
        return f"{major}.{minor + 1}.0", decisions
    return f"{major}.{minor}.{patch + 1}", decisions


def _gh_labels(repo):
    def labels_for(number):
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}/pulls/{number}", "--jq", "[.labels[].name]"],
            capture_output=True, text=True, check=True,
        ).stdout
        return list(json.loads(out or "[]"))
    return labels_for


def main():
    last = os.environ["LAST_VERSION"]
    repo = os.environ["GITHUB_REPOSITORY"]
    rev_range = f"v{last}..HEAD" if last != "0.0.0" else "HEAD"
    subjects = [
        s for s in subprocess.run(
            ["git", "log", rev_range, "--format=%s"], capture_output=True, text=True, check=True
        ).stdout.splitlines() if s.strip()
    ]
    try:
        version, decisions = resolve(last, subjects, _gh_labels(repo))
    except MajorRefused as e:
        print(f"::error::{e}")
        return 1
    for d in decisions:
        pr = f"#{d['pr']}" if d["pr"] else "(no PR)"
        print(f"  {d['bump'] or '-':6} {pr:8} {','.join(d['labels']) or '(unlabeled)':30} {d['subject']}")
    print(f"last tag v{last} -> {'no release' if version is None else version}")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
        fh.write(f"resolved_version={version or ''}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
