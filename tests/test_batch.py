import json

from scripts.run_fixture_batch import run


def test_fixture_batch_run_creates_a_report(tmp_path, monkeypatch):
    import scripts.run_fixture_batch as batch
    monkeypatch.setattr(batch, "OUTPUT", tmp_path)
    path = run()
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["fixture_count"] == 8
    assert report["human_ratings"] == "not supplied - no ratings invented"
    assert all("duration_ms" in case for case in report["cases"])
