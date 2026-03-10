#!/usr/bin/env python3
"""
Creative Office: Autonomous Multi-Agent Brainstorming System

Architecture: async parallel + debate loop
  Phase 1: Generator  (sequential — sets the stage)
  Phase 2: Critic + Builder + Mutant  (parallel — 3x faster than sequential)
  Phase 3: Debate turns  (Generator argues back → Critic+Mutant react in parallel)
  Phase 4: Editor  (sequential — synthesizes and ranks)

Usage:
    python run.py seeds/example_seed.md
    python run.py seeds/example_seed.md --rounds 3 --debate-turns 1
    python run.py seeds/example_seed.md --provider bailian --no-memory
"""

import asyncio
import os
import re
import sys
import json
import yaml
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

from openai import AsyncOpenAI

BASE_DIR = Path(__file__).parent
AGENTS = ["generator", "critic", "builder", "mutant", "editor"]
STALE_MARKER = "[STALE_SESSION]"
STRANGENESS_REDIRECT = "[BELOW_STRANGENESS_FLOOR]"

AGENT_SECTION_HEADERS = {
    "generator": "Generator Output",
    "critic": "Critic Response",
    "builder": "Builder Response",
    "mutant": "Mutant Output",
    "editor": "Editor Summary",
}

SHARED_MEMORY_ALL = ["killed_ideas.md", "patterns.md"]
SHARED_MEMORY_EDITOR = ["best_ideas.md"]
SHARED_MEMORY_CRITIC = ["market_knowledge.md"]
SHARED_MEMORY_BUILDER = ["market_knowledge.md"]

# Debate-phase instructions injected per agent
_DEBATE_GENERATOR = """\

--- DEBATE PHASE ---
The Critic has evaluated your ideas. The Builder has scoped them. The Mutant has \
recombined them. You have read all of this above.

Now argue back:
1. For each idea the Critic KILLED that you believe had real merit: push back \
specifically. Name the Critic's exact objection and counter it with a mechanism or \
market reality they didn't account for. Do not concede ground you don't agree with.
2. For each WOUNDED idea: strengthen it by addressing the specific flaw named.
3. Propose 2–3 new ideas sparked directly by the Mutant's recombinations or the \
Builder's observations — take what they opened and push it further.

The Critic is not always right. Argue from evidence and mechanism, not vibes.
"""

_DEBATE_CRITIC = """\

--- DEBATE PHASE ---
The Generator has pushed back on your kills and wounds. Read the defense above carefully.

For each defended idea: has your verdict changed?
- If the Generator made a compelling argument you genuinely didn't consider: update \
your verdict explicitly (KILL → WOUND, or WOUND → PASS). Show your reasoning.
- If the defense was weak or didn't address your actual objection: explain specifically \
why it failed. Don't just restate your original verdict — engage with what they said.

Also evaluate any new ideas the Generator proposed in their defense with the same rigor.
Do not hold verdicts you can no longer defend under scrutiny.
"""

_DEBATE_MUTANT = """\

--- DEBATE PHASE ---
You have now seen the Generator defend its ideas and the Critic respond. The argument \
itself has generated new material — positions taken, concessions made, mechanisms named.

Produce 2–3 hybrids that could only have come from this specific argument:
- Take the core of an idea the Generator defended + the Critic's specific objection \
= what hybrid survives both?
- Take the Builder's spec for one idea and evolve it using what you learned from the debate.
- Find the synthesis between the Generator's contrarian position and the Critic's reality \
check — what idea lives exactly at the fault line between them?

These should feel like ideas the argument itself produced, not things you could have \
generated before the fight started.
"""


