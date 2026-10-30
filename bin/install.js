#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const PKG_ROOT = path.join(__dirname, "..");
const SCRIPTS_SRC = path.join(PKG_ROOT, "scripts");
const MCP_SRC = path.join(PKG_ROOT, "mcp");
const SKILL_MD_SRC = path.join(PKG_ROOT, "SKILL.md");
const PACKAGE_JSON_SRC = path.join(PKG_ROOT, "package.json");
const SKILL_NAME = "imagemagick-skill";

// This skill shipped as "image-skill" up to 0.2.x. That name on npm belongs to an
// unrelated package, so an "image-skill" directory next to a target may be ours or
// someone else's; it is only removed when every check in legacyNotOursReason() passes.
const LEGACY_NAME = "image-skill";
const LEGACY_CONTRACT_MARKER = "image-skill contract/doctor";
const LEGACY_REPO = "kajisho5/image-skill";
const LEGACY_TOP_LEVEL = new Set(["SKILL.md", "package.json", "scripts"]);

const USAGE = `usage: npx imagemagick-skill [target] [--uninstall]
       npx imagemagick-skill doctor [--json]
       npx imagemagick-skill contract --json
       npx imagemagick-skill --help

Install targets (default: global Claude Code):
  (no flag)          ~/.claude/skills/imagemagick-skill
  --cursor           ~/.cursor/skills/imagemagick-skill
  --codex            ~/.agents/skills/imagemagick-skill
  --all              all of the above
  --dir <parent>     <parent>/imagemagick-skill
  --project          ./.claude/skills/imagemagick-skill (current project only)

  --uninstall        remove the installed target(s) instead of installing

Formerly published as "image-skill": an old image-skill copy next to a target is
removed on install/uninstall only when it is recognisably this project's; anything
else is left in place with a warning.
`;

function targets(flags, cwd) {
  const home = os.homedir();
  if (flags.dir) {
    const parent = path.resolve(flags.dir);
    return [{ dir: path.join(parent, SKILL_NAME), legacy: [path.join(parent, LEGACY_NAME)] }];
  }
  if (flags.project) {
    const parent = path.join(cwd, ".claude", "skills");
    return [{ dir: path.join(parent, SKILL_NAME), legacy: [path.join(parent, LEGACY_NAME)] }];
  }
  const claude = {
    dir: path.join(home, ".claude", "skills", SKILL_NAME),
    legacy: [path.join(home, ".claude", "skills", LEGACY_NAME)],
  };
  const cursor = {
    dir: path.join(home, ".cursor", "skills", SKILL_NAME),
    legacy: [path.join(home, ".cursor", "skills", LEGACY_NAME)],
  };
  // Codex reads user skills from ~/.agents/skills; ~/.codex/skills (where 0.2.x
  // installed) is not a location Codex scans.
  const codex = {
    dir: path.join(home, ".agents", "skills", SKILL_NAME),
    legacy: [
      path.join(home, ".agents", "skills", LEGACY_NAME),
      path.join(home, ".codex", "skills", LEGACY_NAME),
    ],
  };
  if (flags.all) return [claude, cursor, codex];
  if (flags.cursor) return [cursor];
  if (flags.codex) return [codex];
  return [claude];
}

function frontmatterName(skillMdPath) {
  const text = fs.readFileSync(skillMdPath, "utf8");
  if (!text.startsWith("---")) return null;
  const end = text.indexOf("\n---", 3);
  if (end === -1) return null;
  const m = text.slice(3, end).match(/^name:\s*["']?([^"'\r\n]+?)["']?\s*$/m);
  return m ? m[1] : null;
}

