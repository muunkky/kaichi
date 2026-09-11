# The Dispatch Loop — specification

What the dispatcher does, in order, with every decision it makes and every artifact it writes.
Descriptive: this records the loop as the shipped `kaichi-dispatcher` skill defines it, so it can be
read, diagrammed and audited without reading the skill.

Scope is the dispatch loop only — Phase 0 through Phase 5. Planning (roadmap → PRD → design → ADR)
and decomposition (sprint architect) sit upstream and are out of scope.

---

## 1. Modes

The mode is named at invocation. There is no auto-detection.

| Mode | Input | Working branch | Terminal act |
|---|---|---|---|
| **Sprint** (default) | sprint tag | `sprint/{TAG}` | closeout → PR → merge-or-hand-back |
| **Single-card** | card id | `feature/{cardid}` | closeout → PR → merge-or-hand-back |
| **Card scope** | card id + declared scope | `card/{cardid}` | commit `.kaichi/`, push one ref, stop |
| **Sprint scope** | sprint tag | `sprint/{TAG}` | hands each card out; merges branches home |

Single-card mode skips: `take_sprint`, closeout-card verification, sprintmaster, batch barriers,
Gate 0, the closeout reviewer. Card scope additionally suppresses archive and the entire PR path.

### Sprint vs sprint scope

Both are a sprint dispatch; they differ only in where the executor runs. Sprint scope changes exactly
one thing — at the point a sprint dispatch would spawn a card's loop in a local worktree, it hands
the card to another kaichi and waits. Selection, admission, the batch barrier, the merge, the
closeout and the roadmap transitions all stay on the dispatching box, unchanged. Touching any of them
is a scope violation, not an extension.

| | Sprint | Sprint scope |
|---|---|---|
| Executor runs | local worktree | another kaichi box, in card scope |
| Completion signal | the Agent result via `TaskOutput` | `card/{cardid}` advancing, its push landing on the remote |
| Card state arrives | uncommitted in the parent; the dispatcher stages it | committed in `.kaichi/` on the branch |
| Merge | `merge worktree-agent-{id}` | `fetch`, then `merge card/{cardid}` |
| A stalled card | watchdog → `.stale` → re-dispatch once | nothing watches it; a person looks |

The last row is deliberate. Phase 1 has no capacity supplier under sprint scope and therefore no
diagnostic half: there is nothing to ask *why* a branch stalled, so no watcher or probe is invented —
the operator who handed the card out checks on it. Card scope is the other half of the same
instruction: what the receiving box runs.

Under the **Hermes** harness there is no Agent tool and no worktree isolation; the loop runs through
the `hermes-dispatch` driver, which adds a between-card integrity check (quarantine on unsanctioned
protected-state mutation) because Hermes enforcement is fail-legible rather than fail-closed.

---

## 2. Roles

| Role | Isolation | Idle threshold | Writes |
|---|---|---|---|
| Executor | worktree | 300s | code on `worktree-agent-{id}`; card state via MCP |
| Remediator | worktree | 240s | bounded corrections only; never card status |
| Reviewer | main thread | 180s | review report to its inbox; never the card's state |
| Router | main thread | 120s | verdict, review-log append, instruction files |
| Planner | main thread | 180s | follow-up cards; closeout-card appends |
| Sprint-closeout-reviewer | main thread | foreground | review report; writes nothing to any card |

### Liveness supervision

**Specified, but not in effect.** Everything below describes what the skill and the watchdog
prescribe. In practice the loop runs unsupervised: the watchdog is not a service but a prose
instruction telling the dispatcher to background `agent-watchdog.sh` once per agent, and across this
repository's 98 dispatch logs the command appears in 3, with no log recording a stale detection or a
`TaskStop`. So a hung agent is caught by a person or not at all, and every defect below is **latent** —
real in the instructions, never yet fired. Read the counts as of this writing and re-derive them
before relying on them. Tracked as card `toll1h`.

That latency is load-bearing when reading the rest of this section: arming the path as written would
convert the defects below from latent to active, so a correct supervision path has to precede a
running one.

**The threshold is idle time, not a lifetime.** `agent-watchdog.sh` polls the agent's trace file and
measures seconds since the last appended line; any new line resets the clock, so an agent that keeps
calling tools runs indefinitely. Nothing is killed on a timer.

