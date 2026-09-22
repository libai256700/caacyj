from pathlib import Path
import subprocess
import sys


def main() -> int:
    project_dir = Path.cwd()
    if not (project_dir / "pom.xml").is_file():
        print("Run this script from the backend project root containing pom.xml.", file=sys.stderr)
        return 2

    command = [
        "mvn",
        "-pl",
        "yunjikeji-admin-server",
        "-Dtest=FrontPracticeBatchServiceContractTest,FrontPracticeServiceImplBatchStartContractTest",
        "test",
    ]
    return subprocess.run(command, cwd=project_dir, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
