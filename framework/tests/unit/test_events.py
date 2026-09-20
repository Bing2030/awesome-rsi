import json

from rsif.observe.events import EventLog, Event


def test_append_and_read(tmp_path):
    log = EventLog(tmp_path / "events.jsonl", clock=lambda: 0.0)
    log.append("run_start", phase="", generation=0, generations=3)
    log.append("proposal", phase="proposal", generation=1, proposal_id="p1")

    events = log.read()
    assert [e.kind for e in events] == ["run_start", "proposal"]
    assert events[0].seq == 1 and events[1].seq == 2
    assert events[1].payload == {"proposal_id": "p1"}
    assert events[1].phase == "proposal"


def test_filter_and_tail(tmp_path):
    log = EventLog(tmp_path / "events.jsonl", clock=lambda: 0.0)
    for i in range(5):
        log.append("eval", generation=i % 2)
    assert len(log.filter(kind="eval")) == 5
    assert len(log.filter(generation=0)) == 3
    assert len(log.tail(2)) == 2


def test_unknown_kind_rejected(tmp_path):
    log = EventLog(tmp_path / "events.jsonl", clock=lambda: 0.0)
    try:
        log.append("bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_seq_continues_across_reopen(tmp_path):
    log = EventLog(tmp_path / "events.jsonl", clock=lambda: 0.0)
    log.append("run_start")
    log2 = EventLog(tmp_path / "events.jsonl", clock=lambda: 0.0)
    e = log2.append("run_end")
    assert e.seq == 2


def test_event_json_roundtrip():
    e = Event(1, 0.0, "accept", "verification", 2, {"proposal_id": "p1"})
    assert Event.from_json(e.to_json()) == e
