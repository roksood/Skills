---
name: code-trace-map
description: Map how a codebase works by tracing real use cases through the code, producing an interactive HTML walkthrough for people and a compact markdown digest for agents. Point it at a repo (FastAPI/Python out of the box).
disable-model-invocation: true
---

# Code trace map

## Overview

Produce a use-case execution trace: pick one real thing the program does and
walk it top to bottom, recording for each step the task (plain English), the
object that performs it, where it runs (`file:line`), and what it does.

**Core principle:** behavior lives in the call path, not the imports. Trace what
the program *does*, not how its files are arranged.

This skill is **user-invoked** (run it by name); it won't auto-trigger.

It produces two artifacts from one trace, side by side:
- **For people** — a self-contained interactive HTML page: a use-case switcher,
  layer-colored steps, and an objects index (objects whose code spans files get
  a boxes-and-arrows mini-map).
- **For agents** — a compact markdown digest (`.md`) of the same trace,
  linearized and token-light, so an LLM can grasp the codebase's shape fast.

Both are rendered by `scripts/build_map.py` from one JSON spec; see
`references/spec-schema.md` and `assets/example_trace.json`.

## Workflow

### 1. Orient
Identify language/framework; read the manifest and startup file. Form a
one-paragraph picture of the app → `project.summary`.

### 2. Find entry points
Entry points are the front doors to use cases. For **FastAPI, read
`references/python-fastapi.md`** for exactly what to grep; otherwise see "Other
frameworks." Enumerate every entry point you find.

### 3. STOP — propose use cases, let the user choose (required checkpoint)
List the entry points, named, and ask which 2–3 to trace first. Wait for the
answer before tracing. The code shows what's *possible*; only the user knows
what's *important*, dead, or trivial. Do not trace everything, and do not skip
this step even under "just map it" pressure — tracing the wrong flows wastes far
more time than a 2-minute confirmation.
**Only exception:** the user already named the flows, or explicitly says "you
choose" / "do all."

### 4. Trace each chosen flow
Start at the entry point and follow the real calls inward, reading the code at
each hop. Record one step per meaningful hop. Rules:
- **Verify every `location` by reading it.** Never invent a `file:line`; omit it
  if you can't pin it.
- **`task` is plain English; `does` is behavioral** ("constant-time compare"),
  not syntactic ("calls verify()").
- Collapse trivial passthroughs; keep the 5–10 steps that carry meaning.
- Give each step a `layer`; define a small, consistent set in `layers`.
- One use case = one spine. Note forks or dynamic dispatch in a step's `detail`.
- Reuse the *same* object string across flows so the objects index links them.

### 5. Write the spec
Write a JSON file per the schema below.

### 6. Render
Run the bundled renderer (stdlib only — no install). It lives in this skill, so
call it by its path in the skill directory, **not** relative to the target repo.
It writes the HTML and, alongside it, the markdown digest:
```bash
python3 <this-skill-dir>/scripts/build_map.py trace_spec.json -o code_trace_map.html
# writes code_trace_map.html (people) + code_trace_map.md (agents)
```
Iterate by editing the spec and re-running. Never hand-edit the generated files.

### 7. Present
Give the user both files (via `present_files` if available): the HTML to read,
the `.md` to drop into another agent's context or commit as living docs. Offer to
add flows or deepen any step's `detail`.

## Spec schema (minimal)

Full reference: `references/spec-schema.md`. Worked example:
`assets/example_trace.json`.

```json
{
  "project": { "name": "...", "language": "...", "framework": "...", "summary": "..." },
  "layers": [ { "id": "service", "label": "Service", "color": "purple" } ],
  "use_cases": [ {
    "id": "login", "name": "A user logs in", "trigger": "POST /auth/login",
    "steps": [ {
      "n": 1, "task": "Verify credentials",
      "object": "AuthService.authenticate()",
      "location": "app/services/auth_service.py:88",
      "does": "Looks up the user and checks the password",
      "layer": "service", "detail": "optional"
    } ]
  } ]
}
```

Required: `project.name`; per use case `id`, `name`, `steps`; per step `task`.
Colors: `blue purple teal amber coral pink green red gray`. `objects` is optional
— auto-derived from the steps, including each object's file(s) and the
multi-file map.

## Other frameworks

Only entry-point detection differs: find where the framework registers handlers,
then trace inward. HTTP routes (Flask `@app.route`, Express `app.get`, Spring
`@GetMapping`), CLI commands, job/queue consumers, event handlers. The spec and
renderer are identical everywhere. If the user works in one framework often,
offer to add a `references/<lang>-<framework>.md` modeled on the FastAPI one.

## Quality bar

Before presenting: every `location` points at code you actually read; each `task`
reads clearly to a non-author; the layer coloring makes the cross-layer bounce
visible.