# ---------------------------------------------------------------------------
# Config / file loading
# ---------------------------------------------------------------------------


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_file(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_memory_file(path: Path, max_chars: int = 6000) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8").strip()
    if not content or content.startswith("<!-- memory will accumulate"):
        return ""
    if len(content) > max_chars:
        content = "[...older entries archived...]\n\n" + content[-max_chars:]
    return content


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------


def build_system_prompt(agent_name: str, memory_enabled: bool = True) -> str:
    agent_dir = BASE_DIR / "agents" / agent_name
    shared_dir = BASE_DIR / "shared_memory"
    sections = [load_file(agent_dir / "personality.md")]

    if not memory_enabled:
        return sections[0]

    for filename, header in [
        ("memory_identity.md", "## Your Identity Memory\n\n"),
        ("memory_taste.md", "## Your Taste Memory\n\n"),
        ("memory_knowledge.md", "## Your Knowledge Memory\n\n"),
    ]:
        content = load_memory_file(agent_dir / filename)
        if content:
            sections.append(header + content)

    for fname in SHARED_MEMORY_ALL:
        content = load_memory_file(shared_dir / fname, max_chars=8000)
        if content:
            sections.append(
                f"## {fname.replace('_', ' ').replace('.md', '').title()} (shared)\n\n{content}"
            )

    if agent_name == "editor":
        for fname in SHARED_MEMORY_EDITOR:
            content = load_memory_file(shared_dir / fname, max_chars=6000)
            if content:
                sections.append(
                    f"## {fname.replace('_', ' ').replace('.md', '').title()} (shared)\n\n{content}"
                )

    if agent_name in ("critic", "builder"):
        for fname in SHARED_MEMORY_CRITIC:
            content = load_memory_file(shared_dir / fname, max_chars=6000)
            if content:
                sections.append(f"## Market Knowledge (shared)\n\n{content}")

    return "\n\n---\n\n".join(sections)


# ---------------------------------------------------------------------------
# Async agent invocation
# ---------------------------------------------------------------------------


def _pick_model(agent_cfg: dict, provider: str) -> str:
    key = f"model_{provider}" if provider != "openrouter" else "model"
    return agent_cfg.get(key) or agent_cfg["model"]


async def call_agent_async(
    client: AsyncOpenAI,
    agent_name: str,
    room_content: str,
    config: dict,
    memory_enabled: bool,
    provider: str,
    extra_instruction: str = "",
) -> str:
    agent_cfg = config["agents"][agent_name]
    system_prompt = build_system_prompt(agent_name, memory_enabled)
    model_id = _pick_model(agent_cfg, provider)

    user_content = (
        "Here is the current state of the brainstorming session:\n\n"
        "<room>\n" + room_content + "\n</room>\n\n"
        "It is now your turn. Read everything above carefully, then perform "
        "your role exactly as described in your instructions." + extra_instruction
    )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    create_kwargs: dict = {
        "model": model_id,
        "temperature": agent_cfg["temperature"],
        "max_tokens": agent_cfg["max_tokens"],
    }

    while True:
        response = await client.chat.completions.create(
            **create_kwargs, messages=messages
        )
        msg = response.choices[0].message
        tool_uses = getattr(msg, "tool_calls", None) or []

        if not tool_uses:
            return msg.content or ""

        # Handle tool calls (web search stub)
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": msg.tool_calls,
            }
        )
        for tu in tool_uses:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tu.id,
                    "content": "Search executed. Results included in context.",
                }
            )


# ---------------------------------------------------------------------------
# Round orchestration — parallel phases + debate
# ---------------------------------------------------------------------------