// Returns null when `dir` is provably an install of this project under its old
// name, otherwise the reason it is not (and so must be left alone).
function legacyNotOursReason(dir) {
  const top = fs.lstatSync(dir);
  if (top.isSymbolicLink()) return "it is a symlink";
  if (!top.isDirectory()) return "it is not a directory";

  const extra = fs.readdirSync(dir).filter((e) => !LEGACY_TOP_LEVEL.has(e));
  if (extra.length) return `it contains files this installer never wrote (${extra.join(", ")})`;

  const skillMd = path.join(dir, "SKILL.md");
  if (!fs.existsSync(skillMd)) return "it has no SKILL.md";
  if (frontmatterName(skillMd) !== LEGACY_NAME) return `its SKILL.md name is not "${LEGACY_NAME}"`;

  const scriptsDir = path.join(dir, "scripts");
  if (!fs.existsSync(scriptsDir) || !fs.lstatSync(scriptsDir).isDirectory()) return "it has no scripts/ directory";
  for (const entry of fs.readdirSync(scriptsDir, { withFileTypes: true })) {
    const ok = (entry.isFile() && entry.name.endsWith(".py")) || (entry.isDirectory() && entry.name === "__pycache__");
    if (!ok) return `scripts/ contains ${entry.name}, which this project never shipped`;
  }
  const contractPy = path.join(scriptsDir, "_contract.py");
  if (!fs.existsSync(contractPy) || !fs.readFileSync(contractPy, "utf8").includes(LEGACY_CONTRACT_MARKER)) {
    return "scripts/_contract.py is not this project's";
  }

  const pkgPath = path.join(dir, "package.json");
  if (fs.existsSync(pkgPath)) {
    let pkg;
    try {
      pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
    } catch {
      return "its package.json is not valid JSON";
    }
    const repo = typeof pkg.repository === "string" ? pkg.repository : (pkg.repository && pkg.repository.url) || "";
    if (pkg.name !== LEGACY_NAME || !repo.toLowerCase().includes(LEGACY_REPO)) {
      return `its package.json is not ${LEGACY_NAME} from ${LEGACY_REPO}`;
    }
  }
  return null;
}

function cleanLegacy(legacyDirs) {
  let removed = 0;
  for (const dir of legacyDirs) {
    if (!fs.existsSync(dir) && !isDanglingSymlink(dir)) continue;
    let reason;
    try {
      reason = legacyNotOursReason(dir);
    } catch (err) {
      reason = `it could not be inspected (${err.message})`;
    }
    if (reason === null) {
      fs.rmSync(dir, { recursive: true, force: true });
      console.log(`removed old ${LEGACY_NAME} install: ${dir}`);
      removed += 1;
    } else {
      console.warn(`warning: left ${dir} in place: ${reason}.`);
      console.warn(`  If it is an old copy of this skill, delete it by hand; if another package owns it, keep it.`);
    }
  }
  return removed;
}

