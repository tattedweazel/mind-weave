# Mind Weave — domain model

Reader-oriented vocabulary for how Mind Weave represents **workflows**, **nodes**, and **resources**. This document **stages** depth: it links out to execution mechanics and contributor taxonomies instead of duplicating them.

**Start here if:** you are using the editor and want consistent language for what you are placing on the canvas.

**Contributor placement** (where a *new* node belongs, documented exceptions, “verbs vs grammar”): **[NODE_TAXONOMY.md](NODE_TAXONOMY.md)**.

**Execution semantics** (scheduling, streaming, limits, persistence): **[RUNTIME_ARCHITECTURE.md](RUNTIME_ARCHITECTURE.md)** and **[ARCHITECTURE.md](ARCHITECTURE.md)**.

## Mental model (short)

- **Utilities** reshape data that is already in the workflow (*grammar*).
- **Skills** reach outward to models, HTTP, browsers, speech, integrations (*verbs*).
- **Workflows** compose behavior by wiring nodes together.

See the mnemonic in [NODE_TAXONOMY.md — Short mental model](NODE_TAXONOMY.md#short-mental-model).

## Core graph concepts

### Workflows

A **workflow definition** is a named, versioned graph: **nodes** and **edges** stored as JSON, edited in the **Build** UI. **Start** and **Stop** bound every executable graph; palette **nodes** implement the steps between them.

### Primitives

**Primitives** hold typed values or references (strings, numbers, lists, dictionaries, saved **Structures**, **Documents**, images, RFC3339 datetimes, and other shapes). They are the graph’s **data carriers**.

### Skills

**Skills** perform outward work: LLM calls, HTTP fetches, optional **URL snapshot** capture when installed, speech bridges, calendar/mail integrations, transcription providers, and similar. Inventory-oriented lists live in **[WORKFLOW_TOOL_INVENTORY.md](WORKFLOW_TOOL_INVENTORY.md)** and **[WORKFLOW_SKILLS.md](WORKFLOW_SKILLS.md)**.

### Utilities

**Utilities** transform or validate in-graph data: list/string helpers, HTML parsing, validation against **Structures**, document load/upsert helpers (including Mind Weave’s own **Document** resource — still modeled as utilities per [NODE_TAXONOMY.md — Exceptions](NODE_TAXONOMY.md#exceptions-you-will-see-in-this-codebase)), **Add to List** for loop-scoped accumulation, and similar.

### Controls

**Controls** implement branching, comparison, iteration, boolean combination, and **Try / Catch** regions. They decide **which paths run**, not only what values flow.

### Nested composition

**Workflow** nodes reference another saved definition. **Custom Skills** use the same composition mechanism with **Expose as Custom Skill**. Product-oriented detail: [MIND_WEAVE_ONE_PAGE.md](MIND_WEAVE_ONE_PAGE.md).

## Resources and configuration

### Users

Authenticated accounts drive ownership of workflows, runs, and settings. The bundled SPA uses HttpOnly cookies; API clients may use `Authorization: Bearer`. Bootstrap and local-dev auth notes: [backend/README.md — Important notes on authentication](../backend/README.md#important-notes-on-authentication).

### Personas

**Personas** store reusable system prompts and optional default model selection. Nodes such as **Simple LLM Call** can reference them instead of inlining full prompt text.

### Structures

**Structures** are saved **JSON Schema** documents used to constrain or interpret model and utility outputs. Attaching a structure to an LLM step steers **typed** dictionary output where supported.

### Palettes

**Workflow palettes** map palette **handles** to editor colors for canvas readability. Effective colors resolve server-side (**`GET /api/v1/palettes/resolve`**: workflow palette → user preference → default). Palette authoring and import/export: [frontend/README.md](../frontend/README.md).

Canonical keys and SSOT contracts: [ARCHITECTURE.md — Single sources of truth](ARCHITECTURE.md#single-sources-of-truth).

### Documents

**Documents** are first-class stored text resources (Markdown, JSON, or hybrid content) surfaced in **Manage Documents** and referenced from **Document** primitives and related utilities. See **Resource-backed primitives** in [ARCHITECTURE.md](ARCHITECTURE.md).

## Related surfaces

- **Workspace** — Companion chat and staged workflow capabilities using the same executor for confirmed runs. **[WORKSPACE.md](WORKSPACE.md)**.
- **Sandbox** — Board-driven tick simulation; creatures with per-creature workflows — **[SANDBOX.md](SANDBOX.md)**, **[BOARDS.md](BOARDS.md)**.

## Where to go next

| Question | Doc |
|----------|-----|
| How does a run stream to the UI and persist? | [RUNTIME_ARCHITECTURE.md](RUNTIME_ARCHITECTURE.md) |
| Layers, SSOT files, adding a node type? | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Where should my *new* node go in the taxonomy? | [NODE_TAXONOMY.md](NODE_TAXONOMY.md) |
| Operations, retention, debugging | [OPERATIONS.md](OPERATIONS.md) |