async def run_round_async(
    client: AsyncOpenAI,
    room_content: str,
    config: dict,
    memory_enabled: bool,
    provider: str,
    debate_turns: int,
    verbose: bool,
    round_num: int,
    room_path: Path,
) -> tuple[str, str]:
    """
    Returns (additions_to_room, editor_output).
    Phases:
      1. Generator  (sequential)
      2. Critic + Builder + Mutant  (parallel)
      3. Debate turns × (Generator defense → Critic + Mutant react in parallel)
      4. Editor  (sequential)
    """
    additions = ""

    def append(header: str, content: str) -> None:
        nonlocal additions, room_content
        additions += f"\n### {header}\n\n{content}\n"
        room_content = room_content + additions  # live view for next call
        write_room(room_content, room_path)

    def tick(label: str) -> None:
        print(f"  {label:<28}", end="", flush=True)

    def done() -> None:
        print("done", flush=True)

    # ── Phase 1: Generator ──────────────────────────────────────────────────
    tick("GENERATOR")
    gen_out = await call_agent_async(
        client, "generator", room_content, config, memory_enabled, provider
    )
    append("Generator Output", gen_out)
    done()

    # ── Phase 2: Critic + Builder + Mutant in parallel ──────────────────────
    tick("CRITIC + BUILDER + MUTANT")
    critic_out, builder_out, mutant_out = await asyncio.gather(
        call_agent_async(
            client, "critic", room_content, config, memory_enabled, provider
        ),
        call_agent_async(
            client, "builder", room_content, config, memory_enabled, provider
        ),
        call_agent_async(
            client, "mutant", room_content, config, memory_enabled, provider
        ),
    )
    append("Critic Response", critic_out)
    append("Builder Response", builder_out)
    append("Mutant Output", mutant_out)
    done()

    # ── Phase 3: Debate turns ────────────────────────────────────────────────
    for turn in range(debate_turns):
        label = f"DEBATE {turn + 1}/{debate_turns}"

        # Generator argues back
        tick(f"{label} — Generator")
        gen_defense = await call_agent_async(
            client,
            "generator",
            room_content,
            config,
            memory_enabled,
            provider,
            extra_instruction=_DEBATE_GENERATOR,
        )
        append(f"Generator Defense (Debate {turn + 1})", gen_defense)
        done()

        # Critic re-evaluates + Mutant evolves — in parallel
        tick(f"{label} — Critic + Mutant")
        critic_react, mutant_react = await asyncio.gather(
            call_agent_async(
                client,
                "critic",
                room_content,
                config,
                memory_enabled,
                provider,
                extra_instruction=_DEBATE_CRITIC,
            ),
            call_agent_async(
                client,
                "mutant",
                room_content,
                config,
                memory_enabled,
                provider,
                extra_instruction=_DEBATE_MUTANT,
            ),
        )
        append(f"Critic Re-evaluation (Debate {turn + 1})", critic_react)
        append(f"Mutant Evolution (Debate {turn + 1})", mutant_react)
        done()

    # ── Phase 4: Editor ──────────────────────────────────────────────────────
    tick("EDITOR")
    editor_out = await call_agent_async(
        client, "editor", room_content, config, memory_enabled, provider
    )
    append("Editor Summary", editor_out)
    done()

    return additions, editor_out


# ---------------------------------------------------------------------------
# Room management
# ---------------------------------------------------------------------------


def extract_latest_editor_summary(room_content: str) -> str:
    # Try new format first: ## Editor Summary — Round N
    matches = list(re.finditer(r"## Editor Summary[^\n]*\n\n", room_content))
    if matches:
        last_start = matches[-1].end()
        nxt = re.search(r"\n##", room_content[last_start:])
        end = last_start + nxt.start() if nxt else len(room_content)
        return room_content[last_start:end].strip()

    # Fall back to old format: ### Editor Summary
    matches = list(re.finditer(r"### Editor Summary\n\n", room_content))
    if not matches:
        return ""
    last_start = matches[-1].end()
    nxt = re.search(r"\n##", room_content[last_start:])
    end = last_start + nxt.start() if nxt else len(room_content)
    return room_content[last_start:end].strip()


def extract_session_header(room_content: str) -> str:
    m = re.search(r"\n## Round 1\b", room_content)
    return room_content[: m.start()].strip() if m else room_content.strip()


def extract_agent_sections(room_content: str, agent_name: str) -> str:
    header = re.escape(AGENT_SECTION_HEADERS[agent_name])
    pattern = rf"### {header}\n\n(.*?)(?=\n### |\n## |\Z)"
    matches = re.findall(pattern, room_content, re.DOTALL)
    return "\n\n---\n\n".join(m.strip() for m in matches)


def compress_room(room_content: str, buffer_path: Path, round_num: int) -> str:
    """
    Aggressive compression: only Editor summary and key insights stay.
    Everything else goes to buffer.
    """
    with open(buffer_path, "a", encoding="utf-8") as f:
        f.write(f"\n\n{'=' * 80}\n# ARCHIVED — Round {round_num}\n{'=' * 80}\n\n")
        f.write(room_content)

    header = extract_session_header(room_content)
    summary = extract_latest_editor_summary(room_content)
    insights = extract_key_insights(room_content)

    compressed = header
    if summary:
        compressed += f"\n\n## Round {round_num} Summary\n\n{summary}"
    if insights:
        compressed += f"\n\n### Key Insights\n\n{insights}"

    return compressed


