#!/usr/bin/env python3
"""_contract.py - machine-readable description of the toolset (contract) and a live
environment check (doctor). Both are JSON-first: an agent should read `contract`
instead of guessing flags, and run `doctor` before assuming a format/tool works.

Each tool's input_schema (and the legacy required_args/optional_args lists) is
derived from that script's own build_parser(); only facts a parser cannot state
(role, backends, output shape) are written by hand in TOOL_META."""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (  # noqa: E402
    DEFAULT_TIMEOUT,
    TIMEOUT_EXIT_CODE,
    ImageSkillError,
    JSONArgumentParser,
    fail,
    find_fonts,
    magick_argv,
    magick_kind,
    wants_json,
    which_magick,
    which_sips,
)


def _read_version():
    """Single source of truth is package.json (copied alongside scripts/ by the
    installer into every target) - avoids a hardcoded version string here drifting
    out of sync with it."""
    pkg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "package.json")
    try:
        with open(pkg_path, "r", encoding="utf-8") as f:
            return json.load(f).get("version", "0.0.0")
    except (OSError, ValueError):
        return "0.0.0"


VERSION = _read_version()
SKILL_ID = "imagemagick-skill"

CONTRACT_VERSION = "1.0"
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Output shapes shared by every tool. A tool's own output_schema lists only what
# an ok:true, non-dry-run --json result carries.
FAILURE_SCHEMA = {
    "ok": {"type": "boolean", "description": "always false"},
    "reason": {"type": "string", "description": "human-readable cause, including argument errors; a tool may add context keys (compare --fail-below: its metrics; optimize: smallest_bytes, attempts)"},
}
# A failure because --timeout ran out: the failure shape plus code and timeout, exit 124.
TIMEOUT_SCHEMA = {
    **FAILURE_SCHEMA,
    "code": {"type": "string", "enum": ["timeout"], "description": "always \"timeout\"; exit status 124 (every other failure has no code and exits 1). ImageMagick and every process it started have been killed, and an output file the run had begun is removed"},
    "timeout": {"type": "number", "description": "the --timeout budget, in seconds, that ran out"},
}
DRY_RUN_SCHEMA = {
    "ok": {"type": "boolean", "description": "always true"},
    "dry_run": {"type": "boolean", "description": "always true"},
    "would_run": {"type": "array", "description": "argv of the backend command that would run (never a shell string); a tool that runs several commands lists one argv per command"},
}

_WH = {"type": "object", "description": "{width, height} in pixels"}

