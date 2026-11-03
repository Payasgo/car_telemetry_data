import json
import uuid

import pytest

from telemetry.cloud_sync import build_cloud_rows


def test_build_cloud_rows_maps_owner_and_local_identity():
    owner = str(uuid.uuid4())
    rows = [(17, "2026-11-03T10:00:00Z", "obd", json.dumps({"rpm": 1200}))]
    result = build_cloud_rows(rows, owner)
    assert result == [{
        "origin_id": "local-17",
        "owner_id": owner,
        "created_at": "2026-11-03T10:00:00Z",
        "source": "obd",
        "payload": {"rpm": 1200},
    }]


def test_build_cloud_rows_rejects_invalid_owner_uuid():
    with pytest.raises(ValueError):
        build_cloud_rows([], "not-a-uuid")


def test_build_cloud_rows_rejects_invalid_payload_json():
    with pytest.raises(json.JSONDecodeError):
        build_cloud_rows([(1, "2026-11-03T10:00:00Z", "esp32", "{bad")], str(uuid.uuid4()))
