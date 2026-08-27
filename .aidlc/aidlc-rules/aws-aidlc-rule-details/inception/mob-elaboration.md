# Mob Elaboration (Project Agents)

**Purpose**: Run the AI-DLC **Mob Elaboration** ritual using project-defined specialist agents under `.aidlc/aidlc-agents/`.

**Ritual context**: Mob Elaboration is the collaborative Inception practice where AI proposes plans/questions and the team (here: specialist agent personas + the human) validates intent into clear requirements, stories, and technical direction **before Construction**. No source-code implementation during this ritual.

---

## When to Execute

**Start Mob Elaboration when**:
- The user asks to start AI-DLC / Mob Elaboration, OR
- The workflow reaches Requirements Analysis (or later Inception elaboration stages) after Workspace Detection (and Reverse Engineering if brownfield)

**Mob Elaboration covers / informs these Inception stages**:
- Requirements Analysis
- User Stories (when executed)
- Application Design (when executed)
- Units Generation planning inputs (when executed)

**Do NOT treat Mob Elaboration as Construction**. Code Generation and Build and Test remain Construction-phase activities.

---

## MANDATORY: Discover and Load Project Agents

**CRITICAL**: At the start of any Mob Elaboration session, discover agents before elaborating:

1. List all `*.md` files in `.aidlc/aidlc-agents/` (project root relative).
2. **Load every agent file found** (full contents). Do not skip agents unless the user explicitly excludes a role for this session.
3. If `.aidlc/aidlc-agents/` is missing or empty:
   - Stop Mob Elaboration agent mode
   - Tell the user no project agents were found
   - Continue with standard Inception stage rules only
4. Log in `aidlc-docs/audit.md`:
   - That Mob Elaboration started
   - The agent file paths loaded
   - Any agents the user excluded

### Current Project Agents (expected)

| Agent file | Role |
|---|---|
| `.aidlc/aidlc-agents/business-analyst.md` | Business Analyst |
| `.aidlc/aidlc-agents/frontend-architect.md` | Frontend Architect |
| `.aidlc/aidlc-agents/accessibility-specialist.md` | Accessibility Specialist |
| `.aidlc/aidlc-agents/performance-engineer.md` | Performance Engineer |
| `.aidlc/aidlc-agents/technical-writer.md` | Technical Writer |

If additional `*.md` agents appear in the folder, load and apply them as well using the same session protocol.

---

## Session Protocol (How to Apply Agents)

Operate as **session facilitator**. Simulate the mob by applying each loaded agent persona in turn, then synthesizing.

### Global constraints (all agents)

- Follow each agent's **Constraints** section strictly.
- **Do not** write or modify application source code during Mob Elaboration.
- **Do not** modify repository files except approved AI-DLC artifacts under `aidlc-docs/` (and question/audit/state files required by the workflow).
- Prefer clarifying questions (per `common/question-format-guide.md`) over inventing requirements.
- Honor collaboration responsibilities: agents must challenge each other where their files require it.
- Record unresolved disagreements for human decision.

### Recommended participation order

1. **Business Analyst** — clarify business intent, scope, acceptance criteria
2. **Frontend Architect** — fit to existing architecture, boundaries, technical direction
3. **Accessibility Specialist** — keyboard/semantics/a11y acceptance criteria
4. **Performance Engineer** — budgets, bottlenecks, measurable performance requirements
5. **Technical Writer** — audiences, docs/Storybook deliverables, terminology
6. **Any additional agents** found in `.aidlc/aidlc-agents/` (alphabetical by filename unless user specifies order)

Re-visit earlier agents when later agents surface conflicts (true mob behavior).

### Per-agent turn

For each agent:

1. Announce the active persona (role name).
2. Apply that agent's **Primary Objectives** and **Required Analysis** (or equivalent sections) to the current feature/intent and existing repo context.
3. Produce that agent's **Required Output** sections (use the agent's identifiers such as `FR-XXX`, `PR-001`, readiness phrases).
4. Capture open questions / blockers from that agent.
5. Write the agent output artifact (see Artifacts below).

### Synthesis (after all agents)

Produce a single Mob Elaboration synthesis that includes:

1. Agreed scope (in / out)
2. Merged acceptance criteria (business + accessibility + performance where applicable)
3. Proposed technical direction and reuse list
4. Documentation/Storybook obligations
5. Cross-agent conflicts and recommended human decisions
6. Combined readiness:

Return one overall recommendation:

- `MOB ELABORATION READY FOR WORKFLOW PLANNING / CONSTRUCTION GATES`
- `READY WITH APPROVED ASSUMPTIONS`
- `NOT READY — CLARIFICATION REQUIRED`

Do **not** declare overall readiness while any agent reports a blocking `NOT READY` (or equivalent) unless the human explicitly overrides and the override is logged in audit.md.

---

## Artifacts

Create/update under:

```text
aidlc-docs/inception/mob-elaboration/
  session-summary.md
  business-analyst.md
  frontend-architect.md
  accessibility-specialist.md
  performance-engineer.md
  technical-writer.md
  # plus one file per additional agent: <agent-file-stem>.md
```

Rules:

- One artifact file per agent, mirroring the agent filename stem.
- `session-summary.md` holds synthesis, conflicts, and overall readiness.
- Log approvals and raw human answers in `aidlc-docs/audit.md`.
- Reference these artifacts from Requirements Analysis / User Stories / Application Design outputs rather than discarding agent findings.

---

## Integration with Standard Inception Stages

| Stage | How Mob Elaboration applies |
|---|---|
| Requirements Analysis | Use Business Analyst outputs as primary requirements input; fold a11y/perf criteria into NFRs/acceptance criteria |
| User Stories | Derive stories and Given/When/Then from BA + Accessibility outputs |
| Application Design | Use Frontend Architect (+ Performance/Accessibility constraints) as design input |
| Workflow Planning | Include Construction work implied by agent readiness gaps only after human approval |

After Mob Elaboration synthesis is **approved by the user**, continue the normal core-workflow stage sequence (do not skip Workflow Planning approval gates).

---

## User-Facing Start Message

When starting Mob Elaboration, tell the user:

1. Mob Elaboration is starting
2. Which agent files were loaded
3. That no application source code will be modified during this ritual
4. That each agent will produce an artifact under `aidlc-docs/inception/mob-elaboration/`
5. That their approval is required on the synthesis before Construction

Then begin with the Business Analyst turn (or the first loaded agent if BA is absent).
