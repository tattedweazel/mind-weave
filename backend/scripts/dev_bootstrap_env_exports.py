"""Emit bash-evaluable `export` lines for Mind Weave local dev bootstrap (CORS / hosts / SPA API base).

Run from repo root: ``uv run --project backend python backend/scripts/dev_bootstrap_env_exports.py``
"""

from __future__ import annotations

import json
import shlex
import socket


def _detect_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.3)
            s.connect(("8.8.8.8", 80))
            addr = s.getsockname()[0]
            assert isinstance(addr, str)
            return addr
    except OSError:
        return "127.0.0.1"


def main() -> None:
    ip = _detect_lan_ip()
    if ip == "127.0.0.1":
        cors = ["http://localhost:5173", "http://127.0.0.1:5173"]
        trusted = ["localhost", "127.0.0.1", "testserver"]
        frontend = "http://localhost:5173"
        vite_base = "http://127.0.0.1:8000"
    else:
        cors = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            f"http://{ip}:5173",
        ]
        trusted = ["localhost", "127.0.0.1", "testserver", ip]
        frontend = f"http://{ip}:5173"
        vite_base = f"http://{ip}:8000"

    print(f'export BOOTSTRAP_LAN_IP={shlex.quote(ip)}')
    print(f'export CORS_ORIGINS={shlex.quote(json.dumps(cors))}')
    print(f'export TRUSTED_HOSTS={shlex.quote(json.dumps(trusted))}')
    print(f'export FRONTEND_URL={shlex.quote(frontend)}')
    print(f'export VITE_API_BASE={shlex.quote(vite_base)}')


if __name__ == "__main__":
    main()
