"""Tests for agent-handoff."""

from __future__ import annotations

import pytest

from agent_handoff import HandoffBuilder, HandoffPayload, HandoffStatus, HandoffStore

# ---------------------------------------------------------------------------
# HandoffStatus
# ---------------------------------------------------------------------------


def test_status_values():
    assert HandoffStatus.PENDING.value == "pending"
    assert HandoffStatus.COMPLETED.value == "completed"
    assert HandoffStatus.PARTIAL.value == "partial"
    assert HandoffStatus.FAILED.value == "failed"
    assert HandoffStatus.SKIPPED.value == "skipped"


def test_status_from_string():
    assert HandoffStatus("completed") is HandoffStatus.COMPLETED


# ---------------------------------------------------------------------------
# HandoffPayload — construction
# ---------------------------------------------------------------------------


def test_payload_minimal():
    p = HandoffPayload(task="do thing", status=HandoffStatus.COMPLETED)
    assert p.task == "do thing"
    assert p.status is HandoffStatus.COMPLETED
    assert p.result is None
    assert p.context == {}
    assert p.next_step is None
    assert p.metadata == {}


def test_payload_full():
    p = HandoffPayload(
        task="search",
        status=HandoffStatus.PARTIAL,
        result=["hit1"],
        context={"page": 1},
        next_step="fetch page 2",
        metadata={"duration_ms": 120},
        timestamp=1000.0,
    )
    assert p.result == ["hit1"]
    assert p.context == {"page": 1}
    assert p.next_step == "fetch page 2"
    assert p.metadata == {"duration_ms": 120}
    assert p.timestamp == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# HandoffPayload — properties
# ---------------------------------------------------------------------------


def test_succeeded_true():
    p = HandoffPayload(task="t", status=HandoffStatus.COMPLETED)
    assert p.succeeded is True


def test_succeeded_false():
    p = HandoffPayload(task="t", status=HandoffStatus.PARTIAL)
    assert p.succeeded is False


def test_failed_true():
    p = HandoffPayload(task="t", status=HandoffStatus.FAILED)
    assert p.failed is True


def test_failed_false():
    p = HandoffPayload(task="t", status=HandoffStatus.COMPLETED)
    assert p.failed is False


def test_is_terminal_completed():
    p = HandoffPayload(task="t", status=HandoffStatus.COMPLETED)
    assert p.is_terminal is True


def test_is_terminal_failed():
    p = HandoffPayload(task="t", status=HandoffStatus.FAILED)
    assert p.is_terminal is True


def test_is_terminal_skipped():
    p = HandoffPayload(task="t", status=HandoffStatus.SKIPPED)
    assert p.is_terminal is True


def test_is_terminal_pending():
    p = HandoffPayload(task="t", status=HandoffStatus.PENDING)
    assert p.is_terminal is False


def test_is_terminal_partial():
    p = HandoffPayload(task="t", status=HandoffStatus.PARTIAL)
    assert p.is_terminal is False


# ---------------------------------------------------------------------------
# HandoffPayload — repr
# ---------------------------------------------------------------------------


def test_repr_short_task():
    p = HandoffPayload(task="short task", status=HandoffStatus.COMPLETED)
    assert "short task" in repr(p)
    assert "completed" in repr(p)


def test_repr_long_task_truncated():
    long_task = "x" * 50
    p = HandoffPayload(task=long_task, status=HandoffStatus.PENDING)
    assert "..." in repr(p)


# ---------------------------------------------------------------------------
# HandoffPayload — serialisation
# ---------------------------------------------------------------------------


def test_to_dict_round_trip():
    p = HandoffPayload(
        task="search emails",
        status=HandoffStatus.COMPLETED,
        result={"count": 3},
        context={"user": "alice"},
        next_step="reply",
        metadata={"ms": 50},
        timestamp=999.0,
    )
    d = p.to_dict()
    assert d["task"] == "search emails"
    assert d["status"] == "completed"
    assert d["result"] == {"count": 3}
    assert d["context"] == {"user": "alice"}
    assert d["next_step"] == "reply"
    assert d["metadata"] == {"ms": 50}
    assert d["timestamp"] == pytest.approx(999.0)


def test_from_dict_round_trip():
    original = HandoffPayload(
        task="t",
        status=HandoffStatus.PARTIAL,
        result=[1, 2, 3],
        context={"k": "v"},
        next_step="next",
        metadata={"x": 1},
        timestamp=42.0,
    )
    restored = HandoffPayload.from_dict(original.to_dict())
    assert restored.task == original.task
    assert restored.status is original.status
    assert restored.result == original.result
    assert restored.context == original.context
    assert restored.next_step == original.next_step
    assert restored.metadata == original.metadata
    assert restored.timestamp == pytest.approx(original.timestamp)


def test_from_dict_missing_optional_fields():
    p = HandoffPayload.from_dict({"task": "t", "status": "failed"})
    assert p.result is None
    assert p.context == {}
    assert p.next_step is None
    assert p.metadata == {}


def test_to_dict_copies_context():
    p = HandoffPayload(task="t", status=HandoffStatus.COMPLETED, context={"a": 1})
    d = p.to_dict()
    d["context"]["a"] = 999
    assert p.context["a"] == 1  # original not mutated


