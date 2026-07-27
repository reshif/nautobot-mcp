# MCP Engineering Standard

**The shared testbed for every MCP server we build.** Read this before starting a new
server, review against it before shipping, and score with the rubric in Part 1.

Grounded in the official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
docs (`py.sdk.modelcontextprotocol.io` — Building Servers, Protocol, Testing) and the patterns
proven across `meraki-mcp` and `nautobot-mcp`.

> **How to use this doc**
> 1. **New server:** build to Part 3 (architecture) + Part 4 (LLM affordances); tick Part 5 before calling it done.
> 2. **Review:** score with Part 1; each dimension links to the reference in Parts 2–4.
> 3. **Target:** ≥ 90/100 weighted. Anything below 3/5 on a dimension is a release blocker unless consciously waived.

---

## Part 1 — The Rubric (scorecard)

Score each dimension 1–5, multiply by weight, sum to 100. Record evidence (file:line) per score.

| # | Dimension | Wt | 1 (poor) | 3 (adequate) | 5 (excellent) |
|---|-----------|----|----------|--------------|---------------|
| 1 | **Idiomatic SDK construction** | 12 | Ad-hoc wiring, no lifespan | FastMCP + basic lifespan | Typed lifespan DI, transports configurable, ToolAnnotations, one justified global at most |
| 2 | **Tool naming & descriptions** | 14 | `do_stuff(q)`, terse | Clear names, one-line docs | Semantic names, intent + "Use for '…'" + cross-refs to sibling tools |
| 3 | **Parameter schema clarity** | 12 | Bare `x: str`, no guidance | Types + some prose | Every param `Annotated[T, Field(description=…)]`, `Literal`/enum for closed sets |
| 4 | **Structured output / contract** | 12 | Returns raw strings | Returns dict | Returns `BaseModel` → real `outputSchema` + `structuredContent`; one uniform contract; size-budgeted |
| 5 | **Error handling & self-correction** | 10 | Exceptions leak to client | Caught, generic message | Normalized, actionable, ambiguity→candidate choices, never crashes the MCP layer |
| 6 | **Resources** | 6 | None where warranted | Static resources | Titled reference + templates where they add app-driven context |
| 7 | **Prompts** | 6 | None | A few templates | Titled, orchestrate the tools, encode house rules |
| 8 | **Completions** | 6 | None | — | `@mcp.completion()` on prompt args / resource-template params, backed by live reference data |
| 9 | **Context features (log/progress/elicit)** | 6 | Silent long tools | Some logging | Multi-call tools report progress; elicitation used where interaction helps |
| 10 | **Testing against the SDK surface** | 10 | Only manual | Logic unit tests | Logic tests **+** in-memory client-session tests asserting schemas/annotations/`structuredContent` |
| 11 | **Architecture & read-only safety** | 6 | Copy-paste, mixed concerns | Some shared helpers | One seam / one contract / one catalog, DRY, read-only annotated, no accidental writes |

**Bands:** ≥90 ship-grade · 75–89 solid, close gaps before scale · 60–74 strong engine, thin LLM-facing affordances · <60 rework.

> Reference scores (nautobot-mcp): **72/100** at first review → **≈94/100** after the P0–P2 roadmap.
> The lift came from the four LLM-facing gaps every inheriting server should close up front:
> - ③ 2→5: `Annotated[T, Field(description=…)]` on all 57 params (+ registrar `include_extras=True`).
> - ⑧ 1→5: `@mcp.completion()` for prompt args, backed by the resolver reference cache.
> - ⑩ 3→5: in-memory `create_connected_server_and_client_session` tests (schemas, annotations, structuredContent, isError, completions, resources, prompts).
> - ⑤ 4→5 / ⑨ 2→4: `isError` on hard failures (structured error kept), progress on fan-out tools.
> Treat those as the default backlog for a new server built on this architecture.

---

## Part 2 — SDK Conformance Reference

What the SDK gives you and how to use it correctly. **Every point here is a place a server can gain or lose rubric points.**

