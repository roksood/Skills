# Tracing a FastAPI application

FastAPI declares its entry points clearly, which makes it one of the friendlier
frameworks to trace. This file covers where the front doors are and how to
follow a request from the route inward.

## 1. Find the app and its routers

Locate the `FastAPI()` instance — usually in `main.py`, `app.py`, or
`app/main.py`:

```python
app = FastAPI()
```

Then find where routers are mounted, because routes are usually split across
files and attached with `include_router`:

```python
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(orders.router, prefix="/orders")
```

The `prefix` matters — the full path of a route is `prefix + the route's own
path`. Track prefixes so your `trigger` strings (e.g. `POST /auth/login`) are
correct.

## 2. Enumerate the routes (these are your use cases)

Grep across the project for the HTTP method decorators on both `app` and any
`APIRouter` instance:

```
@app.get  @app.post  @app.put  @app.patch  @app.delete
@router.get  @router.post  @router.put  @router.patch  @router.delete
```

Each decorated function is one entry point. The decorator gives you the method
and sub-path; combine with the router prefix for the full `trigger`. The
function's name and docstring are good hints for the use-case `name`.

Also check for non-HTTP entry points, which are real use cases too:

- **Lifespan / startup / shutdown** — `@app.on_event("startup")` or the newer
  `lifespan=` async context manager. Good "use case" if the app does meaningful
  setup (warming caches, opening pools, running migrations).
- **Background tasks** — parameters typed `BackgroundTasks`, or a task queue
  (Celery `@shared_task`, ARQ, RQ, Dramatiq). These run *after* a response and
  are easy to miss; trace them as their own flow.
- **WebSocket endpoints** — `@app.websocket("/ws")`.
- **Dependencies** as cross-cutting steps — see below.

## 3. Follow the request inward

Read the route function body and follow what it calls. A typical FastAPI request
flows through these layers — use them as your `layer` ids:

| Layer      | What lives here                            | Typical names |
|------------|--------------------------------------------|---------------|
| `route`    | the path-operation function itself         | `*_router.py`, `api/`, `routers/`, `endpoints/` |
| `security` | auth dependencies, token/password handling | `Depends(get_current_user)`, `security/`, `auth/` |
| `service`  | business logic, orchestration              | `services/`, `*_service.py`, `domain/`, `use_cases/` |
| `data`     | DB/ORM access, repositories                | `repositories/`, `crud/`, `models/`, `db/`, SQLAlchemy sessions |
| `external` | outbound HTTP, payment, email, queues      | `clients/`, `gateways/`, `external/`, `integrations/` |

Adjust to the project's actual structure — some apps merge service and data, or
name layers differently. Define whatever set you use in the spec's `layers`.

### Dependencies are steps, not noise

FastAPI's `Depends(...)` injects behavior that runs *before* the route body —
authentication, DB sessions, current-user lookup. These are genuine steps in the
flow and usually belong near the top of the trace:

```python
@router.post("/orders")
def create_order(payload: CartIn,
                 user: User = Depends(get_current_user),   # <- a step
                 db: Session = Depends(get_db)):           # <- often setup, can be folded
    ...
```

Trace `get_current_user` as a real step (it validates the token, loads the
user). A pure resource provider like `get_db` that only yields a session can be
folded into whichever step first uses it, unless the session setup itself is
interesting.

### Pydantic models: validation is a step worth naming

The request model (`payload: CartIn`) means FastAPI validated and parsed the
body *before* your code ran. If validation is meaningful to the flow (required
fields, validators, coercion), record an early step like "Validate and parse the
request body" pointing at the Pydantic model's location. If it's trivial, fold
it into the "receive the request" step.

## 4. Pin the file:line

For each step, open the file and read the definition or call site, then record
`path/from/project/root.py:LINE`. Useful commands:

```bash
grep -rn "def authenticate" app/            # find a definition
grep -rn "@router.post" app/api/            # find route declarations
grep -rn "include_router" app/              # find where routers mount
```

Verify the line points at the thing you mean. If a function is defined once but
called from several places, the step's `location` should usually be the
**definition** (where the behavior lives), and you can mention notable call
sites in `detail`.

## 5. Async notes

Most FastAPI apps mix `async def` and `def` handlers. The call path reads the
same either way — just follow `await`ed calls as ordinary steps. If a handler
fans out with `asyncio.gather(...)`, note the parallel calls in a single step's
`detail` rather than forcing them into a strict sequence.

## Worked example shape

The login flow in `assets/example_trace.json` is a realistic FastAPI trace:
route (`POST /auth/login`) → service (`authenticate`) → data (`find_by_email`)
→ security (`verify`, `issue`) → back to route. Use it as a model for depth and
phrasing. Notice it's 6 steps, not 20 — it keeps the steps that teach and folds
the rest.
