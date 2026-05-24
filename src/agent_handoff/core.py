"""Structured context handoff payload between AI agents.

When an agent completes a task (or partially completes it) and needs to pass
state to another agent, it creates a :class:`HandoffPayload` and passes it
along.  The receiving agent reads the payload to understand what was done,
what state to start from, and what to do next.

:class:`HandoffBuilder` provides a fluent construction API.
:class:`HandoffStore` is an append-only log of handoffs for inspection and
replay.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class HandoffStatus(str, Enum):
    """Completion status of the handing-off agent's task.

    Values are lowercase strings so they round-trip cleanly through JSON.
    """

    PENDING = "pending"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class HandoffPayload:
    """A structured context object passed from one agent to another.

    Attributes:
        task: Human-readable description of the task that was performed.
        status: Outcome of the task.
        result: The primary output of the task (any JSON-serialisable value).
        context: Arbitrary key/value pairs the receiving agent should know.
        next_step: Instructions for the receiving agent, if any.
        metadata: Extra data not part of the primary result or context.
        timestamp: Unix timestamp of creation (injected by the builder).
    """

    task: str
    status: HandoffStatus
    result: Any = None
    context: dict[str, Any] = field(default_factory=dict)
    next_step: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def succeeded(self) -> bool:
        """``True`` when status is :attr:`HandoffStatus.COMPLETED`."""
        return self.status is HandoffStatus.COMPLETED

    @property
    def failed(self) -> bool:
        """``True`` when status is :attr:`HandoffStatus.FAILED`."""
        return self.status is HandoffStatus.FAILED

    @property
    def is_terminal(self) -> bool:
        """``True`` for statuses that indicate the task will not continue."""
        return self.status in (
            HandoffStatus.COMPLETED,
            HandoffStatus.FAILED,
            HandoffStatus.SKIPPED,
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "task": self.task,
            "status": self.status.value,
            "result": self.result,
            "context": dict(self.context),
            "next_step": self.next_step,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HandoffPayload:
        """Reconstruct a :class:`HandoffPayload` from a plain dict."""
        return cls(
            task=data["task"],
            status=HandoffStatus(data["status"]),
            result=data.get("result"),
            context=dict(data.get("context") or {}),
            next_step=data.get("next_step"),
            metadata=dict(data.get("metadata") or {}),
            timestamp=float(data.get("timestamp", 0.0)),
        )

    # ------------------------------------------------------------------
    # Builder factory
    # ------------------------------------------------------------------

    @classmethod
    def builder(cls, task: str) -> HandoffBuilder:
        """Return a :class:`HandoffBuilder` pre-seeded with *task*."""
        return HandoffBuilder(task)

    def __repr__(self) -> str:
        preview = self.task[:40] + "..." if len(self.task) > 40 else self.task
        return f"HandoffPayload(task={preview!r}, status={self.status.value!r})"


class HandoffBuilder:
    """Fluent builder for :class:`HandoffPayload`.

    Args:
        task: The task description (required).

    Example::

        payload = (
            HandoffPayload.builder("summarize inbox")
            .status(HandoffStatus.COMPLETED)
            .result({"summary": "3 new emails"})
            .context({"user": "alice"})
            .next_step("Reply to the first email")
            .build()
        )
    """

    def __init__(self, task: str, *, clock: Callable[[], float] | None = None) -> None:
        self._task = task
        self._status: HandoffStatus = HandoffStatus.PENDING
        self._result: Any = None
        self._context: dict[str, Any] = {}
        self._next_step: str | None = None
        self._metadata: dict[str, Any] = {}
        self._clock: Callable[[], float] = clock if clock is not None else time.time

    def status(self, status: HandoffStatus) -> HandoffBuilder:
        """Set the completion status."""
        self._status = status
        return self

    def result(self, value: Any) -> HandoffBuilder:
        """Set the primary result."""
        self._result = value
        return self

    def context(self, ctx: dict[str, Any]) -> HandoffBuilder:
        """Set (replace) the context dict."""
        self._context = dict(ctx)
        return self

    def add_context(self, key: str, value: Any) -> HandoffBuilder:
        """Add or update a single context key."""
        self._context[key] = value
        return self

    def next_step(self, instruction: str) -> HandoffBuilder:
        """Set the next-step instruction for the receiving agent."""
        self._next_step = instruction
        return self

    def metadata(self, meta: dict[str, Any]) -> HandoffBuilder:
        """Set (replace) the metadata dict."""
        self._metadata = dict(meta)
        return self

    def add_metadata(self, key: str, value: Any) -> HandoffBuilder:
        """Add or update a single metadata key."""
        self._metadata[key] = value
        return self

    def build(self) -> HandoffPayload:
        """Construct and return the :class:`HandoffPayload`."""
        return HandoffPayload(
            task=self._task,
            status=self._status,
            result=self._result,
            context=dict(self._context),
            next_step=self._next_step,
            metadata=dict(self._metadata),
            timestamp=self._clock(),
        )


class HandoffStore:
    """Append-only log of :class:`HandoffPayload` objects.

    Args:
        clock: Callable returning current Unix time.  Used by
            :meth:`add_new` for timestamping inline-created payloads.

    Example::

        store = HandoffStore()
        store.add(payload)
        latest = store.latest()
    """

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._payloads: list[HandoffPayload] = []
        self._clock: Callable[[], float] = clock if clock is not None else time.time

    def add(self, payload: HandoffPayload) -> None:
        """Append a pre-built payload."""
        self._payloads.append(payload)

    def add_new(
        self,
        task: str,
        status: HandoffStatus = HandoffStatus.COMPLETED,
        *,
        result: Any = None,
        context: dict[str, Any] | None = None,
        next_step: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> HandoffPayload:
        """Build and append a new payload in one call.

        Returns:
            The newly created :class:`HandoffPayload`.
        """
        payload = HandoffPayload(
            task=task,
            status=status,
            result=result,
            context=dict(context or {}),
            next_step=next_step,
            metadata=dict(metadata or {}),
            timestamp=self._clock(),
        )
        self._payloads.append(payload)
        return payload

    def all(self) -> list[HandoffPayload]:
        """Return a copy of all stored payloads in insertion order."""
        return list(self._payloads)

    def latest(self) -> HandoffPayload | None:
        """Return the most-recently added payload, or ``None`` if empty."""
        return self._payloads[-1] if self._payloads else None

    def by_status(self, status: HandoffStatus) -> list[HandoffPayload]:
        """Return all payloads with the given status."""
        return [p for p in self._payloads if p.status is status]

    def count(self) -> int:
        """Total number of stored payloads."""
        return len(self._payloads)

    def clear(self) -> None:
        """Remove all stored payloads."""
        self._payloads.clear()

    def __len__(self) -> int:
        return len(self._payloads)

    def __repr__(self) -> str:
        return f"HandoffStore(count={len(self._payloads)})"