### 2.1 Tools — `@mcp.tool`
- **Schema is the signature.** FastMCP builds the `inputSchema` from type hints — no manual JSON Schema.
- **Decorator params:** `title="…"` (display name), `structured_output=False` (opt out of structured content), `annotations=ToolAnnotations(...)`.
- **Return a Pydantic `BaseModel`** (or `TypedDict`/dataclass/`dict[str,T]`). FastMCP then generates an **`outputSchema`** and returns **`structuredContent`**, validated against it. Primitives get wrapped as `{"result": value}`. ← This is how you earn dimension ④.
- **Parameter descriptions (dimension ③):** annotate each param:
  ```python
  from typing import Annotated
  from pydantic import Field
  def _device(app, device: Annotated[str, Field(description="Device NAME (not ID), e.g. 'ams01-edge-01'")]) -> ToolResult: ...
  ```
  ⚠️ **Gotcha:** if you do signature surgery in a registrar, you MUST call
  `typing.get_type_hints(handler, include_extras=True)`. Without `include_extras=True`,
  `Annotated[...]` metadata is silently stripped and the `Field(description=…)` never reaches the schema.
- **Closed sets → `Literal`:** `group_by: Literal["status","role","location"]` becomes an enum in the schema; the LLM can't pass a bad value.

### 2.2 ToolAnnotations — set them honestly
| Field | Meaning | Set when |
|-------|---------|----------|
| `title` | Human display name | Always |
| `readOnlyHint` | Does not modify state | Every read tool → `True` |
| `idempotentHint` | Same result on repeat | GET-style tools → `True` |
| `destructiveHint` | Potentially harmful | Any delete/overwrite → `True` |
| `openWorldHint` | Talks to external systems | API-backed tools → `True` |

House helper:
```python
def ro(title: str) -> ToolAnnotations:
    return ToolAnnotations(title=title, readOnlyHint=True, idempotentHint=True, openWorldHint=True)
```

### 2.3 Error handling — three SDK options + our policy
1. `raise ToolError("actionable message")` — expected conditions; becomes an error result.
2. Unhandled exception — auto-caught and converted.
3. Return `CallToolResult(content=[...], isError=True, _meta={...})` — full control, incl. `isError` and client-only `_meta`.

**Our policy (dimension ⑤):** handlers never raise across the MCP layer. A registrar catches everything and returns the uniform contract with a structured `error{kind,message,choices}`. Ambiguity returns **candidate choices** so the LLM self-corrects. Decide consciously whether hard failures should also flip `isError` (spec channel) — LLM agents read our summary, but non-LLM orchestrators key off `isError`.

### 2.4 Resources & templates
- For data with **no side effects / little computation** (REST-GET-like). Expose slow-changing reference data (roles, statuses, sites).
- `@mcp.resource("scheme://path", title="…", mime_type="…")`; `{param}` in the URI makes it a **template** (params become function args).
- Binary: return `bytes` + `mime_type` → auto base64.
- Resource functions can't easily take `Context` in current FastMCP — use a process-scoped app holder if they need shared state (one justified global).

### 2.5 Prompts
- `@mcp.prompt(title="…")`; return a string or `list[base.Message]`.
- Encode **house rules once** (read-only, names-not-IDs, summary-first) and have prompts **orchestrate the tools** by name. Give prompt args `Field` descriptions too.

### 2.6 Completions (dimension ⑧ — commonly skipped, easy win)
`@mcp.completion()` supplies suggestions for prompt args and resource-template params. Back it with cached reference data (e.g., location/role names) so clients autocomplete real values. Context-aware completions can use already-filled args.

### 2.7 Context — logging, progress, elicitation
A `ctx: Context[ServerSession, AppContext]` param unlocks:
- `await ctx.debug/info/warning/error(...)` — surface progress on slow calls.
- `await ctx.report_progress(progress, total, message)` — **use in every multi-call/fan-out tool**.
- `await ctx.elicit(message, schema=PydanticModel)` — ask the user for structured input (enums → dropdowns); `ctx.elicit_url(...)` for out-of-band confirmation.
- `ctx.request_context.lifespan_context` — the DI path to your `AppContext`.

