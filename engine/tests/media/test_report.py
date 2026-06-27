from __future__ import annotations

from devboost.media.report import FakeReporter, Reporter


def test_fake_reporter_records_steps_and_summaries() -> None:
    r = FakeReporter()
    r.step("Ventoy installed")
    r.summary("done")
    assert r.steps == ["Ventoy installed"]
    assert r.summaries == ["done"]


def test_fake_reporter_progress_records_label_total_and_advances() -> None:
    r = FakeReporter()
    with r.progress("fedora-44.iso", 100) as advance:
        advance(40)
        advance(60)
    assert r.progress_calls == [("fedora-44.iso", 100)]
    assert r.advances == [40, 60]


def test_fake_reporter_satisfies_protocol() -> None:
    assert isinstance(FakeReporter(), Reporter)
