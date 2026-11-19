"""Start a fake upstream and the real MCP server (as a subprocess) on free ports."""
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx2
import pytest
import uvicorn

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import fake_upstream  # noqa: E402

TOKEN = "test-mcp-token-0123456789abcdef"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_healthy(url: str, proc: subprocess.Popen | None = None) -> None:
    for _ in range(100):
        if proc and proc.poll() is not None:
            raise RuntimeError(f"server exited early:\n{proc.stdout.read()}")
        try:
            if httpx2.get(url, timeout=1).status_code < 500:
                return
        except httpx2.RequestError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"{url} never came up")


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
def upstream_url():
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(fake_upstream.app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    _wait_healthy(f"{base}/_requests")
    yield base
    server.should_exit = True
    thread.join(5)


class McpProcess:
    def __init__(self, upstream: str, **env_overrides: str):
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        env = {**os.environ, "API_URL": f"{upstream}/api/v1", "API_KEY": fake_upstream.API_KEY,
               "MCP_TOKEN": TOKEN, "UPSTREAM_TIMEOUT_SECONDS": "1", "RATE_LIMIT_PER_MINUTE": "1000",
               "PUBLIC_HOST": "", **env_overrides}
        self.log_path = ROOT / ".pytest-server-logs" / f"mcp-{self.port}.log"
        self.log_path.parent.mkdir(exist_ok=True)
        self._log = open(self.log_path, "w")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1",
             "--port", str(self.port), "--no-access-log"],
            cwd=ROOT, env=env, stdout=self._log, stderr=subprocess.STDOUT, text=True,
        )
        _wait_healthy(f"{self.url}/health")

    def logs(self) -> str:
        self._log.flush()
        return self.log_path.read_text()

    def stop(self) -> None:
        self.proc.terminate()
        self.proc.wait(5)
        self._log.close()


@pytest.fixture(scope="session")
def mcp_server(upstream_url):
    server = McpProcess(upstream_url)
    yield server
    server.stop()


@pytest.fixture
def make_server(upstream_url):
    started = []

    def factory(**env):
        s = McpProcess(upstream_url, **env)
        started.append(s)
        return s
    yield factory
    for s in started:
        s.stop()
