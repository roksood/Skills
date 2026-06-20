# Trace spec — full field reference

The spec is one JSON object. `assets/example_trace.json` is a complete example.
This file documents every field. Required fields are marked **required**; all
others are optional and the renderer degrades cleanly when they're missing.

## Top level

```
{
  "project":   { ... },     // orientation header
  "layers":    [ ... ],     // the color-coded layers used by steps
  "use_cases": [ ... ],     // required — the traced flows
  "objects":   [ ... ]      // optional — curated objects index (else auto-derived)
}
```

## project

| Field       | Type   | Notes |
|-------------|--------|-------|
| `name`      | string | **required.** Shown as the page title and header. |
| `language`  | string | e.g. "Python". Rendered as a badge. |
| `framework` | string | e.g. "FastAPI". Rendered as a badge. |
| `summary`   | string | One short paragraph: what the app is for. |

## layers

An array defining the layers your steps reference. Each step's `layer` field
points at one of these `id`s, and the renderer colors the step accordingly.

| Field   | Type   | Notes |
|---------|--------|-------|
| `id`    | string | **required.** Short id used by steps (e.g. `service`). |
| `label` | string | Human label shown in the legend (e.g. "Service / business logic"). |
| `color` | string | One of: `blue purple teal amber coral pink green red gray`. |

Keep the set small (3–5 is ideal) and consistent across the whole spec. A good
default for a web API is route / service / data / security / external.

## use_cases

The heart of the spec. Each is one flow traced end to end.

| Field     | Type   | Notes |
|-----------|--------|-------|
| `id`      | string | **required.** Short, url-safe, unique (e.g. `login`). Used for cross-links. |
| `name`    | string | **required.** Plain-English flow name ("A user logs in with email and password"). |
| `trigger` | string | What kicks it off, in monospace (e.g. `POST /auth/login`, `CLI: import users`). |
| `summary` | string | Optional one-liner shown under the heading. |
| `steps`   | array  | **required.** Ordered steps (see below). |

## steps

Each step is one meaningful hop in the call path.

| Field      | Type        | Notes |
|------------|-------------|-------|
| `task`     | string      | **required.** What happens, plain English ("Check the password"). |
| `n`        | int/string  | Step number shown in the badge. If omitted, the renderer numbers by position. |
| `object`   | string      | The class/function doing it (`PasswordHasher.verify()`). Reuse the *exact* same string across use cases for the same object so the objects index links them. |
| `location` | string      | `path/from/root.py:LINE`. Must point at real code. Omit if you truly can't pin it — never invent one. |
| `does`     | string      | One behavioral sentence — what the block accomplishes, not its syntax. |
| `layer`    | string      | A `layers[].id`. Drives the step's accent color and the legend. |
| `detail`   | string      | Optional. Shown behind a "Detail" toggle: a fork in the flow, a gotcha, a dynamic-dispatch note, or a short code excerpt. Newlines are preserved. |

## objects (optional)

Provide this only when you want a written `role` for each object. If omitted,
the renderer auto-derives the index from the steps: it groups by the owning
symbol (the class, or the function name for module-level functions), records the
file(s) the object is defined in (from the path portion of step `location`s),
lists the use cases each appears in, and orders by reuse (most-shared first).

| Field        | Type     | Notes |
|--------------|----------|-------|
| `name`       | string   | **required.** The object/class name (matches the owner part of step `object`s). |
| `role`       | string   | One line on what this object is responsible for. |
| `defined_in` | string   | The file(s) the object lives in. Auto-filled from step locations when omitted; set it explicitly to override. |
| `appears_in` | string[] | Use-case `id`s this object participates in. Becomes clickable cross-links. |

**Multi-file objects.** When an object's traced steps point at more than one
file (common with inheritance, mixins, monkey-patching, or partial classes), the
renderer replaces the single-line `defined_in` with a small boxes-and-arrows
file map: the object's primary file (the one with the most traced methods) drawn
as a box of its methods — indented under the filename, the way they nest under a
class in source — with an arrow from each borrowed method to the exact method in
the file that actually supplies it. This is derived
automatically from the steps — you don't supply it. Single-file objects keep the
plain one-line path. Because the locations are where the traced code *runs*, an
inherited method correctly points at the base class's file, not the subclass
declaration — which is usually what you want when learning a flow.

## Rendering reminders

- The renderer is deterministic. Iterate by editing the spec and re-running
  `build_map.py` — never hand-edit the generated HTML.
- All values are HTML-escaped on render, so `<`, `&`, quotes, and code snippets
  in any field are safe.
- The output is one standalone file with no external requests; it works offline
  and can be emailed or committed to the repo as living documentation.