def extract_key_insights(room_content: str) -> str:
    """Extract ## Key Insight sections from debate responses."""
    pattern = r"## Key Insight\n\n(.+?)(?=\n##|\n###|\n---|\Z)"
    matches = re.findall(pattern, room_content, re.DOTALL)
    if not matches:
        return ""
    insights = []
    for m in matches[:6]:  # Limit to 6 most recent insights
        insight = m.strip().replace("\n", " ")
        if len(insight) > 20:
            insights.append(f"- {insight}")
    return "\n".join(insights) if insights else ""


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def write_room(content: str, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Post-session: parallel reflection
# ---------------------------------------------------------------------------

_REFLECTION_PROMPT = """\
You just completed a creative brainstorming session as the {role}.

Here are YOUR contributions from this session:
<your_output>
{agent_output}
</your_output>

Here is the Editor's final scoring and summary (your quality benchmark):
<editor_summary>
{editor_summary}
</editor_summary>

Reflect briefly. Write new observations to APPEND to your memory files.
Be terse — these are notes to your future self, not prose.

Use EXACTLY this format. Write SKIP for any section with nothing to add.

---IDENTITY---
[Bullet observations: tendencies noticed, style corrections, what to do differently]

---KNOWLEDGE---
[New knowledge entries dated {date}: domain combinations, market facts, frameworks]

---TASTE---
[Patterns in what scored high vs low. New quality heuristics]
"""


async def run_reflection_async(
    client: AsyncOpenAI,
    room_content: str,
    config: dict,
    session_date: str,
    provider: str,
    verbose: bool,
) -> None:
    editor_summary = extract_latest_editor_summary(room_content)

    async def reflect_one(agent_name: str) -> None:
        if verbose:
            print(f"  [reflect:{agent_name}]", end="", flush=True)
        agent_output = extract_agent_sections(room_content, agent_name)
        if not agent_output:
            if verbose:
                print(" (skipped — no output found)")
            return
        agent_cfg = config["agents"][agent_name]
        prompt = _REFLECTION_PROMPT.format(
            role=agent_name.title(),
            agent_output=agent_output[:6000],
            editor_summary=editor_summary[:3000],
            date=session_date,
        )
        try:
            response = await client.chat.completions.create(
                model=_pick_model(agent_cfg, provider),
                temperature=0.3,
                max_tokens=1500,
                messages=[
                    {
                        "role": "system",
                        "content": load_file(
                            BASE_DIR / "agents" / agent_name / "personality.md"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            _apply_reflection(
                agent_name, response.choices[0].message.content or "", session_date
            )
            if verbose:
                print(" done")
        except Exception as e:
            if verbose:
                print(f" ERROR: {e}")

    # All 5 agents reflect in parallel
    await asyncio.gather(*[reflect_one(a) for a in AGENTS])


def _parse_reflection(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    parts = re.split(r"---(\w+)---", text)
    for i in range(1, len(parts) - 1, 2):
        key = parts[i].strip().lower()
        content = parts[i + 1].strip()
        if content.upper() != "SKIP" and content:
            result[key] = content
    return result


def _apply_reflection(agent_name: str, reflection_text: str, date: str) -> None:
    agent_dir = BASE_DIR / "agents" / agent_name
    file_map = {
        "identity": agent_dir / "memory_identity.md",
        "knowledge": agent_dir / "memory_knowledge.md",
        "taste": agent_dir / "memory_taste.md",
    }
    for key, content in _parse_reflection(reflection_text).items():
        if key in file_map:
            with open(file_map[key], "a", encoding="utf-8") as f:
                f.write(f"\n\n### {date}\n{content}")


# ---------------------------------------------------------------------------
# Post-session: parallel shared memory updates
# ---------------------------------------------------------------------------

_EDITOR_SHARED_PROMPT = """\
You are the Editor from a creative brainstorming session.

Here is the complete session transcript:
<session>
{session}
</session>

Update the shared memory registry. Write SKIP for any section with nothing to add.

---KILLED---
### Session {date}
[One line per idea killed by the Critic: "- **IdeaName** — reason killed"]

---BEST---
### Session {date}
[One line per idea scoring 7.0+ composite: "- **IdeaName** — Composite X.X — one sentence why"]

---PATTERNS---
### Session {date} observations
[New meta-patterns: domain combos that worked/failed, structural traits of top ideas,
new anti-patterns. SKIP if nothing new.]

---LINEAGE---
### Session {date}
[Notable idea genealogy from the debate: ideas that evolved through argument, Mutant
hybrids that descended from kills. SKIP if nothing notable.]
"""

_CRITIC_MARKET_PROMPT = """\
You are the Critic from a creative brainstorming session.

Here is the complete session transcript:
<session>
{session}
</session>

Extract new market knowledge discovered this session. Only include specific factual claims.

---MARKET---
### [Domain Name]
- [Company or product]: [brief description, price if known]
- [Technical finding]: [maturity level, key limitation]
- Last verified: {date}

Write SKIP if no new market research was conducted.
"""


async def update_shared_memory_async(
    client: AsyncOpenAI,
    room_content: str,
    config: dict,
    session_date: str,
    provider: str,
    verbose: bool,
) -> None:
    shared_dir = BASE_DIR / "shared_memory"

    async def editor_update() -> None:
        if verbose:
            print("  [shared:editor]", end="", flush=True)
        try:
            cfg = config["agents"]["editor"]
            response = await client.chat.completions.create(
                model=_pick_model(cfg, provider),
                temperature=0.3,
                max_tokens=2000,
                messages=[
                    {
                        "role": "system",
                        "content": load_file(
                            BASE_DIR / "agents" / "editor" / "personality.md"
                        ),
                    },
                    {
                        "role": "user",
                        "content": _EDITOR_SHARED_PROMPT.format(
                            session=room_content[:20000], date=session_date
                        ),
                    },
                ],
            )
            _apply_shared_editor(
                response.choices[0].message.content or "", shared_dir, session_date
            )
            if verbose:
                print(" done")
        except Exception as e:
            if verbose:
                print(f" ERROR: {e}")

    async def critic_update() -> None:
        if verbose:
            print("  [shared:critic]", end="", flush=True)
        try:
            cfg = config["agents"]["critic"]
            response = await client.chat.completions.create(
                model=_pick_model(cfg, provider),
                temperature=0.3,
                max_tokens=1500,
                messages=[
                    {
                        "role": "system",
                        "content": load_file(
                            BASE_DIR / "agents" / "critic" / "personality.md"
                        ),
                    },
                    {
                        "role": "user",
                        "content": _CRITIC_MARKET_PROMPT.format(
                            session=room_content[:20000], date=session_date
                        ),
                    },
                ],
            )
            _apply_shared_market(response.choices[0].message.content or "", shared_dir)
            if verbose:
                print(" done")
        except Exception as e:
            if verbose:
                print(f" ERROR: {e}")

    # Both run in parallel
    await asyncio.gather(editor_update(), critic_update())


def _apply_shared_editor(text: str, shared_dir: Path, date: str) -> None:
    section_map = {
        "killed": shared_dir / "killed_ideas.md",
        "best": shared_dir / "best_ideas.md",
        "patterns": shared_dir / "patterns.md",
        "lineage": shared_dir / "session_lineage.md",
    }
    parts = re.split(r"---(\w+)---", text)
    for i in range(1, len(parts) - 1, 2):
        key = parts[i].strip().lower()
        content = parts[i + 1].strip()
        if content.upper() == "SKIP" or not content or key not in section_map:
            continue
        with open(section_map[key], "a", encoding="utf-8") as f:
            f.write(f"\n\n{content}")


def _apply_shared_market(text: str, shared_dir: Path) -> None:
    parts = re.split(r"---(\w+)---", text)
    for i in range(1, len(parts) - 1, 2):
        key = parts[i].strip().lower()
        content = parts[i + 1].strip()
        if key == "market" and content.upper() != "SKIP" and content:
            with open(shared_dir / "market_knowledge.md", "a", encoding="utf-8") as f:
                f.write(f"\n\n{content}")


# ---------------------------------------------------------------------------
# Session archival
# ---------------------------------------------------------------------------


def archive_session(
    room_content: str,
    config: dict,
    rounds_completed: int,
    start_time: datetime,
    seed_path: str,
) -> Path:
    timestamp = start_time.strftime("%Y%m%d_%H%M")
    archive_dir = BASE_DIR / "archive" / f"session_{timestamp}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    (archive_dir / "room_full.md").write_text(room_content, encoding="utf-8")

    summary = extract_latest_editor_summary(room_content)
    (archive_dir / "top_ideas.md").write_text(
        f"# Top Ideas — Session {timestamp}\n\n"
        + (summary or "_No editor summary found._"),
        encoding="utf-8",
    )

    import json as _json

    (archive_dir / "metadata.json").write_text(
        _json.dumps(
            {
                "timestamp": timestamp,
                "start_time": start_time.isoformat(),
                "end_time": datetime.now().isoformat(),
                "rounds_completed": rounds_completed,
                "seed": str(seed_path),
                "config": config,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return archive_dir


def git_commit_session(start_time: datetime, top_idea_name: str) -> None:
    try:
        ts = start_time.strftime("%Y-%m-%d %H:%M")
        msg = f"creative-office: session {ts} — {top_idea_name[:50] or 'complete'}"
        subprocess.run(
            ["git", "add", "-A"], cwd=BASE_DIR, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "--no-gpg-sign", "-m", msg],
            cwd=BASE_DIR,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        pass


def extract_top_idea_name(editor_summary: str) -> str:
    m = re.search(r"#1[:\s]+\*+([^\*\(]+)", editor_summary)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# Main async session loop
# ---------------------------------------------------------------------------


async def run_session_async(
    seed_path: str,
    config: dict,
    memory_enabled: bool,
    verbose: bool,
    provider: str,
    debate_turns: int,
) -> None:
    provider_cfg = config.get("providers", {}).get(provider)
    if not provider_cfg:
        print(
            f"Error: provider '{provider}' not found in config.yaml.", file=sys.stderr
        )
        sys.exit(1)

    client = AsyncOpenAI(
        base_url=provider_cfg["base_url"],
        api_key=provider_cfg["api_key"],
    )

    start_time = datetime.now()
    date_str = start_time.strftime("%Y-%m-%d")
    seed_content = load_file(Path(seed_path))
    session_name = Path(seed_path).stem.replace("_", " ").title()
    room_path = BASE_DIR / "room.md"
    buffer_path = BASE_DIR / f"room_buffer_{start_time.strftime('%Y%m%d_%H%M')}.md"

    room_content = (
        f"# Session: {session_name}\n\n"
        f"## Started: {start_time.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"## Seed\n\n{seed_content}\n\n"
    )
    write_room(room_content, room_path)

    mem_cfg = config.get("memory", {})
    do_memory = memory_enabled and mem_cfg.get("enabled", True)
    do_reflect = do_memory and mem_cfg.get("reflection_after_session", True)
    do_shared = do_memory and mem_cfg.get("shared_memory_update", True)
    do_git = mem_cfg.get("git_commit", True)

    max_rounds = config["session"]["max_rounds"]
    token_budget = config["session"]["room_token_budget"]
    stale_limit = config["session"]["auto_stop_after_stale_rounds"]
    stale_count = 0
    redirect_count = 0

    parallel_note = " + parallel C/B/M" + (
        f" + {debate_turns} debate turn(s)" if debate_turns else ""
    )
    print(f"\nCreative Office — {session_name}")
    print(
        f"Provider: {provider} | Rounds: {max_rounds} | Memory: {'ON' if do_memory else 'OFF'}{parallel_note}"
    )
    print("=" * 60)

    last_round = 0
    for round_num in range(1, max_rounds + 1):
        last_round = round_num
        print(f"\nRound {round_num}/{max_rounds}")
        room_content += f"\n## Round {round_num}\n"

        try:
            additions, editor_out = await run_round_async(
                client,
                room_content,
                config,
                do_memory,
                provider,
                debate_turns,
                verbose,
                round_num,
                room_path,
            )
        except Exception as e:
            print(f"\n[API ERROR round {round_num}]: {e}")
            sys.exit(1)

        room_content += additions
        write_room(room_content, room_path)

        if STALE_MARKER in editor_out:
            stale_count += 1
            print(f"  [STALE FLAG {stale_count}/{stale_limit}]")
            if stale_count >= stale_limit:
                print("\nStopping: session is stale.")
                break
        else:
            stale_count = 0

        # Strangeness floor check (quality gate)
        quality_gates = config.get("quality_gates", {})
        strangeness_floor = quality_gates.get("strangeness_floor", 7)
        floor_action = quality_gates.get("strangeness_floor_action", "redirect")
        max_redirects = quality_gates.get("max_redirects_per_round", 1)

        if STRANGENESS_REDIRECT in editor_out and floor_action == "redirect":
            redirect_count = redirect_count + 1 if "redirect_count" in dir() else 1
            if redirect_count <= max_redirects:
                print(f"  [STRANGENESS REDIRECT {redirect_count}/{max_redirects}]")
            else:
                print(f"  [STRANGENESS REDIRECT] Max redirects reached, continuing...")
        else:
            redirect_count = 0

        tok = estimate_tokens(room_content)
        if tok > token_budget:
            print(f"  [COMPRESS] ~{tok:,} tokens → compressing room", flush=True)
            room_content = compress_room(room_content, buffer_path, round_num)
            write_room(room_content, room_path)

    # Archive
    print("\nArchiving session...", flush=True)

    # Read from buffer for full content, fall back to room_content if buffer doesn't exist
    if buffer_path.exists():
        full_content = buffer_path.read_text(encoding="utf-8")
    else:
        full_content = room_content

    archive_dir = archive_session(
        full_content, config, last_round, start_time, seed_path
    )
    print(f"  archive: {archive_dir}")

    # Post-session memory (all parallel)
    if do_reflect:
        print("\nReflecting (all agents in parallel)...", flush=True)
        await run_reflection_async(
            client, full_content, config, date_str, provider, verbose=True
        )

    if do_shared:
        print("Updating shared memory...", flush=True)
        await update_shared_memory_async(
            client, full_content, config, date_str, provider, verbose=True
        )

    if do_git:
        summary = extract_latest_editor_summary(full_content)
        top_name = extract_top_idea_name(summary)
        git_commit_session(start_time, top_name)
        print("  [git] committed")

    print(f"\nTop ideas: {archive_dir / 'top_ideas.md'}")
    print(f"Transcript: {archive_dir / 'room_full.md'}")

    seed = Path(seed_path)
    if seed.parent.name == "pending":
        processed = BASE_DIR / "seeds" / "processed" / seed.name
        seed.rename(processed)
        print(f"Seed moved to: {processed}")


def run_session(*args, **kwargs) -> None:
    asyncio.run(run_session_async(*args, **kwargs))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Creative Office — Autonomous Multi-Agent Brainstorming",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("seed", help="Path to seed .md (e.g. seeds/example_seed.md)")
    parser.add_argument("--config", default=str(BASE_DIR / "config.yaml"))
    parser.add_argument("--rounds", type=int, help="Override max_rounds")
    parser.add_argument(
        "--no-memory", action="store_true", help="Skip memory (fast test)"
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument(
        "--provider",
        default="openrouter",
        choices=["openrouter", "bailian"],
        help="Model provider (default: openrouter)",
    )
    parser.add_argument(
        "--debate-turns",
        type=int,
        default=1,
        metavar="N",
        help="Debate turns per round — Generator argues back, Critic+Mutant react (default: 1, 0=pipeline mode)",
    )
    args = parser.parse_args()

    config = load_config(Path(args.config))
    if args.rounds:
        config["session"]["max_rounds"] = args.rounds

    run_session(
        seed_path=args.seed,
        config=config,
        memory_enabled=not args.no_memory,
        verbose=args.verbose,
        provider=args.provider,
        debate_turns=args.debate_turns,
    )


if __name__ == "__main__":
    main()