**The marker is reversible; the reaction to it is not.** On the threshold the watchdog writes
`.stale`, removes `.alive`, and deliberately keeps polling — if activity resumes it deletes the
marker and rewrites `.alive`. The marker carries `last_line`, the last tool call, and the script's
own comment says the dispatcher "decides whether to kill". The skill does not decide: *On stale
detection* opens with "The agent is likely hung" and its second step is `TaskStop`. No branch
anywhere permits the verdict *healthy, still working*. The script is the correct half of this design;
the instruction never caught up to it.

**Signal.** The trace fires on **PreToolUse only**, so a line lands when a tool call starts and
nothing until the next one. One long call — a full test suite, which is what an executor runs — reads
as idle for its whole duration. Whatever closes this must keep the trace-derived metrics honest, since
every line is counted as a tool call.

A PostToolUse leg is probably not available as the fix, and the reason is already recorded: ADR-028
states that PostToolUse hooks in `.claude/settings.json` do not propagate to Agent subprocesses, that
agent-frontmatter PostToolUse hooks do not fire either, and that PreToolUse is the only hook that
propagates — which is why the trace carries no per-tool durations. If that still holds, the leg cannot
reach the one population the watchdog supervises, and a heartbeat is the only live mechanism. Nothing
in the repo asserts the constraint today, so it is a probe to run rather than a premise to inherit.

**Policy.** A reversible marker gets a terminal reaction. The prescribed path is kill, merge partials,
re-dispatch — under a canned `"Previous executor hit an internal error"` that is false when nothing
errored — and the second stall escalates as "something is systematically wrong". Correct sampling does
not fix this: any genuinely long single operation still trips it.

**Arming.** A supervision step that happens only when an agent remembers a prose instruction is not
supervision, and this is the defect that hides the other two.

**Four further gaps in the same mechanism, none of them currently exercised by any test.** Each is the
same shape as the arming gap — the supervisor silently stops supervising, and the loop cannot tell:

| Gap | What happens |
|---|---|
| No kill path | The skill says "kill the watchdog processes and remove marker files" and then removes only the marker files. Nothing sends the SIGTERM the script traps, so every watchdog started keeps polling for the life of the shell |
| `MAX_WAIT` exits silently | No trace file matching the prefix within 120s and the watchdog `exit 1`s; nothing notices its supervisor is gone |
| Strategy-2 discovery can latch onto the wrong agent | On a prefix miss it takes the newest `agent-*.jsonl`. Main-thread roles may be dispatched together, so the newest trace can be a sibling's, and the watchdog then reports on one agent under another's name |
| Strategy-2b drops the since-start filter | Its own comment says so. On macOS/BSD it can latch onto a previous session's trace, whose line count never advances — an immediate false stale at the threshold |

Batch cleanup compounds these: `rm -f` over `*.stale` and `*.alive` in the whole traces directory,
while other agents may still be running.

**What the records say.** ADR-035 lists among its consequences that there are *no hard timeouts on
critical-path agents*, that a hung executor simply hangs the dispatcher, and that the human "remains
the only watchdog" for executor, reviewer and router — deferring threshold-based escalation to a Tier
2 gated on platform fixes. Given that supervision is not in effect, that is an accurate description
of what happens: the contradiction is between the **skill** and the record, not between the shipped
system and the record. It also means arming a corrected watchdog may itself be the deferred Tier 2
rather than a fix inside Tier 1.

### Other role invariants

**The loop's terminal node is a reader, never a writer.** There is no close-out writer role. A
per-card agent dispatched after review to tick boxes and complete the card is forbidden — its writes
are the ones no reviewer ever reads. The sprint-closeout-reviewer is sprint-level, runs last, and
reads only.

Executors are dispatched **one per message** — a worktree-isolated Agent call sharing a message with
any other Agent call gets its `WorktreeCreate` hook cancelled.

---

## 3. Stores