# Hand-written facts a parser cannot express. Everything about arguments (names,
# types, choices, defaults, required/positional) is derived from each script's own
# build_parser() in tool_spec(), so the contract cannot drift from the CLI.
TOOL_META = {
    "probe": dict(
        description="Report width, height, format, colorspace, alpha, and GPS presence as JSON.",
        role="analysis",
        backends=["magick", "sips"],
        verify=[],
        output_schema={
            "input": {"type": "string"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "format": {"type": "string", "description": "backend format name, e.g. JPEG, PNG, HEIC (sips reports lowercase)"},
            "colorspace": {"type": ["string", "null"], "description": "null on the sips backend"},
            "has_alpha": {"type": ["boolean", "null"], "description": "null on the sips backend"},
            "has_gps": {"type": ["boolean", "null"], "description": "GPS coordinates in the EXIF block (parsed by the tool for every format, HEIC included); null when an EXIF block can't be parsed, and on the sips backend"},
            "backend": {"type": "string", "enum": ["magick", "sips"]},
            "note": {"type": "string", "description": "present when a field could not be measured"},
        },
        output_required=["input", "width", "height", "format", "backend"],
    ),
    "convert": dict(
        description="Convert an image to a different format (e.g. HEIC to JPEG/PNG/WebP). Input is preserved.",
        role="execution",
        backends=["magick", "sips"],
        verify=["check"],
        output_schema={
            "input": {"type": "string"},
            "output": {"type": "string"},
            "backend": {"type": "string", "enum": ["magick", "sips"]},
        },
        output_required=["input", "output", "backend"],
    ),
    "resize": dict(
        description="Resize an image: fit (default, no distortion), fill (crop to cover), or exact (force size).",
        role="execution",
        backends=["magick", "sips"],
        verify=["check"],
        output_schema={
            "input": {"type": "string"},
            "output": {"type": "string"},
            "mode": {"type": "string", "enum": ["fit", "fill", "exact"]},
            "requested": _WH,
            "actual": _WH,
            "backend": {"type": "string", "enum": ["magick", "sips"]},
        },
        output_required=["input", "output", "mode", "requested", "actual", "backend"],
    ),
    "thumb": dict(
        description="Create a thumbnail sized by its longest edge, preserving aspect ratio.",
        role="execution",
        backends=["magick", "sips"],
        verify=["check"],
        output_schema={
            "input": {"type": "string"},
            "output": {"type": "string"},
            "long_edge": {"type": "integer"},
            "actual": _WH,
            "backend": {"type": "string", "enum": ["magick", "sips"]},
        },
        output_required=["input", "output", "long_edge", "actual", "backend"],
    ),
    "strip": dict(
        description="Remove GPS/EXIF metadata. Applies orientation before stripping. Requires ImageMagick.",
        role="execution",
        backends=["magick"],
        verify=["check", "probe"],
        output_schema={
            "input": {"type": "string"},
            "output": {"type": "string"},
            "has_gps": {"type": "boolean", "description": "always false: a result that still has GPS is a failure"},
            "backend": {"type": "string", "enum": ["magick"]},
        },
        output_required=["input", "output", "has_gps", "backend"],
    ),
    "trim": dict(
        description="Trim a solid-color border. Fails instead of over-trimming. Requires ImageMagick.",
        role="execution",
        backends=["magick"],
        verify=["check"],
        output_schema={
            "input": {"type": "string"},
            "output": {"type": "string"},
            "original": _WH,
            "trimmed": _WH,
            "removed_percent": {"type": "number"},
            "backend": {"type": "string", "enum": ["magick"]},
        },
        output_required=["input", "output", "original", "trimmed", "removed_percent", "backend"],
    ),
    "check": dict(
        description="Verify an output file opens, matches promised dimensions/format, and didn't overwrite the input.",
        role="verification",
        backends=["magick", "sips"],
        verify=[],
        output_schema={
            "output": {"type": "string"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "format": {"type": ["string", "null"], "description": "read only when --expect-format is given"},
        },
        output_required=["output", "width", "height", "format"],
    ),
    "look": dict(
        description="Make a labelled preview sheet (or a before/after pair) of images so the agent can look at them.",
        role="verification",
        backends=["magick"],
        verify=[],
        output_schema={
            "output": {"type": "string"},
            "mode": {"type": "string", "enum": ["grid", "pair"]},
            "inputs": {"type": "array", "description": "per input: {path, width, height, format, has_alpha}"},
            "tile": {"type": "integer"},
            "cols": {"type": "integer"},
            "rows": {"type": "integer"},
            "labels": {"type": "boolean"},
            "actual": _WH,
            "backend": {"type": "string", "enum": ["magick"]},
            "note": {"type": "string", "description": "present when labels were dropped (no font)"},
        },
        output_required=["output", "mode", "inputs", "tile", "cols", "rows", "labels", "actual", "backend"],
    ),
    "compare": dict(
        description="Measure the difference between two same-size images (SSIM, PSNR, changed pixels), optionally write a heatmap, optionally fail below an SSIM threshold.",
        role="verification",
        backends=["magick"],
        verify=["look"],
        output_optional=True,
        output_schema={
            "a": {"type": "string"},
            "b": {"type": "string"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "identical": {"type": "boolean"},
            "ssim": {"type": "number", "description": "0-1, 1 = identical; luma, 7x7 window, after downsampling by ssim_scale"},
            "ssim_scale": {"type": "integer", "description": "downsampling factor applied before SSIM (shorter side ~256)"},
            "psnr_db": {"type": ["number", "null"], "description": "null when the images are identical"},
            "diff_ratio": {"type": "number", "description": "share of pixels whose largest channel difference exceeds --fuzz"},
            "diff_pixels": {"type": "integer"},
            "fuzz": {"type": "number"},
            "output": {"type": "string", "description": "the heatmap, when -o was given"},
            "fail_below": {"type": "number"},
            "passed": {"type": "boolean"},
            "backend": {"type": "string", "enum": ["magick"]},
        },
        output_required=["a", "b", "width", "height", "identical", "ssim", "ssim_scale", "psnr_db",
                         "diff_ratio", "diff_pixels", "fuzz", "backend"],
    ),
    "optimize": dict(
        description="Re-encode an image to fit a file-size budget (--max-kb) without changing its dimensions; fails with the smallest size reached when it cannot.",
        role="execution",
        backends=["magick", "sips"],
        verify=["check", "look"],
        output_schema={
            "input": {"type": "string"},
            "output": {"type": "string"},
            "format": {"type": "string"},
            "max_kb": {"type": "number"},
            "bytes": {"type": "integer"},
            "kb": {"type": "number"},
            "original_bytes": {"type": "integer"},
            "quality": {"type": ["integer", "null"], "description": "null for PNG and for webp:target-size"},
            "method": {"type": "string", "enum": ["quality-search", "webp:target-size", "lossless"]},
            "attempts": {"type": "array", "description": "every encode tried: {quality|target_bytes, bytes}"},
            "stripped": {"type": "boolean"},
            "actual": _WH,
            "backend": {"type": "string", "enum": ["magick", "sips"]},
        },
        output_required=["input", "output", "format", "max_kb", "bytes", "kb", "original_bytes", "quality",
                         "method", "attempts", "stripped", "actual", "backend"],
    ),
    "crop": dict(
        description="Crop to an exact pixel rectangle, or to the largest region of an aspect ratio placed by gravity. Never clips a rectangle silently.",
        role="execution",
        backends=["magick", "sips"],
        verify=["check", "look"],
        output_schema={
            "input": {"type": "string"},
            "output": {"type": "string"},
            "mode": {"type": "string", "enum": ["rect", "aspect"]},
            "box": {"type": "object", "description": "{x, y, width, height} cut from the image as displayed"},
            "original": _WH,
            "actual": _WH,
            "backend": {"type": "string", "enum": ["magick", "sips"]},
        },
        output_required=["input", "output", "mode", "box", "original", "actual", "backend"],
    ),
    "pad": dict(
        description="Pad to an aspect ratio or exact canvas with a given colour (or transparency), never scaling or cropping the image.",
        role="execution",
        backends=["magick", "sips"],
        verify=["check", "look"],
        output_schema={
            "input": {"type": "string"},
            "output": {"type": "string"},
            "mode": {"type": "string", "enum": ["aspect", "canvas"]},
            "color": {"type": "string"},
            "original": _WH,
            "offset": {"type": ["object", "null"], "description": "{x, y} of the image on the canvas; null on sips"},
            "actual": _WH,
            "backend": {"type": "string", "enum": ["magick", "sips"]},
        },
        output_required=["input", "output", "mode", "color", "original", "offset", "actual", "backend"],
    ),
    "rotate": dict(
        description="Rotate clockwise, mirror, or just bake EXIF orientation into the pixels.",
        role="execution",
        backends=["magick", "sips"],
        verify=["check", "look"],
        output_schema={
            "input": {"type": "string"},
            "output": {"type": "string"},
            "degrees": {"type": "number"},
            "flip_horizontal": {"type": "boolean"},
            "flip_vertical": {"type": "boolean"},
            "orientation_before": {"type": ["string", "null"], "description": "EXIF orientation of the input (magick), e.g. RightTop"},
            "original": _WH,
            "actual": _WH,
            "backend": {"type": "string", "enum": ["magick", "sips"]},
        },
        output_required=["input", "output", "degrees", "flip_horizontal", "flip_vertical", "orientation_before",
                         "original", "actual", "backend"],
    ),
    "adjust": dict(
        description="Levels, brightness, contrast, saturation, blur and sharpen with explicit values; never 'auto'.",
        role="execution",
        backends=["magick"],
        verify=["check", "look"],
        output_schema={
            "input": {"type": "string"},
            "output": {"type": "string"},
            "operations": {"type": "array", "description": "applied in order: levels, brightness-contrast, saturation, blur, sharpen"},
            "actual": _WH,
            "backend": {"type": "string", "enum": ["magick"]},
        },
        output_required=["input", "output", "operations", "actual", "backend"],
    ),
    "overlay": dict(
        description="Overlay a logo image or a line of text at a position with margin and opacity; text is rendered literally with a script-appropriate font.",
        role="execution",
        backends=["magick"],
        verify=["check", "look"],
        output_schema={
            "input": {"type": "string"},
            "output": {"type": "string"},
            "kind": {"type": "string", "enum": ["image", "text"]},
            "position": {"type": "string"},
            "margin": {"type": "integer"},
            "opacity": {"type": "number"},
            "overlay": _WH,
            "font": {"type": ["string", "null"], "description": "font file used for text; null for an image overlay"},
            "actual": _WH,
            "backend": {"type": "string", "enum": ["magick"]},
        },
        output_required=["input", "output", "kind", "position", "margin", "opacity", "overlay", "font", "actual", "backend"],
    ),
    "montage": dict(
        description="Compose several images into a row or grid with an explicit background, optional gap and captions.",
        role="execution",
        backends=["magick"],
        verify=["check", "look"],
        output_schema={
            "inputs": {"type": "array", "description": "per input: {path, width, height}"},
            "output": {"type": "string"},
            "cols": {"type": "integer"},
            "rows": {"type": "integer"},
            "cell": _WH,
            "gap": {"type": "integer"},
            "background": {"type": "string"},
            "labels": {"type": "boolean"},
            "font": {"type": ["string", "null"]},
            "actual": _WH,
            "backend": {"type": "string", "enum": ["magick"]},
        },
        output_required=["inputs", "output", "cols", "rows", "cell", "gap", "background", "labels", "font", "actual", "backend"],
    ),
    "icons": dict(
        description="Make favicon.ico (several sizes), PNG icons and apple-touch-icon.png from one square image, plus the HTML and manifest entries.",
        role="execution",
        backends=["magick"],
        verify=["look"],
        output_schema={
            "input": {"type": "string"},
            "output_dir": {"type": "string"},
            "files": {"type": "array", "description": "per file: {path, purpose, sizes, format}"},
            "html": {"type": "array", "description": "<link> tags for the written icons"},
            "manifest_icons": {"type": "array", "description": "web app manifest `icons` entries (192 and up)"},
            "notes": {"type": "array", "description": "present when something needs the caller's attention"},
            "backend": {"type": "string", "enum": ["magick"]},
        },
        output_required=["input", "output_dir", "files", "html", "manifest_icons", "backend"],
    ),
    "preset": dict(
        description="Resize to a named published size (og, instagram-*, youtube-thumbnail, ...) with fill, fit or pad; --list shows sizes and their sources.",
        role="execution",
        backends=["magick", "sips"],
        verify=["check", "look"],
        output_optional=True,
        output_schema={
            "input": {"type": "string"},
            "output": {"type": "string"},
            "preset": {"type": "string"},
            "description": {"type": "string"},
            "source": {"type": "string", "description": "documentation URL the size comes from"},
            "mode": {"type": "string", "enum": ["fill", "fit", "pad"]},
            "requested": _WH,
            "actual": _WH,
            "via": {"type": "array", "description": "tools run: [resize] or [resize, pad]"},
            "backend": {"type": "string", "enum": ["magick", "sips"]},
            "presets": {"type": "object", "description": "--list only: every preset with size, description, source, quote"},
        },
        output_required=[],
    ),
    "batch": dict(
        description="Run a tool over every image in a folder: per-file tools write one output each, look/montage one composite, icons one folder per image, compare pairs with --against.",
        role="execution",
        backends=["magick", "sips"],
        verify=["check"],
        extra_properties={
            "tool_args": {
                "type": "array",
                "items": {"type": "string"},
                "cli": "after --",
                "description": "arguments forwarded to the per-file tool, e.g. [\"--width\", \"1200\", \"--height\", \"1200\"]",
            },
        },
        output_schema={
            "tool": {"type": "string"},
            "count": {"type": "integer"},
            "all_ok": {"type": "boolean"},
            "results": {"type": "array", "description": "one {file, output, ok, result|reason} per input file; a file whose --timeout ran out also has code \"timeout\" and timeout"},
        },
        output_required=["tool", "count", "all_ok", "results"],
    ),
}

RULES = [
    "Never overwrite the input: -o/--output is required and must differ from the input path.",
    "Every tool supports --json for machine-readable output; every tool that writes a file also supports --dry-run to preview the command without running it (check.py writes nothing, so it has no --dry-run).",
    "Failures - including a malformed invocation with missing or invalid flags - return ok:false with a human-readable 'reason'; a broken or empty output is never reported as success.",
    "Call probe.py before editing and check.py after, to confirm the result matches what was promised.",
    "Tools never invoke mogrify (which overwrites in place) and never build a magick command from caller-supplied strings.",
    f"Every tool takes --timeout SECONDS (default {DEFAULT_TIMEOUT}; batch: per file): when it runs out, ImageMagick's whole process group (delegates such as gs or ffmpeg included) is killed and the tool fails with ok:false, code \"timeout\", exit status {TIMEOUT_EXIT_CODE}.",
]

EXECUTION = {"shell": False, "network": False, "input_mutation": False, "arbitrary_executables": False}


def public_tools():
    """Tool names in contract order. Every public script (no leading underscore)
    must have a TOOL_META entry and vice versa - tests enforce both directions."""
    return list(TOOL_META)


def _load_tool_module(name):
    spec = importlib.util.spec_from_file_location(f"imagemagick_skill_tool_{name}", os.path.join(SCRIPTS_DIR, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json_type(action):
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return {"type": "boolean"}
    if isinstance(action, argparse._AppendAction) or action.nargs in ("+", "*"):
        return {"type": "array", "items": {"type": "string"}}
    if action.type is int:
        return {"type": "integer"}
    if action.type is float or getattr(action.type, "json_type", None) == "number":
        return {"type": "number"}
    return {"type": "string"}


def input_schema(parser):
    """JSON-schema-like description of a parser: one property per argparse dest."""
    props = {}
    required = []
    positional = []
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        prop = _json_type(action)
        if action.help and action.help != argparse.SUPPRESS:
            prop["description"] = action.help
        if action.choices:
            prop["enum"] = list(action.choices)
        if action.default not in (None, False, argparse.SUPPRESS):
            prop["default"] = action.default
        if action.option_strings:
            prop["cli"] = list(action.option_strings)
            if action.required:
                required.append(action.dest)
        else:
            prop["cli"] = "positional"
            positional.append(action.dest)
            if action.nargs not in ("?", "*"):
                required.append(action.dest)
        props[action.dest] = prop
    schema = {
        "type": "object",
        "properties": props,
        "required": required,
        "positional": positional,
        "additionalProperties": False,
    }
    groups = [g for g in getattr(parser, "_mutually_exclusive_groups", []) if g._group_actions]
    if groups:
        schema["mutually_exclusive"] = [[a.dest for a in g._group_actions] for g in groups]
    return schema


def _flag_label(prop, dest):
    cli = prop["cli"]
    if cli == "positional":
        return dest
    return "/".join(cli)


def tool_spec(name):
    meta = TOOL_META[name]
    parser = _load_tool_module(name).build_parser()
    schema = input_schema(parser)
    for dest, prop in meta.get("extra_properties", {}).items():
        schema["properties"][dest] = dict(prop)
    props = schema["properties"]
    real = [d for d in props if props[d]["cli"] != "after --"]
    required_args = [_flag_label(props[d], d) for d in real if d in schema["required"]]
    optional_args = [_flag_label(props[d], d) for d in real if d not in schema["required"]]
    writes_output = "output" in props or "output_dir" in props
    if name == "check":
        writes_output = False  # its positional is named "output" but it only reads it
    return {
        "name": name,
        "script": f"{name}.py",
        "description": meta["description"],
        "writes_output": writes_output,
        "required_args": required_args,
        "optional_args": optional_args,
        "id": f"{SKILL_ID}/{name}",
        "executable": f"scripts/{name}.py",
        "role": meta["role"],
        "backends": list(meta["backends"]),
        "requires_magick": meta["backends"] == ["magick"],
        "supports_json": "json" in props,
        "supports_dry_run": "dry_run" in props,
        "output_optional": bool(meta.get("output_optional", False)),
        "mutates_input": False,
        "verify": list(meta["verify"]),
        "input_schema": schema,
        "output_schema": {
            "type": "object",
            "properties": dict(meta["output_schema"]),
            "required": ["ok"] + list(meta["output_required"]),
        },
    }


# Transport flags the MCP server sets itself; they are not tool arguments there.
MCP_TRANSPORT_FLAGS = ("json",)

MCP_INSTRUCTIONS = (
    "Local ImageMagick image editing. Every tool writes a new file (-o/output must differ from "
    "the input and never already exist unless overwrite is true) and returns its JSON result. "
    "Arguments are the input_schema property names; positional ones are passed by name too. "
    "Use absolute file paths. Run probe before editing, check (and look, to see it) after."
)


def mcp_tool(spec):
    """tools/list entry for one contract tool: name, description, inputSchema - all
    derived from the contract, so the MCP surface cannot drift from the scripts."""
    src = spec["input_schema"]
    positional = list(src["positional"])
    props = {}
    for dest, prop in src["properties"].items():
        if dest in MCP_TRANSPORT_FLAGS:
            continue
        out = {"type": prop["type"]}
        if prop["type"] == "array":
            out["items"] = dict(prop.get("items", {"type": "string"}))
        desc = prop.get("description", "")
        if dest in positional:
            desc = f"(positional {positional.index(dest) + 1}) {desc}".strip()
        elif prop.get("cli") == "after --":
            desc = f"(passed after --) {desc}".strip()
        if desc:
            out["description"] = desc
        for key in ("enum", "default"):
            if key in prop:
                out[key] = prop[key]
        props[dest] = out
    description = spec["description"]
    for group in src.get("mutually_exclusive", []):
        description += f" Give exactly one of: {', '.join(group)}."
    schema = {"type": "object", "properties": props, "additionalProperties": False}
    required = [d for d in src["required"] if d not in MCP_TRANSPORT_FLAGS]
    if required:
        schema["required"] = required
    return {"name": spec["name"], "description": description, "inputSchema": schema}


def mcp_argv(spec, arguments):
    """Structured MCP arguments -> the script's argv (plus --json), using the contract's
    own CLI mapping. Raises ValueError for arguments the tool does not have."""
    props = spec["input_schema"]["properties"]
    unknown = sorted(k for k in arguments if k not in props or k in MCP_TRANSPORT_FLAGS)
    if unknown:
        raise ValueError(f"unknown argument(s) for {spec['name']}: {', '.join(unknown)}")
    argv, after = [], []
    for dest in spec["input_schema"]["positional"]:
        value = arguments.get(dest)
        if value is None:
            continue
        argv += [str(v) for v in value] if isinstance(value, list) else [str(value)]
    for dest, value in arguments.items():
        prop = props[dest]
        if dest in spec["input_schema"]["positional"] or value is None or value is False:
            continue
        if prop["cli"] == "after --":
            after += [str(v) for v in (value if isinstance(value, list) else [value])]
            continue
        flag = next((c for c in prop["cli"] if c.startswith("--")), prop["cli"][0])
        if value is True:
            argv.append(flag)
        elif isinstance(value, list):
            for v in value:
                argv += [flag, str(v)]
        else:
            argv += [flag, str(value)]
    argv.append("--json")
    return argv + (["--"] + after if after else [])


def provides(names):
    """The AI Video Production OS registry's capability ids: image.<tool> -> imagemagick-skill/<tool>."""
    return [{"id": f"image.{n}", "lifecycle": "EXPERIMENTAL", "tool_id": f"{SKILL_ID}/{n}"} for n in names]


def build_contract_payload():
    tools = [tool_spec(name) for name in public_tools()]
    return {
        "ok": True,
        "name": SKILL_ID,
        "version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "skill": {
            "id": SKILL_ID,
            "version": VERSION,
            "execution_mode": "local",
            "entrypoints": {
                "cli": "python3 scripts/<tool>.py",
                "contract": "python3 scripts/_contract.py contract --json",
                "mcp": "python3 mcp/server.py",
                "doctor": "python3 scripts/_contract.py doctor --json",
            },
        },
        "requirements": {
            "python": ">=3.9 (standard library only)",
            "backends": "ImageMagick `magick` (every tool) or macOS `sips` (subset; see each tool's backends)",
        },
        "execution": dict(EXECUTION),
        "result_shapes": {"failure": FAILURE_SCHEMA, "timeout": TIMEOUT_SCHEMA, "dry_run": DRY_RUN_SCHEMA},
        "provides": provides(public_tools()),
        "tools": tools,
        "rules": RULES,
    }


_FORMAT_MODE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\*?(?:\s+\S+)?\s+([r-][w-][+-])\s", re.MULTILINE)


def _format_capabilities(formats_out):
    """Map format name (upper) -> (can_read, can_write), parsed from the Mode
    column of `magick -list format` (e.g. 'rw+', 'r--', '-w-').

    A format name appearing in the list at all does NOT mean both directions
    work: a read-only delegate (mode 'r--') still lets `magick in.png
    out.heic` exit 0, silently writing the wrong format under the requested
    name instead of failing (see verify_output_format in _common.py) - so
    doctor has to check the actual mode flags, not just presence of the name.
    """
    caps = {}
    for name, mode in _FORMAT_MODE_RE.findall(formats_out):
        caps[name.upper()] = (mode[0] == "r", mode[1] == "w")
    return caps


def _magick_lists(magick):
    formats = subprocess.run([magick, "-list", "format"], capture_output=True, text=True, timeout=30)
    policy = subprocess.run([magick, "-list", "policy"], capture_output=True, text=True, timeout=30)
    version = subprocess.run([magick, "-version"], capture_output=True, text=True, timeout=30)
    return formats.stdout, policy.stdout, version.stdout


def _heic_roundtrip(magick):
    """Write a tiny HEIC and read it back: {"write": bool, "read": bool or None}.

    `-list format`'s mode flags describe the coder, not the libheif plugins behind it:
    with only an encoder plugin (x265) ImageMagick still lists HEIC as readable, writes a
    valid file, and then fails to decode it ("Unsupported codec"). read is None when
    nothing could be written to test it with."""
    with tempfile.TemporaryDirectory(prefix="imagemagick-skill-doctor-") as tmp:
        path = os.path.join(tmp, "probe.heic")
        try:
            subprocess.run(magick_argv([magick, "-size", "16x16", "xc:#808080", path]),
                           capture_output=True, timeout=30)
            with open(path, "rb") as f:
                written = f.read(12)[4:8] == b"ftyp"
        except (OSError, subprocess.TimeoutExpired):
            written = False
        if not written:
            return {"write": False, "read": None}
        try:
            proc = subprocess.run(magick_argv([magick, "identify", "-format", "%m", path]),
                                  capture_output=True, text=True, timeout=30)
            read = proc.returncode == 0 and proc.stdout.strip().upper().startswith("HEIC")
        except (OSError, subprocess.TimeoutExpired):
            read = False
        return {"write": True, "read": read}


HEIC_NO_DECODER = (
    "ImageMagick lists HEIC as readable, but it could not read back a HEIC it had just written: "
    "the libheif decoder plugin is missing (Debian/Ubuntu: `sudo apt install libheif-plugin-libde265`)"
)


def _tool_status(magick, sips, needs_magick_only=False):
    if magick:
        return {"usable": True, "backend": "magick"}
    if sips and not needs_magick_only:
        return {"usable": True, "backend": "sips", "note": "reduced feature set via sips"}
    if needs_magick_only:
        return {"usable": False, "backend": None, "fix": "install ImageMagick: `brew install imagemagick`"}
    return {
        "usable": False,
        "backend": None,
        "fix": "install ImageMagick or, on macOS, ensure sips is on PATH",
    }


def build_doctor_payload():
    magick = which_magick()
    sips = which_sips()
    is_mac = sys.platform == "darwin"

    backends = {
        "magick": {"found": bool(magick), "path": magick, "kind": magick_kind() if magick else None},
        "sips": {"found": bool(sips), "path": sips},
    }

    heic = {"usable": False, "read": False, "write": False, "backend": None, "fix": None}
    webp = {"usable": False, "read": False, "write": False, "backend": None, "fix": None}
    pdf_policy = None
    magick_version = None

    if magick:
        try:
            formats_out, policy_out, version_out = _magick_lists(magick)
            magick_version = version_out.strip().splitlines()[0] if version_out.strip() else None
            caps = _format_capabilities(formats_out)
            heic_read, heic_write = caps.get("HEIC", (False, False))
            heic_verified = _heic_roundtrip(magick) if heic_write else {"write": False, "read": None}
            heic_write = heic_write and heic_verified["write"]
            heic_no_decoder = heic_read and heic_verified["read"] is False
            heic_read = heic_read and not heic_no_decoder
            webp_read, webp_write = caps.get("WEBP", (False, False))

            # "usable" tracks the workflow this skill actually documents: HEIC is
            # read FROM (iPhone photos in, something else out); WebP is written TO
            # (an OG/thumb asset out). Both directions are still reported so an
            # agent doesn't get burned assuming the other direction also works.
            if heic_read:
                heic = {
                    "usable": True,
                    "read": True,
                    "write": heic_write,
                    "backend": "magick",
                    "fix": None
                    if heic_write
                    else "read-only HEIC on this build (no encode delegate) - can convert FROM HEIC but not "
                    "create it; reinstall ImageMagick with libheif's encoder for write support, e.g. "
                    "`brew reinstall imagemagick`, or use sips on macOS to write HEIC",
                }
            elif is_mac and sips:
                heic = {
                    "usable": True,
                    "read": True,
                    "write": True,
                    "backend": "sips",
                    "fix": None,
                    "note": HEIC_NO_DECODER + "; falling back to sips for HEIC" if heic_no_decoder
                    else "magick has no HEIC read delegate here; falling back to sips for HEIC",
                }
            else:
                heic = {
                    "usable": False,
                    "read": False,
                    "write": heic_write,
                    "backend": None,
                    "fix": HEIC_NO_DECODER if heic_no_decoder
                    else "reinstall ImageMagick with HEIC support, e.g. `brew reinstall imagemagick` "
                    "(needs libheif), or run on macOS to use sips instead",
                }
            heic["verified"] = heic_verified

            if webp_write:
                webp = {"usable": True, "read": webp_read, "write": True, "backend": "magick", "fix": None}
            else:
                webp = {
                    "usable": False,
                    "read": webp_read,
                    "write": False,
                    "backend": None,
                    "fix": "reinstall ImageMagick with WebP write support, e.g. `brew reinstall imagemagick` "
                    "(needs libwebp)",
                }

            pdf_disabled = "PDF" in policy_out.upper() and 'rights="none"' in policy_out.lower()
            pdf_policy = {
                "enabled": not pdf_disabled,
                "note": (
                    "PDF read/write is blocked by ImageMagick's policy.xml on this system"
                    if pdf_disabled
                    else "not detected as blocked here; PDF conversion is out of scope for this skill regardless"
                ),
            }
        except (subprocess.TimeoutExpired, OSError) as e:
            heic = {"usable": False, "read": False, "write": False, "backend": None, "fix": f"could not query magick: {e}"}
    elif is_mac and sips:
        heic = {"usable": True, "read": True, "write": True, "backend": "sips", "fix": None}
        webp = {
            "usable": False,
            "read": False,
            "write": False,
            "backend": None,
            "fix": "sips cannot write WebP; install ImageMagick: `brew install imagemagick`",
        }
    else:
        heic = {
            "usable": False,
            "read": False,
            "write": False,
            "backend": None,
            "fix": "install ImageMagick (`brew install imagemagick` / your package manager) or run on macOS for sips",
        }
        webp = {
            "usable": False,
            "read": False,
            "write": False,
            "backend": None,
            "fix": "install ImageMagick: `brew install imagemagick`",
        }

    tools = {
        name: _tool_status(magick, sips, needs_magick_only=meta["backends"] == ["magick"])
        for name, meta in TOOL_META.items()
    }

    overall_ok = magick is not None or sips is not None

    payload = {
        "ok": overall_ok,
        "platform": sys.platform,
        "backends": backends,
        "magick_version": magick_version,
        "heic": heic,
        "webp": webp,
        "pdf_policy": pdf_policy,
        "fonts": find_fonts(),
        "tools": tools,
    }
    if not overall_ok:
        payload["reason"] = (
            "no usable backend found: install ImageMagick (`brew install imagemagick`, `apt install imagemagick`, "
            "or https://imagemagick.org) or run on macOS for the sips fallback"
        )
    return payload


def cmd_contract(args):
    payload = build_contract_payload()
    print(json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2))


def cmd_doctor(args):
    payload = build_doctor_payload()
    print(json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2))


def build_parser():
    parser = JSONArgumentParser(description=f"{SKILL_ID} contract/doctor")
    sub = parser.add_subparsers(dest="command", required=True)

    contract_p = sub.add_parser("contract", help="describe the available tools as JSON")
    contract_p.add_argument("--json", action="store_true")
    contract_p.set_defaults(func=cmd_contract)

    doctor_p = sub.add_parser("doctor", help="check the local environment for usable backends")
    doctor_p.add_argument("--json", action="store_true")
    doctor_p.set_defaults(func=cmd_doctor)

    return parser


def main(argv=None):
    as_json = wants_json(argv)
    try:
        args = build_parser().parse_args(argv)
    except ImageSkillError as e:
        fail(str(e), as_json)
        return
    args.func(args)


if __name__ == "__main__":
    main()
