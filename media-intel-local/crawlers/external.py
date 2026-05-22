import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


class ExternalCommandError(RuntimeError):
    pass


def python_command(value: Any, base_dir: Optional[Path] = None) -> List[str]:
    if isinstance(value, list) and value:
        command = [str(part) for part in value]
        return _resolve_program(command, base_dir)
    if value:
        return _resolve_program([str(value)], base_dir)
    return [sys.executable]


def _resolve_program(command: List[str], base_dir: Optional[Path]) -> List[str]:
    if not base_dir or not command:
        return command
    program = Path(command[0])
    if program.is_absolute():
        return command
    candidate = (base_dir / program).resolve()
    if candidate.exists():
        command[0] = str(candidate)
    return command


def run_json_command(
    command: List[str],
    cwd: Optional[Path] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 120,
) -> Any:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    runtime_root = Path(os.getenv("MEDIA_INTEL_RUNTIME_DIR") or (Path.cwd() / ".runtime"))
    env.setdefault("CRAWL4_AI_BASE_DIRECTORY", str(runtime_root / "crawl4ai"))
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(runtime_root / "playwright"))
    env.setdefault("HOME", str(runtime_root / "home"))
    env.setdefault("USERPROFILE", str(runtime_root / "home"))
    stdin_text = None
    if payload is not None:
        stdin_text = json.dumps(payload, ensure_ascii=False)

    try:
        result = subprocess.run(
            command,
            input=stdin_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
            env=env,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except OSError as exc:
        raise ExternalCommandError("cannot start {}: {}".format(command[0], exc))
    except subprocess.TimeoutExpired:
        raise ExternalCommandError(
            "external command timed out after {}s: {}".format(
                timeout_seconds, " ".join(command)
            )
        )

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-1200:]
        raise ExternalCommandError(
            "external command failed with exit {}: {} {}".format(
                result.returncode, " ".join(command), detail
            ).strip()
        )

    stdout = (result.stdout or "").strip()
    if not stdout:
        raise ExternalCommandError("external command returned empty JSON output")
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ExternalCommandError(
            "external command returned invalid JSON: {} output={}".format(
                exc, stdout[-1200:]
            )
        )
    if isinstance(parsed, dict) and parsed.get("error"):
        raise ExternalCommandError("external tool error: {}".format(parsed["error"]))
    return parsed