| Store | Path | Travels? |
|---|---|---|
| Dispatch log | `.kaichi/agents/dispatcher/inbox/{TAG}-dispatch-log.md` | yes |
| Gate 0 verdicts | `.kaichi/agents/dispatcher/inbox/{TAG}-gate0-{stamp}.json` | yes |
| Role inboxes | `.kaichi/agents/{role}/inbox/{TAG}-{cardid}-{role}-{N}.md` | yes |
| Agent error files | same, `…-{N}-ERROR.md` | yes |
| Reasoning trails | `.kaichi/agents/{role}/reasoning/{TAG}-{cardid}-{role}-{N}.jsonl` | yes |
| Traces | `.kaichi/agents/traces/agent-{id}-NNN.jsonl` | no (git-ignored) |
| Watchdog markers | `.kaichi/agents/traces/*.stale`, `*.alive` | no (transient) |
| Cards | `.kaichi/cards/`, archive under `cards/archive/sprints/{stamp}-sprint-{tag}/` | yes |
| Roadmap | `.kaichi/roadmap/roadmap.yaml` | yes |
| Views | `.kaichi/views/{board,roadmap,docs}.html` | no (regenerable) |
| Audit | `.kaichi/audit/*.jsonl`, `audit/bypasses/` | **no — machine-local by design** |
| Worktrees | `.claude/worktrees/agent-{id}/` | no |
| Git refs | `sprint/{TAG}`, `worktree-agent-{id}`, tag `{TAG}-{cardid}-done` | refs only |
| Sprint report | `docs/reports/{TAG}/{TAG}-report.md` + `index.html` | yes (committed) |
| Changelog | `CHANGELOG.md` | yes |

The dispatch-log path comes from `dispatch_log_path(scope=…)` and is never hand-built: it is the one
inbox file whose name is not card-scoped, so two dispatchers on one sprint would otherwise collide.

---

## 4. Phase 0 — Readiness

Ordered. Each step gates the next.

1. **Orphan sweep** — `prune-orphan-worktrees.sh --quiet`. Skips live worktrees, tolerates
   OS-locked directories, always exits 0.
2. **WIP onto the branch** — create the working branch; uncommitted WIP comes along.
3. **Claim** — `take_sprint(tag, handle)`. Moves backlog→todo and assigns. Cards already
   todo/in_progress/done are ignored.
4. **Migration preflight** — `health_check()` → read `pending_migrations`.
   - any entry `class == "rewrite"` in state `available`/`interrupted` → **HALT**
   - `additive`-only → proceed, note it
   - errors-only, empty, or field absent → proceed
   Never auto-applies. A rewrite migration rewrites committed history.
5. **Closeout card exists** — locate it by sprint tag; **stop** if absent. Record its id and the
   full card list; both are injected into every planner prompt for the run.
6. **Sprintmaster** — a general-purpose agent brings cards to `todo`, assigns step numbers
   (`2A`/`2B` = parallel batch, next integer = phase barrier), resolves dependencies, assigns owners,
   and returns an execution plan.
7. **Plan review** — the dispatcher verifies batch independence itself: shared source files, shared
   test fixtures, P0-before-P1 at equal depth. Re-sequence before proceeding.

---

## 5. Phase 1–4 — Execution loop

Per batch:

### 5.1 Pre-dispatch invariants, in order

- **0a. Advance status** — `move_to_in_progress` from the dispatcher, before the Agent call. This
  closes the duplicate-executor race: a card left `todo` is pickable by a second pass.
- **0b. Push the sprint branch** — after any card-creation or status commits, before the first Agent
  call. Worktree executors merge `origin/sprint/{TAG}` on startup; an unpushed commit is invisible to
  them. A rejected push is fail-fast: dispatch nothing, fix, re-run the phase.
  Then `reconcile_sprint_issue(...)` — idempotent on a sprint label. `conflict` and `denied` are
  noted and do not halt.
- **0c. Architectural-bridge check** — a card claiming to bridge subsystems, unify partitions or
  close an architectural gap requires a design doc that walks one real data path end to end, and
  acceptance criteria derived from it. Otherwise **pause**.
- **0d. Worktree hook** — `WorktreeCreate` must be registered and executable, or **abort**: the
  harness default forks from `origin/main`, not the sprint branch. Prune orphans.

### 5.2 Executor

Dispatch → start watchdog with the returned agent id → poll every 30s on three signals: the task
result, a `.stale` marker, an `-ERROR.md` file.

**Hung-executor check, before any merge.** Zero commits since the fork point *and* no card state
written in the parent = hung. A card whose entire deliverable is card or roadmap state commits
nothing by design, and its state lands in the parent store the moment each MCP tool returns.

**Base check.** Test the *fork point*, not the sprint tip — the tip advances on every card, so a
tip-based test flags every routine parallel dispatch:

