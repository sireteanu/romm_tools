"""Shared fixtures: `romm` = a RomM client talking to the mock RomM (tests/mock_romm.py) over real HTTP."""
import socket
import threading
import time

import pytest
import uvicorn

from src.romm_client import RommClient
from tests import mock_romm


@pytest.fixture
def romm(tmp_path):
    mock_romm.S.__init__()
    mock_romm.seed_demo()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(mock_romm.app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    client = RommClient(romm_url=f"http://127.0.0.1:{port}", auth_type="api", romm_api_token="x")
    yield client
    server.should_exit = True
    t.join(timeout=5)


