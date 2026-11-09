"""Local Codex subscription bridge for visual classification.

The public CLI can use the operator's signed-in Codex subscription without an
API key.  Codex receives the exact local evidence files as image attachments
and must return a JSON object matching the supplied schema.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Sequence


class SubscriptionAgentError(RuntimeError):
    pass


def run_subscription_visual_agent(*, prompt: str, image_paths: Sequence[str], schema: dict[str, Any], cwd: str | None = None) -> str:
    executable = shutil.which("codex")
    if not executable:
        raise SubscriptionAgentError("Codex CLI was not found on PATH; install/sign in to Codex or use OpenRouter/OpenAI BYOK.")
    images = [str(Path(path).resolve()) for path in image_paths if Path(path).is_file()]
    if not images:
        raise SubscriptionAgentError("subscription visual classification requires at least one readable image")
    working_root = str(Path(cwd or os.getcwd()).resolve())
    with tempfile.TemporaryDirectory(prefix="wct-subscription-") as temp_dir:
        schema_path = Path(temp_dir) / "schema.json"
        response_path = Path(temp_dir) / "response.json"
        schema_path.write_text(json.dumps(schema, ensure_ascii=True), encoding="utf-8")
        command = [
            executable,
            "exec",
            "--sandbox",
            "read-only",
            "--cd",
            working_root,
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(response_path),
        ]
        for image in images:
            command.extend(("--image", image))
        # `--image` accepts multiple values, so the separator prevents the
        # natural-language prompt from being consumed as another image path.
        command.append("--")
        command.append(prompt)
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
        except OSError as error:
            raise SubscriptionAgentError(f"could not start Codex CLI: {error}") from error
        except subprocess.TimeoutExpired as error:
            raise SubscriptionAgentError("Codex visual classification timed out after 300 seconds") from error
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown Codex CLI failure").strip()
            raise SubscriptionAgentError(f"Codex visual classification failed: {detail[-1200:]}")
        try:
            return response_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise SubscriptionAgentError("Codex visual classification completed without a structured response") from error