```
FORK=$(git merge-base worktree-agent-{id} sprint/{TAG})
git merge-base --is-ancestor "$FORK" origin/main   # true ⇒ WRONG BASE
```

**Merge, then reconcile — the order is a gate.** The executor commits code only and never
`.kaichi/`, so card mutations sit uncommitted in the parent until the dispatcher stages them. Merge
first (`--no-edit`, never a hand-written subject), then reconcile. Reconciling first converts a
protective merge-abort into a content conflict on card markdown.

Post-merge: run tests on the merged branch, run project-specific validation, regenerate derived
artifacts, and check for "Already up to date" (which means the executor committed to the wrong
branch).

### 5.3 Review → route

Every executor cycle is reviewed. No exceptions.

The router exists for **isolation**, not transcription: a review report is adversarial prose carrying
its author's framing, hedges and follow-up section; piped raw into a fixer it becomes context
pollution. The router reduces it to a bounded instruction set — blocker, evidence, fences, nothing
else.

```
executor → reviewer → router → [remediator | sprint-architect] → reviewer → router → … → planner
```

### 5.4 Verdict decisions

| Verdict | Action |
|---|---|
| **APPROVAL**, card `done` | dispatch nothing; post closeout checkpoint |
| **APPROVAL**, card not `done` | the reviewer approved what it should have blocked — surface and re-review |
| **APPROVAL**, reviewer-flipped | card left `in_progress` with boxes resolved; the router queues a close-out-only pass |
| **BLOCKERS** | router → **remediator** (never the executor); full loop repeats |
| **Blocker unreducible to a bounded instruction** | the card is the defect → `kaichi-sprint-architect` for re-scoping |
| **TERMINAL remediation** | router names the exact permitted change; card completes without re-review. Three conditions, and the remediator voids the declaration if it did anything more |
| **Blocked + `needs_human_marked`** | **HALT** — enumerate every outstanding act across every marked card |
| **PLANNER WORK** | dispatch planner; non-blocking; retry once on failure |

`needs_human_marked` is a boolean on `read_card`. Never match the marker text in the body — cards
discuss this mechanism, and an auto-block appends a `## BLOCKED` section to an intact body.

An **unmarked** blocked card terminates nothing: that is routine self-healing work the loop repairs.

### 5.5 Batch close

Re-read the card list — the planner extends the sprint with new step-numbered cards, which join the
remaining plan. Then `sprint_profile(mode="phase")` appended to the dispatch log, and a batch-barrier
checkpoint.

---

## 6. Phase 5 — Closeout

Runs **only** when every assigned card is `done` with an APPROVAL. A subset dispatch commits and
stops; cards are never archived mid-sprint.

1. **Backlog verification** — count router-routed items against cards actually on the board. Fewer
   cards than items means the planner dropped work; re-dispatch before proceeding.
2. **Done-tag cleanup** — delete `{TAG}-*-done`.
3. **Gate 0** — `gate0(card_id=closeout, sprint=TAG)`. No strictness parameter exists.

   | Verdict | Action |
   |---|---|
   | `PASS` | proceed |
   | `FAIL` | refuse the commit; surface each failure row; planner files fix-ups; re-invoke |
   | `INPUT_ERROR` | refuse; wrong card id or tag |
   | `EXTERNAL_PROBE_ERROR` | **halt and escalate** — a probe that cannot run is not a skip |

   Serialise the verdict to `{TAG}-gate0-{stamp}.json`; never mutate it afterwards.
4. **Sprint-closeout reviewer** — runs on every `PASS`, foreground. Gate 0 validates a cite's
   *shape*; this reviewer *resolves* it. Read `unresolved_attestations` from the verdict file as its
   worklist. `REVISE`/`FAIL` refuses the commit. **A spawn failure is a halt** — a `subagent_type`
   that does not resolve fails silently, and silence is indistinguishable from a clean review.
5. **Metrics + report** — `sprint_profile(mode="summary")`, then `sprint_report(sprint=TAG)`, which
   also harvests each agent's reasoning while the transcripts still exist.