function isDanglingSymlink(p) {
  try {
    return fs.lstatSync(p).isSymbolicLink();
  } catch {
    return false;
  }
}

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    if (entry.name === "__pycache__") continue;
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDir(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

function installTo(dir) {
  // Wipe first so a reinstall never leaves an older version's scripts behind.
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  fs.copyFileSync(SKILL_MD_SRC, path.join(dir, "SKILL.md"));
  fs.copyFileSync(PACKAGE_JSON_SRC, path.join(dir, "package.json"));
  copyDir(SCRIPTS_SRC, path.join(dir, "scripts"));
  if (fs.existsSync(MCP_SRC)) copyDir(MCP_SRC, path.join(dir, "mcp"));
}

function warnIfNoBackend() {
  const python = findPython3();
  if (!python.ok) return; // `doctor` reports the missing Python itself
  const doctorScript = path.join(SCRIPTS_SRC, "_contract.py");
  const result = spawnSync(python.command, [...python.args, doctorScript, "doctor", "--json"], { encoding: "utf8" });
  if (result.error || result.status !== 0 || !result.stdout) {
    return; // doctor itself failed; `doctor` will surface the real error
  }
  let payload;
  try {
    payload = JSON.parse(result.stdout);
  } catch {
    return;
  }
  if (payload.ok) return;

  console.warn("");
  console.warn("warning: no usable image backend found (magick or sips).");
  console.warn("  macOS:          brew install imagemagick");
  console.warn("  Debian/Ubuntu:  sudo apt install imagemagick");
  console.warn("  Windows:        https://imagemagick.org/script/download.php#windows");
  console.warn("  Then check:     npx imagemagick-skill doctor");
  console.warn("");
}

// The names Python 3 goes by, in the order they are tried. A python.org install on
// Windows has the `py` launcher and `python`, not `python3`; elsewhere `python3` is the
// norm and `python` may be Python 2. Each candidate must prove it is Python 3.
function python3Candidates(platform) {
  if (platform === "win32") {
    return [
      { command: "py", args: ["-3"] },
      { command: "python", args: [] },
      { command: "python3", args: [] },
    ];
  }
  return [
    { command: "python3", args: [] },
    { command: "python", args: [] },
  ];
}

function findPython3() {
  const candidates = python3Candidates(process.platform);
  for (const c of candidates) {
    const r = spawnSync(c.command, [...c.args, "-c", "import sys; print(sys.version_info[0])"], {
      encoding: "utf8",
      timeout: 30000,
      windowsHide: true,
    });
    if (!r.error && r.status === 0 && (r.stdout || "").trim() === "3") return { ok: true, ...c };
  }
  const tried = candidates.map((c) => [c.command, ...c.args].join(" "));
  return {
    ok: false,
    code: "python_not_found",
    reason: `no Python 3 interpreter found on PATH (tried: ${tried.join(", ")}); install Python 3.9+ from https://www.python.org/downloads/ and make sure it is on PATH`,
    tried,
  };
}

function runContractOrDoctor(command, extraArgs) {
  const python = findPython3();
  if (!python.ok) {
    const { ok, code, reason, tried } = python;
    if (extraArgs.includes("--json")) {
      console.log(JSON.stringify({ ok, code, reason, tried }, null, 2));
    } else {
      console.error(`error: ${reason}`);
    }
    process.exit(1);
  }
  const script = path.join(SCRIPTS_SRC, "_contract.py");
  const result = spawnSync(python.command, [...python.args, script, command, ...extraArgs], { stdio: "inherit" });
  process.exit(result.status === null ? 1 : result.status);
}

function parseFlags(argv) {
  const flags = {
    cursor: false,
    codex: false,
    all: false,
    project: false,
    uninstall: false,
    dir: null,
    help: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    switch (arg) {
      case "--cursor":
        flags.cursor = true;
        break;
      case "--codex":
        flags.codex = true;
        break;
      case "--all":
        flags.all = true;
        break;
      case "--project":
        flags.project = true;
        break;
      case "--uninstall":
        flags.uninstall = true;
        break;
      case "--help":
      case "-h":
        flags.help = true;
        break;
      case "--dir":
        flags.dir = argv[++i];
        if (!flags.dir) {
          console.error("--dir requires a path argument");
          process.exit(1);
        }
        break;
      default:
        console.error(`unknown flag: ${arg}`);
        console.error(USAGE);
        process.exit(1);
    }
  }
  return flags;
}

function main() {
  const argv = process.argv.slice(2);
  const command = argv[0];

  if (command === "doctor" || command === "contract") {
    runContractOrDoctor(command, argv.slice(1));
    return;
  }

  const flags = parseFlags(argv);
  if (flags.help) {
    console.log(USAGE);
    return;
  }

  const list = targets(flags, process.cwd());

  if (flags.uninstall) {
    let removedAny = false;
    for (const t of list) {
      if (fs.existsSync(t.dir)) {
        fs.rmSync(t.dir, { recursive: true, force: true });
        console.log(`removed: ${t.dir}`);
        removedAny = true;
      }
      if (cleanLegacy(t.legacy) > 0) removedAny = true;
    }
    if (!removedAny) console.log(`no ${SKILL_NAME} install found at the selected target(s)`);
    return;
  }

  for (const t of list) {
    installTo(t.dir);
    console.log(`installed: ${t.dir}`);
    cleanLegacy(t.legacy);
  }
  console.log("");
  console.log("Already installed? Re-running replaces the copy with whatever version you run.");
  console.log("Next: npx imagemagick-skill doctor");

  warnIfNoBackend();
}

main();
