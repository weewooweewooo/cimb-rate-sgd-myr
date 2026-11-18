import json
from datetime import datetime, timedelta, timezone

import pytest

from db import Database
from models import WiseFee

NOW = datetime(2026, 11, 18, 3, 0, tzinfo=timezone.utc)


def test_user_crud():
    db = Database(":memory:")
    assert db.create_user("1", "Sean")
    assert not db.create_user("1", "Sean")
    assert db.get_user("1").target_rate == 3.1
    assert db.update_user("1", target_rate=3.16, enabled=False)
    assert db.get_user("1").enabled is False
    assert db.get_user("1").target_rate == 3.16
    assert not db.update_user("missing", enabled=True)
    with pytest.raises(ValueError):
        db.update_user("1", bogus=1)


def test_list_users():
    db = Database(":memory:")
    db.create_user("1", "A")
    db.create_user("2", "B")
    assert sorted(u.discord_user_id for u in db.list_users()) == ["1", "2"]


def test_record_rate_only_on_change():
    db = Database(":memory:")
    assert db.record_rate("cimb", 3.17, NOW)
    assert not db.record_rate("cimb", 3.17, NOW + timedelta(minutes=1))
    assert db.record_rate("cimb", 3.18, NOW + timedelta(minutes=2))
    assert db.record_rate("wise", 3.17, NOW)
    assert [r for _, r in db.rates_since("cimb", NOW)] == [3.17, 3.18]
    assert db.rates_since("cimb", NOW)[0][0] == NOW


def test_wise_fee_roundtrip():
    db = Database(":memory:")
    assert db.latest_wise_fee() is None
    db.save_wise_fee(WiseFee(0.53, 0.0025), NOW)
    db.save_wise_fee(WiseFee(0.53, 0.0025), NOW + timedelta(days=1))
    assert db.latest_wise_fee() == WiseFee(0.53, 0.0025)
    db.save_wise_fee(WiseFee(0.60, 0.0026), NOW + timedelta(days=2))
    assert db.latest_wise_fee() == WiseFee(0.60, 0.0026)


def test_meta():
    db = Database(":memory:")
    assert db.get_meta("k") is None
    db.set_meta("k", "v1")
    db.set_meta("k", "v2")
    assert db.get_meta("k") == "v2"


def test_file_db_persists(tmp_path):
    path = tmp_path / "sub" / "rates.db"
    Database(path).create_user("1", "A")
    assert Database(path).get_user("1").name == "A"


def test_import_any_json_name(tmp_path):
    (tmp_path / "sean.json").write_text(json.dumps({
        "discord_user_id": "1", "name": "S", "target_rate": 3.16, "enabled": True,
        "peak_rate": 3.17, "last_alerted_at": "2026-11-17T01:00:00+00:00", "active_days": ["mon"],
    }))
    (tmp_path / "user_2.json").write_text(json.dumps({"discord_user_id": "2", "name": "T"}))
    db = Database(":memory:")
    assert db.import_legacy_configs(tmp_path) == 2
    user = db.get_user("1")
    assert (user.target_rate, user.enabled, user.peak_rate) == (3.16, True, 3.17)
    assert db.get_user("2").target_rate == 3.1
    assert (tmp_path / "sean.json.migrated").exists()
    assert not (tmp_path / "sean.json").exists()


def test_import_skips_malformed(tmp_path):
    (tmp_path / "bad.json").write_text("{not json")
    (tmp_path / "noid.json").write_text("{}")
    assert Database(":memory:").import_legacy_configs(tmp_path) == 0
    assert (tmp_path / "bad.json").exists()


def test_import_is_idempotent(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"discord_user_id": "1", "name": "S"}))
    db = Database(":memory:")
    assert db.import_legacy_configs(tmp_path) == 1
    assert db.import_legacy_configs(tmp_path) == 0
    assert len(db.list_users()) == 1


def test_import_missing_dir(tmp_path):
    assert Database(":memory:").import_legacy_configs(tmp_path / "nope") == 0


def test_prune():
    db = Database(":memory:")
    db.record_rate("cimb", 3.1, NOW - timedelta(days=91))
    db.record_rate("cimb", 3.2, NOW)
    assert db.prune(NOW - timedelta(days=90)) == 1
