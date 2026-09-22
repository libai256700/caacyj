#!/usr/bin/env python3
"""Render a credential-free macOS LaunchAgent from the bundled template."""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
from pathlib import Path
from string import Template
from xml.sax.saxutils import escape


def absolute_path(value: str, label: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path: {value}")
    return path


def render(args: argparse.Namespace) -> Path:
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    template_path = skill_dir / "assets" / "ai.openclaw.job-crawler-watchdog.plist.template"
    workspace = absolute_path(args.workspace, "workspace")
    output = absolute_path(args.output, "output")
    python_path = absolute_path(args.python, "python")
    openclaw_home = absolute_path(args.openclaw_home, "openclaw-home")
    home = Path.home().resolve()

    if not python_path.is_file():
        raise FileNotFoundError(f"python executable not found: {python_path}")
    watchdog = skill_dir / "scripts" / "job_crawler_watchdog.py"
    if not watchdog.is_file():
        raise FileNotFoundError(f"watchdog script not found: {watchdog}")

    log_dir = openclaw_home / "logs" / "job-crawler-watchdog"
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_dir.chmod(0o700)
    config = workspace / "projects" / "recruitment-crawler" / "config.json"

    values = {
        "PYTHON": escape(str(python_path)),
        "WATCHDOG": escape(str(watchdog)),
        "WORKSPACE": escape(str(workspace)),
        "HOME": escape(str(home)),
        "OPENCLAW_HOME": escape(str(openclaw_home)),
        "CONFIG": escape(str(config)),
        "PATH": escape(args.path),
        "TIMEZONE": escape(args.timezone),
        "HOUR": str(args.hour),
        "MINUTE": str(args.minute),
        "STDOUT": escape(str(log_dir / "stdout.log")),
        "STDERR": escape(str(log_dir / "stderr.log")),
    }
    rendered = Template(template_path.read_text(encoding="utf-8")).substitute(values)
    parsed = plistlib.loads(rendered.encode("utf-8"))
    if "RunAtLoad" in parsed or "KeepAlive" in parsed:
        raise ValueError("watchdog template must not set RunAtLoad or KeepAlive")

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(rendered, encoding="utf-8")
        tmp.chmod(0o644)
        tmp.replace(output)
        output.chmod(0o644)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return output


def main() -> int:
    default_python = shutil.which("python3") or ""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace",
        default=os.environ.get(
            "OPENCLAW_WORKSPACE",
            str(Path.home() / ".openclaw" / "workspace"),
        ),
    )
    parser.add_argument(
        "--openclaw-home",
        default=os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw")),
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--python", default=default_python)
    parser.add_argument("--hour", type=int, default=10)
    parser.add_argument("--minute", type=int, default=0)
    parser.add_argument(
        "--timezone",
        default="Asia/Kuala_Lumpur",
        help="watchdog process timezone only; launchd scheduling uses the Mac system timezone",
    )
    parser.add_argument("--path", default=os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"))
    args = parser.parse_args()

    if not 0 <= args.hour <= 23 or not 0 <= args.minute <= 59:
        parser.error("hour/minute are outside the valid range")
    if not args.python:
        parser.error("python3 not found; pass --python /absolute/path/to/python3")
    try:
        output = render(args)
    except (FileNotFoundError, OSError, ValueError, plistlib.InvalidFileException) as exc:
        parser.error(str(exc))
    print(f"Rendered LaunchAgent: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