> If you abstract `ctx` away behind an `AppContext` (as we do), still thread an **optional progress hook** through it so fan-out tools aren't silent.

### 2.8 Server construction, lifespan, transports
```python
@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    client = build_http_client(settings)          # one shared client
    async with client:
        yield AppContext(gateway=Gateway(client), resolver=Resolver(...), settings=settings)

mcp = FastMCP("name", instructions=_INSTRUCTIONS, lifespan=lifespan, ...)
```
- **Transports:** `stdio` (dev / local clients), `streamable-http` (production; `stateless_http=True, json_response=True` for scale), `sse` (legacy).
- Put **usage instructions** on the server (`instructions=`) — names not IDs, contract shape, what `meta.partial/truncated` mean.

### 2.9 Testing against the SDK surface (dimension ⑩)
Logic tests (call handlers with a fake gateway) are necessary but **not sufficient** — they skip registration, schema generation, and serialization. Add in-memory client-session tests:
```python
from mcp.shared.memory import create_connected_server_and_client_session

async with create_connected_server_and_client_session(mcp, raise_exceptions=True) as session:
    tools = await session.list_tools()            # assert names, annotations, inputSchema, outputSchema
    result = await session.call_tool("x_device", {"device": "ams01"})
    assert result.structuredContent["summary"]    # assert the real serialized shape
```
This is the only thing that covers a custom **registrar** end to end.

---

## Part 3 — Architecture Patterns (our house style, proven)

Every server mirrors these. They are why the reference servers score 5/5 on ①④⑪.

