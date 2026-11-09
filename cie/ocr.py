import subprocess


def extract_image_text(path, timeout=20):
    if not path:
        return ""
    try:
        result = subprocess.run(
            ["/opt/homebrew/bin/tesseract", path, "stdout"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return ""
    if result.returncode != 0 or not result.stdout:
        return ""
    return " ".join(result.stdout.split())
