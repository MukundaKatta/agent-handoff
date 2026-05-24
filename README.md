# agent-handoff

Structured context handoff payload between AI agents.

When one agent finishes a task (or fails partway through) and another agent needs to continue, pass a `HandoffPayload` instead of raw strings. It carries the task description, status, result, context dict, next-step instructions, and metadata.

## Install

```bash
pip install agent-handoff
```

## Quick start

```python
from agent_handoff import HandoffPayload, HandoffStatus, HandoffStore

# Build a payload
payload = (
    HandoffPayload.builder("summarize inbox")
    .status(HandoffStatus.COMPLETED)
    .result({"summary": "3 unread emails about project X"})
    .context({"user_id": "alice", "inbox_count": 3})
    .next_step("Reply to the first email")
    .build()
)

print(payload.succeeded)   # True
print(payload.is_terminal) # True

# Store and retrieve
store = HandoffStore()
store.add(payload)
latest = store.latest()
completed = store.by_status(HandoffStatus.COMPLETED)
```

## API

### `HandoffStatus`

`PENDING` · `COMPLETED` · `PARTIAL` · `FAILED` · `SKIPPED`

### `HandoffPayload`

| Attribute | Type | Description |
|-----------|------|-------------|
| `task` | `str` | Task description |
| `status` | `HandoffStatus` | Outcome |
| `result` | `Any` | Primary output |
| `context` | `dict` | State for the receiving agent |
| `next_step` | `str \| None` | What to do next |
| `metadata` | `dict` | Extra info |
| `timestamp` | `float` | Unix time |

Properties: `succeeded`, `failed`, `is_terminal`

Serialisation: `to_dict()` / `HandoffPayload.from_dict(d)`

### `HandoffBuilder`

```python
HandoffPayload.builder(task)
  .status(HandoffStatus.COMPLETED)
  .result(value)
  .context({"key": "value"})
  .add_context("key", "value")
  .next_step("instruction")
  .metadata({"key": "value"})
  .add_metadata("key", "value")
  .build()  # → HandoffPayload
```

### `HandoffStore`

```python
store = HandoffStore()
store.add(payload)
store.add_new("task", HandoffStatus.COMPLETED, result=..., context=...)
store.latest()          # most recent or None
store.all()             # list[HandoffPayload]
store.by_status(...)    # filtered list
store.count()
store.clear()
```

## License

MIT