# ---------------------------------------------------------------------------
# HandoffBuilder
# ---------------------------------------------------------------------------


def test_builder_minimal():
    p = HandoffPayload.builder("do thing").build()
    assert p.task == "do thing"
    assert p.status is HandoffStatus.PENDING  # default


def test_builder_status():
    p = HandoffPayload.builder("t").status(HandoffStatus.COMPLETED).build()
    assert p.status is HandoffStatus.COMPLETED


def test_builder_result():
    p = HandoffPayload.builder("t").result({"x": 1}).build()
    assert p.result == {"x": 1}


def test_builder_context():
    p = HandoffPayload.builder("t").context({"a": 1}).build()
    assert p.context == {"a": 1}


def test_builder_add_context():
    p = HandoffPayload.builder("t").context({"a": 1}).add_context("b", 2).build()
    assert p.context == {"a": 1, "b": 2}


def test_builder_next_step():
    p = HandoffPayload.builder("t").next_step("do X next").build()
    assert p.next_step == "do X next"


def test_builder_metadata():
    p = HandoffPayload.builder("t").metadata({"ms": 10}).build()
    assert p.metadata == {"ms": 10}


def test_builder_add_metadata():
    p = HandoffPayload.builder("t").metadata({"a": 1}).add_metadata("b", 2).build()
    assert p.metadata == {"a": 1, "b": 2}


def test_builder_is_fluent():
    """All builder methods return the builder for chaining."""
    b = HandoffPayload.builder("t")
    assert b.status(HandoffStatus.COMPLETED) is b
    assert b.result(None) is b
    assert b.context({}) is b
    assert b.add_context("k", "v") is b
    assert b.next_step("step") is b
    assert b.metadata({}) is b
    assert b.add_metadata("k", "v") is b


def test_builder_uses_clock():
    b = HandoffBuilder("t", clock=lambda: 12345.0)
    p = b.build()
    assert p.timestamp == pytest.approx(12345.0)


def test_builder_build_copies_context():
    b = HandoffPayload.builder("t").context({"a": 1})
    p = b.build()
    p.context["a"] = 999
    p2 = b.build()
    assert p2.context["a"] == 1  # builder not affected


# ---------------------------------------------------------------------------
# HandoffStore — basic
# ---------------------------------------------------------------------------


def test_store_empty():
    store = HandoffStore()
    assert store.count() == 0
    assert len(store) == 0
    assert store.latest() is None


def test_store_add():
    store = HandoffStore()
    p = HandoffPayload(task="t", status=HandoffStatus.COMPLETED)
    store.add(p)
    assert store.count() == 1


def test_store_latest():
    store = HandoffStore()
    p1 = HandoffPayload(task="first", status=HandoffStatus.COMPLETED)
    p2 = HandoffPayload(task="second", status=HandoffStatus.FAILED)
    store.add(p1)
    store.add(p2)
    assert store.latest() is p2


def test_store_all_returns_copy():
    store = HandoffStore()
    p = HandoffPayload(task="t", status=HandoffStatus.COMPLETED)
    store.add(p)
    copy = store.all()
    copy.clear()
    assert store.count() == 1


def test_store_by_status():
    store = HandoffStore()
    store.add(HandoffPayload(task="a", status=HandoffStatus.COMPLETED))
    store.add(HandoffPayload(task="b", status=HandoffStatus.FAILED))
    store.add(HandoffPayload(task="c", status=HandoffStatus.COMPLETED))
    completed = store.by_status(HandoffStatus.COMPLETED)
    assert len(completed) == 2
    assert all(p.status is HandoffStatus.COMPLETED for p in completed)


def test_store_by_status_empty():
    store = HandoffStore()
    store.add(HandoffPayload(task="t", status=HandoffStatus.COMPLETED))
    assert store.by_status(HandoffStatus.FAILED) == []


def test_store_clear():
    store = HandoffStore()
    store.add(HandoffPayload(task="t", status=HandoffStatus.COMPLETED))
    store.clear()
    assert store.count() == 0


def test_store_repr():
    store = HandoffStore()
    assert "HandoffStore" in repr(store)


# ---------------------------------------------------------------------------
# HandoffStore — add_new
# ---------------------------------------------------------------------------


def test_store_add_new_defaults():
    store = HandoffStore(clock=lambda: 5.0)
    p = store.add_new("do thing")
    assert p.task == "do thing"
    assert p.status is HandoffStatus.COMPLETED
    assert p.timestamp == pytest.approx(5.0)
    assert store.count() == 1


def test_store_add_new_with_result():
    store = HandoffStore(clock=lambda: 0.0)
    p = store.add_new("search", result=["hit"])
    assert p.result == ["hit"]


def test_store_add_new_with_context():
    store = HandoffStore(clock=lambda: 0.0)
    p = store.add_new("t", context={"k": "v"})
    assert p.context == {"k": "v"}


def test_store_add_new_with_status():
    store = HandoffStore(clock=lambda: 0.0)
    p = store.add_new("t", HandoffStatus.FAILED)
    assert p.status is HandoffStatus.FAILED


def test_store_add_new_returns_payload():
    store = HandoffStore(clock=lambda: 0.0)
    p = store.add_new("t")
    assert store.latest() is p
