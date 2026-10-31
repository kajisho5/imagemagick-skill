#!/usr/bin/env python3
"""Write the files for an automatic release bump OLD_VERSION -> NEW_VERSION.

Run by .github/workflows/release.yml from the repository root after
resolve_version.py picked NEW_VERSION; the workflow commits and pushes the result.
Kept as a script (ffmpeg-skill runs the same logic inline) so tests can drive it in a
throwaway git repository.

  - refuses to cross a major boundary: a major release is a hand-made package.json
    bump in a PR, never inferred from labels
  - moves the version in package.json, .claude-plugin/plugin.json, skill.contract.json
    (SkillPact: `skill.version` only), docs/contract.md (two anchors only) and
    docs/roadmap.md ("The released version today is ...")
  - writes a CHANGELOG.md section: whatever sits under "## Unreleased" moves into it,
    followed by the commit subjects since the last tag read from `git log` at run time
    (never interpolated by the workflow: PR titles are attacker-controlled text), and
    "## Unreleased" is reset to "(nothing yet)"
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bump_contract_md import bump_contract_md  # noqa: E402
from bump_roadmap_md import bump_roadmap_md  # noqa: E402

VERSION_FIELD = re.compile(r'("version":\s*")[^"]+(")')
# skill.contract.json has other "version" keys (requirement ranges); only the one directly inside "skill" moves
SKILL_VERSION_FIELD = re.compile(r'("skill":\s*\{[^{}]*?"version":\s*")[^"]+(")')


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def bump_json_version(path, new, field=VERSION_FIELD):
    text = _read(path)
    updated = field.sub(rf"\g<1>{new}\g<2>", text, count=1)
    if updated == text:
        raise SystemExit(f"{path}: version field not found or already {new}")
    _write(path, updated)


def changelog_section(old, new, root):
    last_tag = f"v{old}" if old != "0.0.0" else None
    rev_range = f"{last_tag}..HEAD" if last_tag else "HEAD"
    log = subprocess.run(
        ["git", "log", rev_range, "--format=%s----BODY----%b----COMMIT----"],
        capture_output=True, text=True, check=True, cwd=root,
    ).stdout
    subjects, issues = [], set()
    for commit in (c for c in log.split("----COMMIT----") if c.strip()):
        subject, _, body = commit.partition("----BODY----")
        subject = subject.strip()
        if subject:
            subjects.append(subject)
        issues.update(int(n) for n in re.findall(r"(?im)^closes\s+#(\d+)\.?\s*$", body))
    bullets = "\n".join(f"- {s}" for s in subjects) or "- (no commit subjects found)"
    closes = f"\n\nCloses: {', '.join(f'#{n}' for n in sorted(issues))}" if issues else ""
    return (
        f"## {new}\n\n"
        f"_Automated release: version and notes generated from pull requests merged since {old}._\n\n"
        f"{bullets}{closes}\n\n"
    )


def update_changelog(text, section, old):
    m = re.search(r"## Unreleased\n(.*?)(?=^## )", text, re.S | re.M)
    if not m:
        raise SystemExit("CHANGELOG.md has no '## Unreleased' section followed by a version heading")
    unreleased = m.group(1).strip()
    if unreleased and unreleased != "(nothing yet)":
        section = section.replace(f"since {old}._\n\n", f"since {old}._\n\n{unreleased}\n\n", 1)
    return text[:m.start()] + "## Unreleased\n\n(nothing yet)\n\n" + section + text[m.end():]


def main(root="."):
    old = os.environ["OLD_VERSION"]
    new = os.environ["NEW_VERSION"]
    if old.split(".")[0] != new.split(".")[0]:
        raise SystemExit(
            f"refusing to auto-bump across a major boundary ({old} -> {new}); "
            "bump package.json by hand in a PR if a major release is intended"
        )
    path = lambda *p: os.path.join(root, *p)  # noqa: E731
    bump_json_version(path("package.json"), new)
    bump_json_version(path(".claude-plugin", "plugin.json"), new)
    bump_json_version(path("skill.contract.json"), new, SKILL_VERSION_FIELD)
    _write(path("docs", "contract.md"), bump_contract_md(_read(path("docs", "contract.md")), old, new))
    _write(path("docs", "roadmap.md"), bump_roadmap_md(_read(path("docs", "roadmap.md")), old, new))
    section = changelog_section(old, new, root)
    _write(path("CHANGELOG.md"), update_changelog(_read(path("CHANGELOG.md")), section, old))
    print(f"bumped {old} -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
