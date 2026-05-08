# Domain `schemas` package

Pydantic models for HTTP request/response bodies, workflow graph nodes (`GraphNode` union), node outputs, and run DTOs. **Import from the package root** so call sites stay stable:

```python
from app.domain.schemas import GraphNode, WorkflowRunResult, …
```

Submodules (`graph_nodes.py`, `outputs.py`, etc.) group related models; re-exports live in `__init__.py`.

## Rename from `types`

This package was previously named `app.domain.types`. It was **renamed to `schemas`** because a project submodule called `types` shadows Python’s stdlib [`types`](https://docs.python.org/3/library/types.html) module and breaks **mypy** (and confuses tooling that assumes `import types` refers to the standard library).

Use **`app.domain.schemas`** for all new code. Do not reintroduce a package named `types` under `app/domain/`.

More context: [docs/ARCHITECTURE.md](../../../../docs/ARCHITECTURE.md) (domain Pydantic models / SSOT) and [CHANGELOG.md](../../../../CHANGELOG.md).
