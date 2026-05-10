# Node taxonomy (contributor mental model)

Audience: anyone adding or wiring workflow steps. High-level runtime and execution flow: [RUNTIME_ARCHITECTURE.md](RUNTIME_ARCHITECTURE.md). Implementation and schema details: [ARCHITECTURE.md](ARCHITECTURE.md) and package READMEs.

This is a **guide, not a taxonomy police state**—break the rules deliberately when the product needs it, but explain why in code review.

---

## Short mental model

- **Primitives** hold typed data (or resource references the graph can pass around).
- **Utilities** are *grammar*: reshape data that is already in the workflow boundary.
- **Skills** are *verbs*: act on the outside world (models, HTTP, browsers, speech, integrations).
- **Controls** decide execution flow (branching, retries, loops, boolean logic).
- **Workflow** nodes compose other saved graphs into reusable building blocks.

Mnemonic:

> **Utilities shape information. Skills act upon the world.**

---

## Definitions

### Primitives = typed containers

They hold structured values: text, numbers, booleans, lists, objects, saved **Structures**, **Documents**, **Images**, **Gmail-shaped** message objects, RFC3339 datetimes, and similar.

**Start** and **Stop** frame every executable graph: inputs and return contract. They are not palette “bricks” like String or List, but they complete the mental model for composable graphs.

### Utilities = grammar

**Default expectation:** a utility is a **pure-ish data transform** at the workflow boundary—inputs in, outputs out, no surprise side effects.

Examples: list ↔ string, truncation, dictionary key reads, JSON parse/serialize helpers, basic HTML structure extraction, **`Add to List`** for loop-scoped accumulation, integer math, validation against a **Structure**.

### Skills = verbs

Skills **reach outward**: LLM chat, HTTP from the API host, Playwright URL snapshots, speech bridges, Google mail/calendar, transcription providers, etc.

If the step **depends on the network, OS services, or mutable external systems** to do its job, it is almost certainly a **Skill**.

### Controls = flow

Controls choose **which path runs** (conditionals, comparisons, **Try / Catch**) or **iterate** (**For Loop** / **For Loop End**) or combine booleans (**And** / **Or** / **Xor** / **Not**) for downstream wiring.

### Workflows = composition

A **Workflow** node references another saved definition. Custom Skills are the same mechanism with **Expose as Custom Skill** enabled in the editor—see [MIND_WEAVE_ONE_PAGE.md](MIND_WEAVE_ONE_PAGE.md).

### Editor-only pieces

**Annotation** nodes (**notes**, **regions**) are persisted on the canvas for humans; they never execute. See **Editor-only annotations** in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Exceptions you will see in this codebase

Mind Weave labels **`load_document`** and **`upsert_document`** as **utilities**, not skills, because they manipulate **Mind Weave’s own persisted Document resources** that workflows already treat as typed data—not arbitrary files on disk and not third-party APIs.

Treat them as **“resource grammar with persistence”**:

- Prefer a **utility** when the step’s contract is **read/write Documents (or similar first-party resources)** the editor models as data handles.
- Prefer a **skill** when the step talks to **LLMs, outbound HTTP integrations, OAuth providers, bridges, browsers**, or other **third-party / heavy side-effect** systems.

If a new capability blurs this line (e.g. cloud object storage), default to **Skill** unless the team explicitly adopts it as another first-party resource primitive/utility pair.

---

## Where should my new node go?

1. Does it call an external system, model, API, browser, cloud STT/TTS vendor, or other out-of-process integration? → **Probably a Skill.**
2. Does it only transform or validate data already represented in the workflow (including Documents as workflow resources)? → **Probably a Utility.**
3. Does it decide execution flow (branch, catch, iterate, gates)? → **Probably a Control.**
4. Does it primarily hold or reference a typed value (including saved resources exposed as primitives)? → **Probably a Primitive.**
5. Does it embed a whole subgraph you want reused as one step? → **Workflow node** (possibly **Expose as Custom Skill**).

Still unsure—read [ARCHITECTURE.md](ARCHITECTURE.md#adding-a-workflow-node-type-condensed), then backend and frontend README “Adding a…” sections.
