#!/usr/bin/env python3
"""
Seed Generator for Creative Office

Generates tension-based seeds that produce non-obvious ideas through agent collision.

Philosophy:
- Seeds are not instructions — they're tensions
- Must contain a contradiction, paradox, or unanswerable question
- Domain-agnostic (could lead anywhere)
- Impossible to answer directly (requires interpretation)

Usage:
    python seeds/generate_seed.py
    python seeds/generate_seed.py --save pending/my_seed.md
"""

import random
import argparse
from pathlib import Path
from datetime import datetime

# Seed pattern templates - each contains a structural tension
SEED_PATTERNS = [
    {
        "pattern": "What becomes {property} when it becomes {condition}?",
        "properties": [
            "dangerous",
            "valuable",
            "useless",
            "invisible",
            "powerful",
            "fragile",
            "contagious",
        ],
        "conditions": [
            "cheap",
            "abundant",
            "fast",
            "automated",
            "public",
            "free",
            "common",
        ],
        "example_reasoning": "AI, sensors, genomic sequencing, energy, surveillance — all getting cheap. Second-order effects, not just applications.",
    },
    {
        "pattern": "What if {abstract_concept} had a {mechanism}?",
        "abstract_concepts": [
            "trust",
            "reputation",
            "attention",
            "silence",
            "privacy",
            "identity",
            "memory",
            "desire",
        ],
        "mechanisms": [
            "spot price",
            "expiration date",
            "undo button",
            "pause button",
            "inheritance",
            "insurance policy",
        ],
        "example_reasoning": "Trust is binary and non-tradable. Making it continuous opens weird territory.",
    },
    {
        "pattern": "What do people do {state_a} that would be transformative if done {state_b}?",
        "state_pairs": [
            ("alone", "collectively"),
            ("privately", "publicly"),
            ("voluntarily", "by requirement"),
            ("unconsciously", "consciously"),
            ("once", "repeatedly"),
            ("for free", "for payment"),
            ("in secret", "as a ritual"),
        ],
        "example_reasoning": "Grieving, sleeping, learning, saving money — each becomes different with coordination.",
    },
    {
        "pattern": "What product gets {paradox_a} the {paradox_b} you use it?",
        "paradox_pairs": [
            ("better", "less"),
            ("worse", "more"),
            ("cheaper", "longer"),
            ("more valuable", "fewer people use"),
            ("safer", "older"),
        ],
        "example_reasoning": "Contradicts every growth metric. Forces thinking about products where restraint is the value.",
    },
    {
        "pattern": "What's the opposite of {familiar_thing}?",
        "familiar_things": [
            "a search engine",
            "social media",
            "a subscription",
            "an algorithm",
            "a marketplace",
            "a bank",
            "a school",
            "a hospital",
            "a government",
            "advertising",
        ],
        "example_reasoning": "Each interpretation is a different product category. Generator must DECIDE what 'opposite' means.",
    },
    {
        "pattern": "What would you build if you could only {constraint}?",
        "constraints": [
            "charge for outcomes, never for access",
            "serve users who never open the app",
            "make money from people NOT using your product",
            "build for users who actively distrust you",
            "create value without collecting any data",
            "grow without adding any features",
            "compete without any technology advantage",
        ],
        "example_reasoning": "Kills SaaS, subscriptions, advertising. Forces pure outcome-based models.",
    },
    {
        "pattern": "What's currently {current_state} that should be {desired_state}?",
        "state_pairs": [
            ("free", "expensive"),
            ("abundant", "scarce"),
            ("automatic", "manual"),
            ("public", "private"),
            ("fast", "slow"),
            ("easy", "hard"),
            ("optional", "required"),
            ("individual", "collective"),
        ],
        "example_reasoning": "Attention, silence, clean air, privacy, boredom — all being destroyed, becoming scarce.",
    },
    {
        "pattern": "What would {domain_a} look like if it had the logic of {domain_b}?",
        "domain_pairs": [
            ("a hospital", "a casino"),
            ("a school", "a gym"),
            ("a government", "a startup"),
            ("a family", "a corporation"),
            ("dating", "hiring"),
            ("healthcare", "hospitality"),
            ("justice", "customer service"),
            ("death", "logistics"),
            ("childhood", "professional sports"),
            ("friendship", "banking"),
        ],
        "example_reasoning": "Metaphor forces cross-domain thinking. What would 'diagnosis' mean for an organization?",
    },
    {
        "pattern": "What if {entity} were the {role}, not the {opposite_role}?",
        "entity_role_pairs": [
            ("children", "customers", "products"),
            ("patients", "doctors", "patients"),
            ("employees", "investors", "resources"),
            ("citizens", "shareholders", "subjects"),
            ("users", "owners", "products"),
            ("students", "teachers", "students"),
            ("borrowers", "lenders", "borrowers"),
            ("fans", "creators", "consumers"),
        ],
        "example_reasoning": "Every product aimed at kids sells to parents or sells kids' attention. Different power dynamic.",
    },
    {
        "pattern": "Where does the most {valuable_thing} go to {negative_outcome}?",
        "valuable_things": [
            "human expertise",
            "institutional knowledge",
            "creative energy",
            "trust",
            "attention",
            "ambition",
        ],
        "negative_outcomes": [
            "die",
            "disappear",
            "get wasted",
            "get corrupted",
            "atrophy",
            "get extracted",
        ],
        "example_reasoning": "Retirement, career changes, industry collapse — all destroy accumulated knowledge.",
    },
    {
        "pattern": "What's the {timeframe_a} version of {timeframe_b}?",
        "timeframe_pairs": [
            ("100-year", "a 10-year problem"),
            ("multi-generational", "a quarterly result"),
            ("permanent", "a temporary fix"),
            ("reversible", "an irreversible decision"),
            ("slow", "a viral product"),
            ("accumulating", "a one-time event"),
        ],
        "example_reasoning": "Forces thinking at different time scales. What accumulates? What compounds?",
    },
    {
        "pattern": "What if {action} required {unexpected_requirement}?",
        "action_requirement_pairs": [
            ("leaving a job", "permission from your future self"),
            ("starting a company", "proof someone else needed it"),
            ("having children", "passing a test"),
            ("retiring", "transferring your knowledge"),
            ("getting married", "completing a trial period"),
            ("buying a house", "living there first"),
        ],
        "example_reasoning": "Creates friction where there isn't any, or removes friction where it shouldn't be.",
    },
]

