# Creative Office

Multi-agent brainstorming system that produces validated, novel ideas through adversarial collaboration. Runs overnight. Generates ranked portfolios with build specs.

## What It Does

- **Generator** produces 8-12 ideas per round with cross-domain combinations
- **Critic** kills 30%+, wounds the rest through adversarial evaluation
- **Builder** specs the survivors with MVP definitions and first-user identification
- **Mutant** creates hybrids from killed ideas + passed ideas through recombination operations
- **Editor** ranks, scores, and directs next round using a 2x2 portfolio matrix
- **Debate mechanism**: Ideas argue for survival through multi-turn debate

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/HenriqueTecas/creative-office.git
cd creative-office
cp config.template.yaml config.yaml

# Edit config.yaml with your API keys
# Supports: OpenRouter, Bailian (Aliyun)

# 2. Write a seed
cp seeds/template.md seeds/pending/my_seed.md
# Edit the seed with your domain and provocation

# 3. Run a session
python run.py seeds/pending/my_seed.md --debate-turns 2

# 4. View results
python evaluate.py --leaderboard

# 5. Dashboard (optional)
cd ui && python server.py --port 8080
# Open http://localhost:8080
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  GENERATOR  │────▶│   CRITIC    │────▶│   BUILDER   │
│  8-12 ideas │     │  Kill 30%+  │     │   MVP specs │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       │                   ▼                   │
       │           ┌─────────────┐             │
       └──────────▶│   MUTANT    │◀────────────┘
                   │ Recombinant  │
                   └─────────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │   EDITOR    │
                   │   Ranks &   │
                   │   Directs   │
                   └─────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
       ┌─────────────┐         ┌─────────────┐
       │   DEBATE    │         │   MEMORY    │
       │   TURNS     │         │   UPDATE    │
       └─────────────┘         └─────────────┘
              │
              ▼
       Next Round
```

### Debate Mechanism

When debate is enabled, ideas don't just get evaluated — they fight for survival:

1. Generator produces ideas
2. Critic attacks
3. Generator defends (can transform the idea)
4. Critic re-evaluates
5. Mutant evolves survivors
6. Editor scores and ranks

This produces ideas that are **both creative AND validated** — rare in brainstorming systems.

## Agent Roles

### Generator
**Job:** Volume, velocity, surprise.
- 8-12 ideas per round
- Must span 3+ unrelated domains (Wildcard Mandate)
- At least 2 ideas from outside the seed domain
- Uses conceptual lenses: deterritorialization, hyperobjects, desire creation

### Critic
**Job:** Adversarial evaluation.
- Kills 30%+ per round minimum
- Finds closest competitor (novelty check)
- Identifies fatal assumptions
- Applies Inevitability Test (will this exist in 5 years regardless?)
- Tracks structural patterns across kills

### Builder
**Job:** Implementation reality check.
- MVP definition (minimum viable build)
- First 10 users (WHO and WHERE specifically)
- Stack sketch and rough cost
- Business model and unit economics
- Scale killers and design-arounds

### Mutant
**Job:** Recombination and surprise.
- 4-6 hybrids per round
- Operations: Hybrid, Inversion, Time Shift, Domain Transplant
- Prefers recombining ideas 3+ rounds apart
- Finds the perpendicular axis to the room's direction
- Extracts mechanisms from killed ideas (organ donors)

### Editor
**Job:** Taste and direction.
- 2x2 Portfolio Matrix (Strange×Buildable)
- Dimensional scores: Novelty, Timing, Desire, Buildability, Strangeness, Survivability
- Dinner Table Test (is this inherently interesting?)
- Enforces Strangeness Floor
- Directs next round with specific prompts

## Memory System

### Per-Agent Memory
Each agent maintains three memory files that grow across sessions:

- `memory_identity.md` — How this agent's behavior evolved
- `memory_taste.md` — What this agent learned about quality
- `memory_knowledge.md` — Domain expertise accumulated

### Shared Memory
All agents read from shared memory each round:

- `killed_ideas.md` — Graveyard (prevents recycling dead ideas)
- `best_ideas.md` — Hall of fame (quality benchmark)
- `patterns.md` — Meta-patterns across sessions
- `market_knowledge.md` — Research accumulated by Critic
- `session_lineage.md` — Full idea genealogy (ancestry tracking)

## Why It Works This Way

### Why agents must disagree
Homogeneous agents produce homogeneous output. The Generator and Critic have fundamentally different dispositions. The Mutant exists to prevent convergence. If all agents start agreeing, the system is broken.

### Why the debate mechanism exists
Ideas that survive adversarial pressure are stronger than ideas that were merely filtered. The debate doesn't just kill bad ideas — it transforms mediocre ideas into good ones through forced justification. The Generator can defend, modify, or abandon ideas based on Critic attacks.

### Why strangeness is weighted 2x
The system's purpose is to produce ideas humans wouldn't arrive at alone. A feasible but obvious idea is LESS valuable than a strange but plausible one, because the obvious idea will be built by someone else regardless. The strangeness floor forces creative ambition.

### Why the 2x2 matrix matters
Composite scores collapse nuance. An idea that's strange but hard to build is different from one that's normal and easy. The 2x2 matrix (Strange×Buildable) separates research bets from immediate wins from safe plays from garbage.

### Why memory matters
Agents without memory repeat themselves. The killed_ideas registry prevents recycling. The taste memory develops aesthetic judgment. The knowledge memory prevents redundant research. Without memory, session 50 isn't better than session 1.

### Why seeds must be broad
Narrow seeds produce narrow output. Broad, conceptual seeds allow the system to discover unexpected territories. A seed about "AI agents for advocacy" will produce advocacy tools. A seed about "invisible power dynamics" might produce advocacy tools, or financial instruments, or architectural interventions.

### Why room compression is aggressive
Context limits crash sessions. The room carries only what's needed for creative continuity: Editor summaries, key debate insights, session tallies. Full Builder specs, Critic evaluations, and debate transcripts go to the buffer. The Editor's summary is the compression function.

## Configuration

Key settings in `config.yaml`:

```yaml
session:
  max_rounds: 10                  # How many rounds before stopping
  room_token_budget: 15000        # When compression triggers (reduced for stability)
  auto_stop_after_stale_rounds: 2 # Stop if Editor flags staleness