6. **Archive** done cards; **commit** `.kaichi/`.
7. **PR** — push; `/kaichi-pr` drafts it and returns a merge-readiness assessment; **mark ready**
   (the required review refuses to run against a draft, and its refusal looks like a pass); run
   `/code-review:code-review` in an isolated worktree at PR head; decide.

   Merge requires a positive artifact: the review's own returned text naming what it reviewed, that
   it was eligible and proceeded, and an explicit findings count — including zero. All three.
   Silence is never that artifact. Anything irreversible hands back regardless.
8. **Orphan sweep** again.

---

## 7. Stop conditions

Exhaustive. Anything not listed is a normal autonomous action.

1. kaichi MCP unavailable or erroring — at startup or mid-sprint
2. Gate 0 `FAIL` / `INPUT_ERROR` / `EXTERNAL_PROBE_ERROR` / uncaught exception
3. Missing sprint closeout card
4. Missing `WorktreeCreate` hook
5. Sprint-branch push rejection (retry, never force)
6. Architectural-bridge card with no design doc
7. Hung agent still stale after exactly one re-dispatch
8. Pending rewrite-class migration at startup
9. A sprint card blocked on an act only a person can perform
10. The sprint adding cards faster than it closes them

Condition 9 is a **termination**, not a sequencing input: the card is not reordered, skipped or
retried. Nothing waits — the operator finds a report, not a prompt — and re-invoking re-terminates on
the same durable fact.

---

## 8. Completion validation

`complete_card` is the only path to `done`, and it is a gate rather than a status write. It re-parses
the card's checkboxes; any unchecked, non-deferred box **auto-moves the card to `blocked`** with a
structured `## BLOCKED` section naming the outstanding items.

A blocked card **cascades**: Gate 0 fails the closeout while any sprint card is blocked.

**Tally neutrality.** The `## BLOCKED` section is a record, not a worklist: it emits plain bullets,
never `- [ ]` checkboxes, because the same body is re-parsed on the next call. The section is
rewritten, never appended, so the body cannot grow across repeated attempts.

**Dispositions.** An unchecked box carrying a recognised disposition is resolved, not outstanding.
Thirteen words map onto two sub-states:

- **superseded** (nothing is owed) — `superseded`, `retired`, `void`, `obsolete`, `template-imposed`,
  `not-applicable`, `n/a`, `unverifiable`, `not-ownable`, `not-executor-ownable`
- **deferred** (real, owed elsewhere) — `deferred`, `relocated`, `moved`

An unrecognised or empty disposition **fails closed** rather than silently resolving. Annotations are
box-scoped: a box owns its own cell, and the canonical resolution position is inside that cell.

---

## 9. Citations

Each tickable claim on the closeout's upper checklist carries `<!-- cite: <kind>:<value> -->`.

| Kind | Resolves against |
|---|---|
| `commit:<sha>` | a commit on the sprint branch or main |
| `pr:<number>` | a **merged** PR |
| `ci:<run-url>` | a run with status `success` |
| `card:<id>` | a sister card that is `done` and corroborates |
| `roadmap:<path>` | a **leaf** node in `done` or `verifying` |
| `retro:<item-id>` | a retrospective item in this same body |
| `none` | explicit no-evidence, for genuinely N/A rows |

**Three reject criteria**, any one a FAIL: a **missing** cite on a ticked box; a **contradicted**
cite (a red CI run, a reverted commit, an unmerged PR, a leaf still `todo`); an **external-state
contradiction** even when the cite looks self-consistent — sprint CI status, a non-empty in-progress
card list, or an unflipped leaf.

The division of labour is the point: **Gate 0 checks that a cite is well-formed; the closeout
reviewer checks that it is true.** A closeout citing a red build passes Gate 0 cleanly, which is why
step 4 is not optional.

---

## 10. Invariants

- No card is `todo` while an executor works it.
- The executor commits code to its worktree branch and never `.kaichi/`; the dispatcher merges
  first, reconciles second.
- Card status is never a sequencing control signal — the router's verdict drives sequencing. Status
  is a health check, except condition 9, which terminates.
- Every write-class git invocation whose target is the parent's refs is pinned to `$PARENT`;
  worktree-local mutations are not pinned.
- No output piping anywhere — a piped exit code masks failure, and buffered sub-agent output hides
  hangs completely.
- Dispatcher commits always run pre-commit hooks. Worker agents may skip on intermediate commits;
  the dispatcher is the merge gate.
- Stage `.kaichi/` whole, excluding `**/audit/**`. Partial staging orphans renames and creates
  duplicate cards.