# Cross-pollination lenses that can be added to any seed
STRANGENESS_LENSES = [
    "Apply the logic of {immune systems / futures markets / mycelial networks / religious conversion / grief stages / addiction recovery}",
    "What would this look like designed to be as uncomfortable as possible for VCs?",
    "What if the product's users and its customers were different entities entirely?",
    "What if the product made money by making itself unnecessary?",
    "What if the target market doesn't exist yet and the product creates it?",
    "What would this look like in 1975? In 2080?",
    "What's the version for the 1%? For the bottom 1%?",
    "What if this was illegal? What if it was mandatory?",
    "What would {a child / an elderly person / someone from another century} think of this?",
    "What's the feature that would make half your users leave but the other half never switch?",
]

# Anti-targets to explicitly exclude
ANTI_TARGET_TEMPLATES = [
    "The obvious AI wrapper",
    "The 'X but for Y' startup",
    "Incremental features on existing products",
    "Solutions that create more work than they solve",
    "Anything that requires changing human nature",
    "Pure vibes with no mechanism",
]


def generate_seed_question() -> dict:
    """Generate a tension-based seed question."""
    pattern_data = random.choice(SEED_PATTERNS)
    pattern = pattern_data["pattern"]

    # Fill in the pattern based on its structure
    if "{property}" in pattern and "{condition}" in pattern:
        return {
            "question": pattern.format(
                property=random.choice(pattern_data["properties"]),
                condition=random.choice(pattern_data["conditions"]),
            ),
            "reasoning": pattern_data["example_reasoning"],
        }

    elif "{abstract_concept}" in pattern and "{mechanism}" in pattern:
        return {
            "question": pattern.format(
                abstract_concept=random.choice(pattern_data["abstract_concepts"]),
                mechanism=random.choice(pattern_data["mechanisms"]),
            ),
            "reasoning": pattern_data["example_reasoning"],
        }

    elif "state_a" in pattern:
        state_a, state_b = random.choice(pattern_data["state_pairs"])
        return {
            "question": pattern.format(state_a=state_a, state_b=state_b),
            "reasoning": pattern_data["example_reasoning"],
        }

    elif "paradox_a" in pattern:
        paradox_a, paradox_b = random.choice(pattern_data["paradox_pairs"])
        return {
            "question": pattern.format(paradox_a=paradox_a, paradox_b=paradox_b),
            "reasoning": pattern_data["example_reasoning"],
        }

    elif "{familiar_thing}" in pattern:
        return {
            "question": pattern.format(
                familiar_thing=random.choice(pattern_data["familiar_things"]),
            ),
            "reasoning": pattern_data["example_reasoning"],
        }

    elif "{constraint}" in pattern:
        return {
            "question": pattern.format(
                constraint=random.choice(pattern_data["constraints"]),
            ),
            "reasoning": pattern_data["example_reasoning"],
        }

    elif "current_state" in pattern:
        current, desired = random.choice(pattern_data["state_pairs"])
        return {
            "question": pattern.format(current_state=current, desired_state=desired),
            "reasoning": pattern_data["example_reasoning"],
        }

    elif "domain_a" in pattern:
        domain_a, domain_b = random.choice(pattern_data["domain_pairs"])
        return {
            "question": pattern.format(domain_a=domain_a, domain_b=domain_b),
            "reasoning": pattern_data["example_reasoning"],
        }

    elif "entity" in pattern:
        entity, role, opposite = random.choice(pattern_data["entity_role_pairs"])
        return {
            "question": pattern.format(
                entity=entity, role=role, opposite_role=opposite
            ),
            "reasoning": pattern_data["example_reasoning"],
        }

    elif "valuable_thing" in pattern:
        return {
            "question": pattern.format(
                valuable_thing=random.choice(pattern_data["valuable_things"]),
                negative_outcome=random.choice(pattern_data["negative_outcomes"]),
            ),
            "reasoning": pattern_data["example_reasoning"],
        }

    elif "timeframe_a" in pattern:
        tf_a, tf_b = random.choice(pattern_data["timeframe_pairs"])
        return {
            "question": pattern.format(timeframe_a=tf_a, timeframe_b=tf_b),
            "reasoning": pattern_data["example_reasoning"],
        }

    elif "unexpected_requirement" in pattern:
        action, requirement = random.choice(pattern_data["action_requirement_pairs"])
        return {
            "question": pattern.format(
                action=action, unexpected_requirement=requirement
            ),
            "reasoning": pattern_data["example_reasoning"],
        }

    return {
        "question": pattern,
        "reasoning": pattern_data["example_reasoning"],
    }