quality_gates:
  strangeness_floor: 7            # Minimum strangeness for valid round
  strangeness_floor_action: redirect  # 'redirect' or 'warn'
  max_redirects_per_round: 1      # Prevent infinite loops
  domain_diversity_minimum: 3     # Distinct domains required in top 5

scoring:
  weights:
    novelty: 2.0
    timing: 1.0
    desire: 1.5
    buildability: 1.0
    strangeness: 2.0              # Weighted highest
    survivability: 1.0
```

## Dashboard

```bash
cd ui && python server.py --port 8080
```

Visualizes:
- Agent interactions by round
- Idea journey through pipeline
- Score breakdown across dimensions
- Session statistics and trends
- Live session monitoring

## File Structure

```
creative_office/
├── run.py                  # Main execution loop
├── evaluate.py             # Scoring utilities
├── config.yaml             # Configuration (gitignored - has API keys)
├── config.template.yaml    # Safe to share
├── agents/
│   ├── generator/
│   │   ├── personality.md  # Agent's instructions
│   │   ├── memory_identity.md
│   │   ├── memory_taste.md
│   │   └── memory_knowledge.md
│   ├── critic/
│   ├── builder/
│   ├── mutant/
│   └── editor/
├── shared_memory/
│   ├── killed_ideas.md     # Graveyard
│   ├── best_ideas.md       # Hall of fame
│   ├── patterns.md         # Meta-patterns
│   ├── market_knowledge.md # Research
│   └── session_lineage.md  # Genealogy
├── seeds/
│   ├── template.md         # How to write seeds
│   ├── pending/            # Seeds to run
│   ├── processed/          # Completed seeds
│   └── queue/              # Batch queue
├── archive/
│   └── session_*/
│       ├── room_full.md    # Complete transcript
│       ├── top_ideas.md    # Final ranking
│       └── metadata.json   # Session stats
└── ui/
    ├── index.html          # Dashboard
    ├── app.js              # Visualization logic
    └── server.py           # API server
```

## Troubleshooting

### Session crashed (context limits)
Compression isn't aggressive enough. Check `room_token_budget` in config. Builder output should be dense, not verbose.

### Output is boring
- Raise `strangeness_floor` 
- Broaden the seed
- Check if Generator's wildcard mandate is being followed
- Add more debate turns

### Everything survives the Critic
- Critic is too soft
- Tighten kill criteria in personality
- Identity test not being applied

### Ideas all sound the same
- Domain diversity check is failing
- Force Generator out of dominant domain
- Make Mutant more aggressive with perpendicular axis

### Generator keeps recycling killed ideas
- Check `shared_memory/killed_ideas.md` is being read
- Critic should call out recycling explicitly
- Add more strangeness seeds to prompt file

## Philosophy

Based on:
- **Thielian contrarianism:** Secrets exist, most people don't see them
- **Adversarial collaboration:** Iron sharpens iron
- **Combinatorial creativity:** Novelty from recombination of distant domains
- **Accelerationist lens:** What survives 10x change rate?

The goal is ideas that could actually exist, that real humans would use, that require believing something true that sounds insane.

## License

MIT