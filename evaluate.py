#!/usr/bin/env python3
"""
evaluate.py — Scoring utilities for Creative Office sessions.

Usage:
    # Score a single top_ideas.md
    python evaluate.py archive/session_20240101_0000/top_ideas.md

    # Compare all archived sessions
    python evaluate.py --compare

    # Print leaderboard across sessions
    python evaluate.py --leaderboard
"""

import re
import sys
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field

BASE_DIR = Path(__file__).parent

# Scoring weights matching config.yaml defaults
WEIGHTS = {
    "novelty": 2.0,
    "timing": 1.0,
    "desire": 1.5,
    "buildability": 1.0,
    "strangeness": 2.0,
    "survivability": 1.0,
}
WEIGHT_SUM = sum(WEIGHTS.values())  # 8.5


@dataclass
class IdeaScore:
    name: str
    novelty: float = 0.0
    timing: float = 0.0
    desire: float = 0.0
    buildability: float = 0.0
    strangeness: float = 0.0
    survivability: float = 0.0
    composite: float = field(init=False)

    def __post_init__(self):
        self.composite = self._compute_composite()

    def _compute_composite(self) -> float:
        weighted_sum = (
            self.novelty * WEIGHTS["novelty"]
            + self.timing * WEIGHTS["timing"]
            + self.desire * WEIGHTS["desire"]
            + self.buildability * WEIGHTS["buildability"]
            + self.strangeness * WEIGHTS["strangeness"]
            + self.survivability * WEIGHTS["survivability"]
        )
        return round(weighted_sum / WEIGHT_SUM, 2)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "scores": {
                "novelty": self.novelty,
                "timing": self.timing,
                "desire": self.desire,
                "buildability": self.buildability,
                "strangeness": self.strangeness,
                "survivability": self.survivability,
            },
            "composite": self.composite,
        }