1. **One response contract.** `ToolResult{summary, data, meta, error}` — a Pydantic model so structured output is free. `summary` is one human line (answer first); `data` is projected/trimmed; `meta` carries `scope/count/truncated/partial/warnings/note/elapsed_ms`; `error` is structured. A `Collector` runs sub-fetches so partial data is **declared** (`meta.partial` + warnings), never a silent `None`.
2. **One lifecycle owner (registrar).** Handlers are pure `async def _x(app, ...) -> ToolResult`. One `register_tool()` adapts each: `ctx→app`, whole-tool timeout, exception→`ToolResult`, response-size budget, `elapsed_ms`, one structured log. Registration is one line. *(Registrar does signature surgery — remember `include_extras=True`.)*
3. **One API seam (gateway).** All HTTP through one class: shared client, **concurrency semaphore**, **timeout**, **bounded retry** on transient timeout/502-504, **error normalization** (no raw client exceptions escape), logging. Tools depend on this duck-typed interface → a `FakeGateway` substitutes offline (Dependency Inversion payoff).
4. **One catalog.** A single registry mapping object-type → API path (+ resolution/audit metadata). The generic query tool, resolver, and audit aliases all derive from it — adding a type/app is a one-file edit.
5. **Resolver — names in, IDs never invented.** Turns human strings into objects; exact-then-fuzzy in one place (`lookup()`); ambiguity raises with a **candidate list**. Small reference lists cached with TTL.
6. **Response-size budget.** `enforce_budget` shrinks the largest arrays until `data` fits the agent context; flags `meta.truncated` + a note telling the LLM how to narrow.
7. **Config via `pydantic-settings`.** Env-prefixed, validated, `lru_cache`d. Constrain enums with `Literal` (+ a `mode="before"` validator to normalize case) so bad config fails fast at startup.
8. **Layered coverage (don't wrap every endpoint).** For a big API: **power tools** (generic query + GraphQL + schema introspection) for breadth · **workflow tools** (multi-endpoint, job-driven answers) for value · **sharp purpose tools** for the common intents. This protects LLM tool-selection accuracy.
9. **Read-only by default.** No write tools unless explicitly required; annotate `readOnlyHint=True`; log a warning if TLS verification is ever disabled.
10. **DRY helpers.** One `disp()` (nested-object display), one `filters()` (drop-None param builder), one place for pagination/trimming. Zero copy-pasted helpers across tool modules.

### Module layout (reference)
```
src/<pkg>/
  config.py            # Settings (pydantic-settings)
  context.py           # AppContext dataclass + DI accessor
  server.py            # build_server(), lifespan, instructions
  core/
    catalog.py         # object-type registry (single source of truth)
    gateway.py         # the one HTTP seam
    resolver.py        # names -> objects, ambiguity -> choices
    response.py        # ToolResult / Meta / Collector / enforce_budget
    errors.py          # exception hierarchy -> ErrorKind
    formatting.py      # disp / filters / pick / ref / Trimmer
    observability.py   # logging
  tools/
    _registry.py       # register_tool (the one lifecycle owner)
    _shared.py         # single import surface for tool modules
    <domain>.py        # sharp tools
    workflows.py       # multi-endpoint tools
    optional/          # feature-flagged tools
  resources/  prompts/
tests/
  fakes.py             # FakeGateway (DIP)
  test_*.py            # logic tests + client-session tests
```

---

## Part 4 — Tool Design for LLMs (the affordances that matter)

The engine can be perfect and the server still score low if the LLM can't use it confidently. Optimize for **"fill every parameter, first try, with confidence."**

- **Name for intent**, resource-first: `x_device`, `x_list_devices`, `x_site_report`. Prefix with the product so tools don't collide in multi-server clients.
- **Describe with purpose + trigger + boundaries:** what it does, "Use for '…'", what to pass (NAME vs ID), and which sibling tool to use instead. (See any description in the reference servers.)
- **Every parameter gets a `Field(description=…)`** with an example, and a `Literal`/enum for closed sets. This is dimension ③ and the single highest-ROI LLM improvement.
- **Answer first:** `summary` is a complete one-line answer; `data` is the backing detail. LLMs (and users) read the summary.
- **Project & cap output:** declare fields, compact nested objects to small refs, cap arrays, and budget total size — never dump raw API payloads.
- **Self-correcting errors:** unknown enum → return the valid set as `choices`; ambiguous name → return candidates. The LLM recovers without a human.
- **Prefer one rich call:** offer GraphQL / multi-endpoint workflow tools so the model gets related data together instead of chaining ten calls.

---

## Part 5 — Definition of Done (pre-flight checklist)

**Architecture**
- [ ] One `ToolResult` contract; handlers are pure `_x(app, ...) -> ToolResult`
- [ ] One gateway seam (concurrency + timeout + retry + error normalization)
- [ ] One catalog for object-type/path knowledge
- [ ] Resolver: names→objects, ambiguity→choices; no invented IDs
- [ ] `enforce_budget` on every response; `meta.truncated/partial` honest
- [ ] Config validated via pydantic-settings; enums are `Literal`

**LLM affordances**
- [ ] Every tool: semantic name + purpose/"use for"/cross-ref description
- [ ] Every parameter: `Annotated[T, Field(description=…)]` (+ `Literal` for closed sets)
- [ ] Registrar uses `get_type_hints(..., include_extras=True)`
- [ ] Returns a `BaseModel` → `outputSchema` + `structuredContent` verified
- [ ] `ToolAnnotations`: `readOnlyHint`/`idempotentHint`/`openWorldHint` set honestly
- [ ] Prompts titled + orchestrate tools + encode house rules
- [ ] Completions on prompt args / template params where reference data exists
- [ ] Multi-call tools report progress via Context (or an injected hook)
- [ ] Server `instructions=` explain contract + names-not-IDs

**Safety & quality gates**
- [ ] Read-only unless writes explicitly required; TLS-off logs a warning
- [ ] `pytest` — logic tests **and** in-memory client-session tests (schemas + `structuredContent`)
- [ ] `ruff check` clean
- [ ] `mypy` clean (`check_untyped_defs`, no suppressions)
- [ ] No real tokens committed; `.env` git-ignored, `.env.example` placeholder
- [ ] Rubric scored, evidence recorded, ≥90 or waivers documented

---

## Part 6 — Environment & Ops gotchas (hard-won)

- **Windows Application Control (Smart App Control / WDAC)** can block generated `.exe` console-script shims (OS error 4551) and `_multiprocessing.pyd` (pulled in by uvicorn). **Workarounds:** run `python -m <pkg>` (trusted interpreter) instead of the console script; use **stdio locally, Docker for HTTP**. Default `.env.example` to `stdio`.
- **Console encoding:** Windows `cp1252` chokes on non-ASCII (e.g. `→`) in smoke scripts — `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`. Server JSON is UTF-8; this is only a console concern.
- **Bare-list endpoints:** some APIs return a bare JSON list instead of the paginated envelope — the gateway's `list()` must tolerate both, not each caller.
- **Slow/public demo servers:** keep per-call timeouts tight in smoke scripts; fan-out tools can exceed a 2-min wall — another reason for progress reporting.
- **Pin the SDK** (`mcp>=…`) and keep `uv.lock` current.

---

## Part 7 — Anti-patterns (don't)

- ❌ One tool per API endpoint (wrecks LLM selection) → use the layered coverage strategy.
- ❌ Returning raw API payloads → project, compact, cap, budget.
- ❌ Bare `x: str` parameters → always `Field(description=…)`.
- ❌ Letting exceptions cross the MCP layer → normalize in the registrar.
- ❌ Silent partial results (`None` on sub-fetch failure) → declare via `Collector`/`meta.partial`.
- ❌ Copy-pasted helpers across tool files → one shared helper.
- ❌ Three maps for the same object-type knowledge → one catalog.
- ❌ Testing only handlers → also test through an in-memory client session.
- ❌ Inventing IDs from names → resolve, and return choices when ambiguous.

---

## Part 8 — Decisions log (reasoned defaults for read-only servers)

Deliberate calls made once and reused; revisit only on the stated trigger.

- **`isError` policy.** Set the protocol `isError=True` only for *genuine execution failures*
  (timeout, upstream API error, unexpected exception) by returning a `CallToolResult` whose
  `structuredContent` is still the full `ToolResult` (so the structured error survives — verified
  against the SDK's `convert_result`/output-schema path). Keep `AMBIGUOUS_TARGET` /
  `TARGET_NOT_FOUND` as `isError=False`: the tool ran successfully and is *guiding* the caller.
  *Trigger to revisit:* a client that treats any structured error as success.
- **Elicitation vs choices.** Do **not** use `ctx.elicit` for disambiguation on a read-only,
  LLM-facing server. Return candidate `choices` in the structured error instead — universally
  supported and self-correcting for agents, with no dependency on the optional elicitation
  capability and no coupling of the resolver to `ctx`. *Trigger to revisit:* a write-capable
  server (confirmation flows) or a confirmed interactive elicitation-capable client.
- **Injected params.** Cross-cutting handles a handler may need (e.g. `progress`) are *injected*
  by the registrar and stripped from the public input schema (convention: reserved parameter
  names), so tools stay pure `(app, …)` and the schema shows only real user arguments.
- **4xx is self-correction, 5xx is failure.** Classify upstream `400/422` (unknown filter, bad
  value) as a self-correcting `INVALID_INPUT` (`isError=False`) that returns the *valid* options
  — never a hard failure. Reserve the `isError` flag for `5xx`/timeout/unexpected. A validation
  error that only says "wrong" is half a tool; a top-notch tool says "wrong — here are the right ones."
- **Uniform list envelope + cursor.** Every list-shaped tool returns `{kind, count, items}` (+
  `offset`/`next_offset`), so an agent extracts and *paginates* every list the same way. Detail
  and aggregation tools keep their own shape. Expose `id` in list items.
- **Surface the filter vocabulary.** A generic query tool is only usable if the model can discover
  valid filters. Curate common filters per type and return them on rejection; have the generic tool
  *defer to sharp, typed tools* where they exist (say so in its description).

---

*Living document. When a new server teaches us something, add it here first — this is the testbed every MCP builds toward.*