def generate_seed() -> str:
    """Generate a complete seed file content."""
    seed_data = generate_seed_question()

    # Generate title from the question
    title = seed_data["question"].replace("?", "").strip()
    if len(title) > 60:
        title = title[:60] + "..."

    # Generate domain (keep it abstract)
    domains = [
        "Products that make invisible dynamics visible and tradable",
        "Systems that change who has power and how it flows",
        "Tools that create new categories of human experience",
        "Infrastructure for aspects of life that lack it",
        "Markets for things that shouldn't be marketable",
        "Products that serve the people currently ignored",
    ]

    # Generate a concrete moment (anchor)
    moments = [
        "It's 11pm and you just realized the airline charged you twice for a flight you cancelled three weeks ago. You don't have the energy to call them. You don't even know which number to call. You just want it fixed by morning.",
        "A farmer checks her phone. The irrigation system ran all night even though it rained. She's wasted water she can't afford to lose, and she doesn't have time to fix the sensors before the harvest crew arrives.",
        "You're at dinner and your friend describes a product that sounds exactly like something you brainstormed six months ago. Someone else shipped it. You had the idea first but you never made it real.",
        "Your grandmother died last month. You're now the executor of an estate with 47 accounts, 12 subscriptions, 3 storage units, and no documentation. You have no idea where to start.",
        "You've been paying for software for 3 years. You forgot you subscribed. You've never used it. You check your statements and find 8 other subscriptions you forgot about.",
        "A doctor spends 20 minutes entering data into a system that doesn't talk to any other system. She knows the patient's history is in 4 other places. She gives up and asks the patient to remember.",
        "You receive a legal notice. You don't understand it. You can't afford a lawyer. You Google for an hour and give up. You sign something you don't understand because you have no choice.",
        "Your startup failed. You have 3 months of runway left. 7 people believed in you. You don't know what to tell them. You don't know what to do with the code, the data, the relationships you built.",
        "A teacher spends more time on paperwork than teaching. She knows which students are struggling but the system only tracks test scores. She helps them anyway, off the clock, untracked, unmeasured.",
        "You've worked at the same company for 12 years. You know where everything is, who to call, how things actually get done. You're retiring next month. No one's asked you to write any of it down.",
    ]

    # Generate constraints
    constraints = [
        "Must work with existing infrastructure and legal frameworks",
        "Cannot require changing regulations or human behavior",
        "Must have a first customer who is a real, findable person",
        "Cannot depend on network effects to provide initial value",
        "Must be buildable by a small team in under 18 months",
        "Cannot be a feature of an existing platform",
        "Must serve someone currently ignored by the market",
        "Cannot depend on advertising or surveillance capitalism",
    ]

    # Generate provocation
    provocations = [
        "Every solution in this space creates more work than it solves. What if the solution required LESS work, not more?",
        "The current players optimize for growth, not outcomes. What if you optimized for outcomes at the expense of growth?",
        "Everyone assumes this problem requires technology. What if technology is the problem, not the solution?",
        "The business model dictates the product. What if the product dictated the business model?",
        "This space is dominated by people who benefit from its complexity. What if you benefited from simplicity?",
        "Every solution serves the person who pays, not the person who uses. What if those were different people?",
    ]

    # Select components
    domain = random.choice(domains)
    moment = random.choice(moments)
    constraint = random.choice(constraints)
    provocation = random.choice(provocations)

    # Select 2-3 strangeness lenses
    lenses = random.sample(STRANGENESS_LENSES, min(3, len(STRANGENESS_LENSES)))

    # Select 3-4 anti-targets
    anti_targets = random.sample(
        ANTI_TARGET_TEMPLATES, min(4, len(ANTI_TARGET_TEMPLATES))
    )

    # Build the seed
    seed_content = f"""# Seed: {title}

## The Moment

{moment}

## Provocation

{seed_data["question"]}

{provocation}

## Domain

{domain}

## Temporal Frame

Buildable by 2030. Uses technology that exists today or is in late-stage development. No AGI, no brain-computer interfaces, no sci-fi assumptions.

## Constraints

- {constraint}
- Must have a clear first customer who exists today
- Cannot require regulatory changes to launch
- Real products, real users — not art projects or thought experiments

## Anti-targets

{chr(10).join(f"- {t}" for t in anti_targets)}

## Strangeness Seeds

{lenses[0]}

{lenses[1] if len(lenses) > 1 else ""}

{lenses[2] if len(lenses) > 2 else ""}

---

<!-- 
SEED REASONING:
{seed_data["reasoning"]}

This seed is domain-agnostic by design. The tension "{seed_data["question"]}" 
forces interpretation before generation. Different agents will resolve it 
differently — Generator sees opportunities, Critic sees problems, 
Mutant sees inversions, Builder sees implementations. The collision 
between their resolutions produces non-obvious ideas.
-->
"""

    return seed_content


def main():
    parser = argparse.ArgumentParser(
        description="Generate tension-based seeds for Creative Office"
    )
    parser.add_argument(
        "--save", type=str, help="Save to file (e.g., pending/my_seed.md)"
    )
    parser.add_argument("--batch", type=int, help="Generate N seeds")
    args = parser.parse_args()

    if args.batch:
        # Generate multiple seeds
        output_dir = Path(__file__).parent / "pending"
        output_dir.mkdir(exist_ok=True)

        for i in range(args.batch):
            seed = generate_seed()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"seed_{timestamp}_{i + 1}.md"
            filepath = output_dir / filename
            filepath.write_text(seed)
            print(f"Generated: {filepath}")

    elif args.save:
        # Save single seed to specified path
        seed = generate_seed()
        filepath = Path(__file__).parent / args.save
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(seed)
        print(f"Generated: {filepath}")

    else:
        # Print to stdout
        seed = generate_seed()
        print(seed)


if __name__ == "__main__":
    main()