def compute_composite(scores: dict[str, float]) -> float:
    """Standalone composite scorer. Pass a dict with the six dimension keys."""
    weighted = sum(scores.get(dim, 0) * w for dim, w in WEIGHTS.items())
    return round(weighted / WEIGHT_SUM, 2)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_SCORE_LINE_RE = re.compile(
    r"Scores?:\s*"
    r"Novelty\s*(\d+(?:\.\d+)?)\s*\|?\s*"
    r"Timing\s*(\d+(?:\.\d+)?)\s*\|?\s*"
    r"Desire\s*(\d+(?:\.\d+)?)\s*\|?\s*"
    r"Buildability\s*(\d+(?:\.\d+)?)\s*\|?\s*"
    r"Strangeness\s*(\d+(?:\.\d+)?)\s*\|?\s*"
    r"Survivability\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

_IDEA_HEADER_RE = re.compile(
    r"^\*+#?\d+[.:)]\s*(.+?)\*+\s*(?:\(Composite[:\s]*[\d.]+\))?",
    re.MULTILINE,
)


def parse_scores_from_text(text: str) -> list[IdeaScore]:
    """
    Extract IdeaScore objects from an Editor Summary or top_ideas.md file.

    Looks for lines matching:
        Scores: Novelty X | Timing X | Desire X | Buildability X | Strangeness X | Survivability X

    and pairs them with the nearest preceding idea header.
    """
    ideas: list[IdeaScore] = []

    # Split into blocks per idea header
    headers = list(_IDEA_HEADER_RE.finditer(text))
    if not headers:
        return []

    for i, header_match in enumerate(headers):
        idea_name = header_match.group(1).strip().rstrip("*").strip()
        block_start = header_match.end()
        block_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[block_start:block_end]

        score_match = _SCORE_LINE_RE.search(block)
        if not score_match:
            continue

        n, t, d, b, s, sv = (float(x) for x in score_match.groups())
        idea = IdeaScore(
            name=idea_name,
            novelty=n,
            timing=t,
            desire=d,
            buildability=b,
            strangeness=s,
            survivability=sv,
        )
        ideas.append(idea)

    return ideas


def parse_top_ideas_file(path: Path) -> list[IdeaScore]:
    text = path.read_text(encoding="utf-8")
    return parse_scores_from_text(text)


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_scorecard(ideas: list[IdeaScore], session_label: str = "") -> None:
    if session_label:
        print(f"\n{'=' * 60}")
        print(f"Session: {session_label}")
        print(f"{'=' * 60}")

    if not ideas:
        print("  No parseable scored ideas found.")
        return

    # Header
    print(
        f"\n{'RANK':<6}{'IDEA':<36}"
        f"{'NOV':>5}{'TIM':>5}{'DES':>5}{'BLD':>5}{'STR':>5}{'SRV':>5}"
        f"{'COMP':>7}"
    )
    print("-" * 74)

    for rank, idea in enumerate(sorted(ideas, key=lambda i: i.composite, reverse=True), 1):
        print(
            f"#{rank:<5}{idea.name[:35]:<36}"
            f"{idea.novelty:>5.1f}{idea.timing:>5.1f}{idea.desire:>5.1f}"
            f"{idea.buildability:>5.1f}{idea.strangeness:>5.1f}{idea.survivability:>5.1f}"
            f"{idea.composite:>7.2f}"
        )

    best = max(ideas, key=lambda i: i.composite)
    print(f"\nBest idea: {best.name} (composite {best.composite})")
    avg = round(sum(i.composite for i in ideas) / len(ideas), 2)
    print(f"Session avg composite: {avg}")


def print_leaderboard(sessions: list[tuple[str, list[IdeaScore]]]) -> None:
    """Print a cross-session leaderboard of top ideas."""
    all_ideas: list[tuple[str, IdeaScore]] = []
    for session_label, ideas in sessions:
        for idea in ideas:
            all_ideas.append((session_label, idea))

    all_ideas.sort(key=lambda x: x[1].composite, reverse=True)

    print(f"\n{'=' * 80}")
    print("ALL-SESSION LEADERBOARD")
    print(f"{'=' * 80}")
    print(
        f"\n{'RANK':<6}{'IDEA':<36}{'SESSION':<22}{'COMP':>7}"
    )
    print("-" * 72)

    for rank, (session_label, idea) in enumerate(all_ideas[:20], 1):
        print(
            f"#{rank:<5}{idea.name[:35]:<36}"
            f"{session_label[:21]:<22}{idea.composite:>7.2f}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Creative Office — Scoring and Evaluation Utilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Path to a top_ideas.md (or room_full.md) to score",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Score all sessions in the archive/ directory",
    )
    parser.add_argument(
        "--leaderboard",
        action="store_true",
        help="Print top ideas across all sessions",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output scores as JSON instead of formatted table",
    )
    args = parser.parse_args()

    archive_dir = BASE_DIR / "archive"

    if args.file:
        path = Path(args.file)
        ideas = parse_top_ideas_file(path)
        if args.json:
            print(json.dumps([i.as_dict() for i in ideas], indent=2))
        else:
            print_scorecard(ideas, session_label=path.parent.name)

    elif args.compare or args.leaderboard:
        sessions = []
        for session_path in sorted(archive_dir.glob("session_*")):
            top_ideas_file = session_path / "top_ideas.md"
            if not top_ideas_file.exists():
                continue
            ideas = parse_top_ideas_file(top_ideas_file)
            label = session_path.name
            if not args.leaderboard:
                print_scorecard(ideas, session_label=label)
            sessions.append((label, ideas))

        if args.leaderboard:
            print_leaderboard(sessions)

    else:
        # Default: try to score the most recent session
        sessions = sorted(archive_dir.glob("session_*/top_ideas.md"))
        if not sessions:
            print("No archived sessions found. Run run.py first, or pass a file path.")
            sys.exit(1)
        latest = sessions[-1]
        ideas = parse_top_ideas_file(latest)
        if args.json:
            print(json.dumps([i.as_dict() for i in ideas], indent=2))
        else:
            print_scorecard(ideas, session_label=latest.parent.name)


if __name__ == "__main__":
    main()
