import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fastapi.testclient import TestClient

import main

app = main.app

client = TestClient(app)


def test_main_base_endpoint_should_return_ok():
    response = client.get('/')

    assert response.status_code == 200
    assert response.json()["service"] == "GP-DAT — GP Document Processing"
    assert response.json()["version"] == "0.1.0"
