"""Deploy the reviewed source and verified big-screen assets to the server.

Credentials are read from S_HOST/S_USER/S_PASS. If S_PASS is absent, the
script prompts without echoing it. The live database volume is never copied or
modified by this script.
"""
from __future__ import annotations

import getpass
import os
import shlex
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path

import paramiko

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REMOTE_ROOT = "/root/welding-sheet-system"
HOST = os.environ.get("S_HOST", "8.137.13.118")
USER = os.environ.get("S_USER", "root")

DEPLOY_PATHS = (
    "README.md",
    "docker-compose.yml",
    "backend/Dockerfile",
    "backend/.env.example",
    "backend/deploy_server.py",
    "backend/requirements.txt",
    "backend/requirements-migration.txt",
    "backend/app",
    "frontend/Dockerfile",
    "frontend/nginx.conf",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/tsconfig.json",
    "frontend/tsconfig.node.json",
    "frontend/vite.config.ts",
    "frontend/src",
    "frontend/bigscreen-assets",
    "docs/code-audit-2026-07-19.md",
)


def _archive_filter(member: tarfile.TarInfo) -> tarfile.TarInfo | None:
    parts = Path(member.name).parts
    if "__pycache__" in parts or "node_modules" in parts or member.name.endswith((".pyc", ".tsbuildinfo")):
        return None
    return member


def deployment_paths() -> tuple[str, ...]:
    tests = tuple(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in sorted((PROJECT_ROOT / "backend").glob("test_*.py"))
    )
    return DEPLOY_PATHS + tests


def build_archive(timestamp: str, paths: tuple[str, ...]) -> Path:
    archive_path = Path(os.environ.get("TEMP", r"C:\temp")) / f"welding-audit-{timestamp}.tar.gz"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as archive:
        for relative in paths:
            source = PROJECT_ROOT / relative
            if not source.exists():
                raise FileNotFoundError(source)
            archive.add(source, arcname=relative, filter=_archive_filter)
    return archive_path


def run(client: paramiko.SSHClient, command: str, timeout: int = 900) -> str:
    print(f"\nSERVER $ {command}")
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    output = stdout.read().decode("utf-8", "replace")
    error = stderr.read().decode("utf-8", "replace")
    status = stdout.channel.recv_exit_status()
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    if error:
        print(error, end="" if error.endswith("\n") else "\n")
    if status:
        raise RuntimeError(f"remote command failed with exit status {status}")
    return output


def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    subprocess.run(
        ["python", "frontend/bigscreen-assets/patch_bigscreen_runtime.py"],
        cwd=PROJECT_ROOT,
        check=True,
    )
    paths = deployment_paths()
    archive = build_archive(timestamp, paths)
    remote_archive = f"/tmp/{archive.name}"
    backup = f"/root/welding-sheet-system-audit-{timestamp}.tar.gz"
    password = os.environ.get("S_PASS") or getpass.getpass("Server password: ")

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST,
        username=USER,
        password=password,
        timeout=20,
        look_for_keys=False,
        allow_agent=False,
    )
    try:
        run(client, f"test -d {shlex.quote(REMOTE_ROOT)}")
        run(
            client,
            "tar --ignore-failed-read -czf "
            f"{shlex.quote(backup)} -C {shlex.quote(REMOTE_ROOT)} "
            + " ".join(shlex.quote(path) for path in paths),
        )
        run(client, f"test -s {shlex.quote(backup)}")

        with client.open_sftp() as sftp:
            print(f"Uploading {archive.name} ({archive.stat().st_size} bytes)")
            sftp.put(str(archive), remote_archive)

        run(client, f"tar -xzf {shlex.quote(remote_archive)} -C {shlex.quote(REMOTE_ROOT)}")
        run(client, f"cd {shlex.quote(REMOTE_ROOT)} && docker compose config --quiet")
        run(client, "docker commit bigscreen-nginx bigscreen-nginx:pre-audit-" + timestamp)
        run(client, f"cd {shlex.quote(REMOTE_ROOT)} && docker compose build backend", timeout=1200)
        run(
            client,
            f"cd {shlex.quote(REMOTE_ROOT)} && docker compose up -d backend --remove-orphans",
        )

        run(
            client,
            f"docker cp {shlex.quote(REMOTE_ROOT)}/frontend/nginx.conf "
            "bigscreen-nginx:/etc/nginx/conf.d/default.conf",
        )
        run(
            client,
            f"docker cp {shlex.quote(REMOTE_ROOT)}/frontend/bigscreen-assets/bigscreen-index-v5.html "
            "bigscreen-nginx:/usr/share/nginx/html/index.html",
        )
        run(
            client,
            f"docker cp {shlex.quote(REMOTE_ROOT)}/frontend/bigscreen-assets/bigscreen-index-v5.html "
            "bigscreen-nginx:/usr/share/nginx/html/bigscreen-index-v5.html",
        )
        run(
            client,
            f"docker cp {shlex.quote(REMOTE_ROOT)}/frontend/bigscreen-assets/bigscreen-enhancements-v5.js "
            "bigscreen-nginx:/usr/share/nginx/html/assets/bigscreen-enhancements-v5.js",
        )
        run(
            client,
            f"docker cp {shlex.quote(REMOTE_ROOT)}/frontend/bigscreen-assets/index-C5sOsRGW-api-usage-incremental-v1.js "
            "bigscreen-nginx:/usr/share/nginx/html/assets/index-C5sOsRGW-api-usage-incremental-v1.js",
        )
        run(client, "docker exec bigscreen-nginx nginx -t")
        run(client, "docker exec bigscreen-nginx nginx -s reload")
        run(client, "docker commit bigscreen-nginx bigscreen-nginx:latest")

        run(
            client,
            "for attempt in 1 2 3 4 5 6 7 8 9 10; do "
            "docker exec bigscreen-nginx wget -qO- http://backend:8000/health && exit 0; "
            "sleep 2; done; exit 1",
            timeout=60,
        )
        run(client, "curl -fsS --max-time 10 http://localhost:9000/api/tencent/config")
        run(client, "curl -fsS --max-time 10 http://localhost:9000/api/dashboard >/dev/null")
        run(client, "docker exec bigscreen-nginx nginx -T >/dev/null")
        run(client, f"cd {shlex.quote(REMOTE_ROOT)} && docker compose ps")
        run(client, f"cd {shlex.quote(REMOTE_ROOT)} && docker compose logs --tail 30 backend")
        print(f"\nDeployment complete. Source backup: {backup}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
