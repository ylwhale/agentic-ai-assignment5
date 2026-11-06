# ARCHITECTURE.md · RepoMind on the seven layers

For each layer: what does this job, and where is it enforced. Cite code as a file
path and line number joined by a colon, inside backticks; a checker opens every
reference (`checks/FORMATS.md`, section 8). A layer held only by a sentence in a
prompt (any file under `prompts/`) is **EMPTY**, and so is a layer nothing does
yet. Status is one of: present, partial (say what is missing), or **EMPTY**. Each
assignment brings this file up to date.

What each layer is for (Lecture 1, slides 42 to 44):

- **Model**: reasoning, choosing tools, generating text.
- **Harness**: runs the loop, builds each prompt, trims old history.
- **Tools**: where the system acts on the world.
- **Memory & State**: what survives a step, a session, a restart.
- **Control & Policy**: what the system may do, and when it must ask.
- **Observability**: a step-by-step record of what it did.
- **Evaluation**: measuring quality, before and after release.

The table below describes RepoMind after the Assignment 5 control-and-policy changes.

| Layer | What does this job | Where it is enforced | Status |
|---|---|---|---|
| Model | The configured model, called only through the metered client | `harness/client.py:150` | present |
| Harness | The loop, with three bounds checked in code; a plan validated before it runs, and an executor that runs only the plan's steps | `agent/loop.py:38`, `ways/planned.py:284`, `ways/planned.py:375` | present |
| Tools | Ten namespaced tools behind one registry; pre-call hooks enforce policy before dispatch, while write calls use harness-managed identifiers and records | `tools/__init__.py:145`, `tools/__init__.py:167`, `tools/__init__.py:235`, `tools/__init__.py:266`, `tools/__init__.py:283`, `policy/hook.py:57` | present |
| Memory & State | Synchronous checkpoints support durable execution and resume; the memory store preserves dated records and their origin | `ways/planned.py:338`, `ways/planned.py:351`, `state/checkpointer.py:55`, `state/store.py:96` | present |
| Control & Policy | The registry installs a policy hook that checks actions before execution. The control layer enforces autonomy boundaries, disclosure, and stop behavior; the planned executor prepares and posts reviewed drafts | `tools/__init__.py:145`, `tools/__init__.py:235`, `policy/hook.py:57`, `ways/planned.py:699`, `ways/planned.py:725` | present |
| Observability | One trace line per model call and per tool call, and the plan as data before it runs | `agent/loop.py:50`, `ways/planned.py:178` | partial: traces, no alerts |
| Evaluation | The grounded check reads the tracker, never the agent | `eval/check_triage.py:7` | partial: offline only |

**Empty layers: 0 of 7**; two layers are partial (Observability and Evaluation).
