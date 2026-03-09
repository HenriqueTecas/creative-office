#!/usr/bin/env python3
"""
Creative Office UI Server — serves parsed session data + live status to the dashboard.

Usage:
    cd ~/creative_office && python ui/server.py
    cd ~/creative_office && python ui/server.py --port 8080
"""

import os
import re
import json
import time
import argparse
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE_DIR = Path(__file__).parent.parent  # creative_office/
UI_DIR = Path(__file__).parent  # creative_office/ui/
ARCHIVE_DIR = BASE_DIR / "archive"
ROOM_FILE = BASE_DIR / "room.md"
SEEDS_DIR = BASE_DIR / "seeds" / "pending"

# Simple cache for parsed sessions
SESSION_CACHE = {}
SESSION_CACHE_TIME = {}
CACHE_TTL = 60  # Cache for 60 seconds

AGENTS = ["generator", "critic", "builder", "mutant", "editor"]

AGENT_HEADERS = {
    "Generator Output": "generator",
    "Critic Response": "critic",
    "Builder Response": "builder",
    "Mutant Output": "mutant",
    "Editor Summary": "editor",
}

NEXT_AGENT = {
    "generator": "critic",
    "critic": "builder",
    "builder": "mutant",
    "mutant": "editor",
    "editor": "generator",
}

WEIGHTS = {
    "novelty": 2.0,
    "timing": 1.0,
    "desire": 1.5,
    "buildability": 1.0,
    "strangeness": 2.0,
    "survivability": 1.0,
}
WEIGHT_SUM = sum(WEIGHTS.values())


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_killed_ideas(content: str) -> list:
    """
    Extract killed idea names from Critic output.
    Handles formats:
      **[NAME] — KILL**
      **[NAME] — KILL / ...**
      **NAME — KILL**
    """
    killed = []
    patterns = [
        # **[Name] — KILL** or **[Name] — KILL / ...**
        r"\*\*\[([^\]]+)\]\s*[—\-–]+\s*KILL",
        # **Name — KILL**
        r"\*\*([^\[\*\n]+?)\s*[—\-–]+\s*KILL",
        # KILL: **Name** or killed **Name**
        r"KILL(?:ED)?\b[^\n]*\*\*\[?([^\]\*\n]+?)\]?\*\*",
        # derivative/unfeasible signal
        r"\*\*\[?([^\]\*\n]+?)\]?\*\*[^\n]*(?:unfeasible|saturated|already exists|direct match)",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, content, re.IGNORECASE):
            name = m.group(1).strip().rstrip("]").strip()
            if name and name not in killed:
                killed.append(name)
    return killed


def parse_generator_ideas(content: str) -> list:
    ideas = []
    # Match numbered: **1. NAME** and unnumbered: **NAME** followed by content and *Timing:*
    patterns = [
        r"\*\*\d+\.\s*([A-Z][A-Z0-9\s]+)\*\*\s*\n\n(.*?)(?:\*Timing:\*(.*?))(?=\n---|\n\*\*\d+\.|\Z)",
        r"(?<!\d\.)\*\*([A-Z]{2,}[A-Z0-9\s]+)\*\*\s*\n\n(.*?)(?:\*Timing:\*(.*?))(?=\n---|\n\*\*[A-Z]|\Z)",
    ]
    seen = set()
    for pattern in patterns:
        for m in re.finditer(pattern, content, re.DOTALL):
            name = m.group(1).strip()
            if name in seen or len(name) < 2:
                continue
            seen.add(name)
            pitch = m.group(2).strip()
            timing = m.group(3).strip() if m.group(3) else ""
            ideas.append(
                {
                    "name": name,
                    "pitch": pitch,
                    "timing": timing,
                    "domains": extract_domains(pitch),
                    "status": "generated",
                    "journey": [
                        {"agent": "generator", "action": "Generated initial idea"}
                    ],
                }
            )
    return ideas


def parse_mutants(content: str) -> list:
    mutants = []
    # Match mutant format: **NAME** followed by **Operation:** and **Concept:**
    pattern = r"\*\*([A-Z]{2,}[A-Z0-9\s]+)\*\*\s*\n\n\*\*Operation:\*\*.*?\n\n\*\*Concept:\*\*\s*(.*?)(?=\n\n---|\n\*\*[A-Z]{2,}|\Z)"
    for m in re.finditer(pattern, content, re.DOTALL):
        name = m.group(1).strip()
        concept = m.group(2).strip()
        mutants.append(
            {
                "name": f"{name}",
                "pitch": concept,
                "timing": "Mutant hybrid",
                "domains": extract_domains(concept),
                "status": "mutated",
                "journey": [
                    {"agent": "mutant", "action": "Created hybrid from existing ideas"}
                ],
            }
        )
    return mutants


def parse_built_specs(content: str) -> list:
    built = []
    patterns = [
        r"\*\*([^\*\n]+)\*\*[^\n]*\n\s*\*\*MVP",
        r"^\*\*([^\*\n]+)\*\*\s*$",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE):
            name = m.group(1).strip()
            if name and name not in built:
                built.append(name)
    return built


def parse_editor_scores(content: str, ideas: list):
    """
    Parse scores from editor summary sections.
    Format: **#1: NAME** (Composite: X.X) ... Scores: Novelty X | Timing X | ...
    """
    score_re = re.compile(
        r"Scores?:\s*"
        r"Novelty\s*(\d+(?:\.\d+)?)\s*\|?\s*"
        r"Timing\s*(\d+(?:\.\d+)?)\s*\|?\s*"
        r"Desire\s*(\d+(?:\.\d+)?)\s*\|?\s*"
        r"Buildability\s*(\d+(?:\.\d+)?)\s*\|?\s*"
        r"Strangeness\s*(\d+(?:\.\d+)?)\s*\|?\s*"
        r"Survivability\s*(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    idea_header_re = re.compile(
        r"\*\*#\d+[:.]\s*([^\*\(\n]+?)(?:\s*\(Composite[^)]*\))?\*+",
        re.IGNORECASE,
    )

    # Get the last editor summary (final round)
    editor_matches = list(
        re.finditer(r"## Editor Summary[^\n]*\n\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
    )
    if not editor_matches:
        return

    # Use the last editor summary
    section_text = editor_matches[-1].group(1)

    # Split into per-idea blocks by ranked headers
    blocks = re.split(r"(?=\*\*#\d+[:.]\s)", section_text)
    for block in blocks:
        header_m = idea_header_re.match(block)
        score_m = score_re.search(block)
        if not header_m or not score_m:
            continue

        idea_name = header_m.group(1).strip()
        scores = {
            "novelty": float(score_m.group(1)),
            "timing": float(score_m.group(2)),
            "desire": float(score_m.group(3)),
            "buildability": float(score_m.group(4)),
            "strangeness": float(score_m.group(5)),
            "survivability": float(score_m.group(6)),
        }
        composite = round(sum(scores[k] * WEIGHTS[k] for k in scores) / WEIGHT_SUM, 2)

        # Match to idea by name
        for idea in ideas:
            clean_idea = idea["name"].lower().replace(" (mutant)", "")
            clean_name = idea_name.lower()
            if clean_name in clean_idea or clean_idea in clean_name:
                idea["scores"] = scores
                idea["composite"] = composite
                idea["status"] = "selected"
                if not any(s["agent"] == "editor" for s in idea["journey"]):
                    idea["journey"].append(
                        {
                            "agent": "editor",
                            "action": f"Scored (composite: {composite})",
                        }
                    )
                break


def extract_domains(text: str) -> list:
    keywords = [
        "AI",
        "Quantum",
        "Blockchain",
        "Neural",
        "Bio",
        "Crypto",
        "Finance",
        "Health",
        "Education",
        "Energy",
        "Transport",
        "Agriculture",
        "Manufacturing",
        "Entertainment",
        "Gaming",
        "Social",
        "Security",
        "Climate",
        "Space",
        "Robotics",
        "Biology",
        "Economics",
        "Psychology",
        "Logistics",
        "Military",
        "Infrastructure",
    ]
    found = [k for k in keywords if k.upper() in text.upper()]
    return found[:3] if found else ["Technology", "Innovation"]


def mark_ideas_killed(ideas: list, killed_names: list):
    for idea in ideas:
        for kn in killed_names:
            if kn.lower() in idea["name"].lower():
                idea["status"] = "killed"
                if not any(s["agent"] == "critic" for s in idea["journey"]):
                    idea["journey"].append({"agent": "critic", "action": "Killed idea"})


def mark_ideas_built(ideas: list, built_names: list):
    for idea in ideas:
        for bn in built_names:
            if bn.lower() in idea["name"].lower():
                if idea["status"] != "killed":
                    idea["status"] = "built"
                if not any(s["agent"] == "builder" for s in idea["journey"]):
                    idea["journey"].append(
                        {"agent": "builder", "action": "Built technical specification"}
                    )


# ---------------------------------------------------------------------------
# Room parsing
# ---------------------------------------------------------------------------


def parse_room_file(room_path: Path) -> dict:
    if not room_path.exists():
        return None

    content = room_path.read_text(encoding="utf-8")

    session_m = re.search(r"# Session: (.+)", content)
    date_m = re.search(r"## Started: (.+)", content)
    session_name = session_m.group(1).strip() if session_m else "Unknown"
    session_date = date_m.group(1).strip() if date_m else "Unknown"

    rounds = []
    all_ideas = []
    stats = {
        "ideasGenerated": 0,
        "ideasKilled": 0,
        "specsBuilt": 0,
        "hybridsCreated": 0,
        "roundsCompleted": 0,
        "ideasSurvived": 0,
    }

    for round_m in re.finditer(
        r"## Round (\d+)\n(.*?)(?=## Round \d+|\Z)", content, re.DOTALL
    ):
        round_num = int(round_m.group(1))
        round_content = round_m.group(2)
        stats["roundsCompleted"] = round_num
        interactions = []

        for header, agent in AGENT_HEADERS.items():
            agent_m = re.search(
                rf"### {header}\n\n(.*?)(?=### |\Z)", round_content, re.DOTALL
            )
            if not agent_m:
                continue

            agent_content = agent_m.group(1).strip()
            summary = (
                (agent_content[:200] + "...")
                if len(agent_content) > 200
                else agent_content
            )
            summary = summary.replace("\n", " ")

            interactions.append(
                {
                    "agent": agent,
                    "summary": summary,
                    "content": agent_content,
                }
            )

            if agent == "generator":
                ideas = parse_generator_ideas(agent_content)
                stats["ideasGenerated"] += len(ideas)
                all_ideas.extend(ideas)

            elif agent == "critic":
                killed = parse_killed_ideas(agent_content)
                stats["ideasKilled"] += len(killed)
                mark_ideas_killed(all_ideas, killed)

            elif agent == "builder":
                built = parse_built_specs(agent_content)
                stats["specsBuilt"] += len(built)
                mark_ideas_built(all_ideas, built)

            elif agent == "mutant":
                mutants = parse_mutants(agent_content)
                stats["hybridsCreated"] += len(mutants)
                all_ideas.extend(mutants)

        rounds.append({"round": round_num, "interactions": interactions})

    stats["ideasSurvived"] = len([i for i in all_ideas if i["status"] != "killed"])
    parse_editor_scores(content, all_ideas)

    scored = [i for i in all_ideas if i.get("composite")]
    stats["avgCompositeScore"] = (
        round(sum(i["composite"] for i in scored) / len(scored), 2) if scored else 0
    )

    return {
        "id": room_path.parent.name,
        "name": session_name,
        "date": session_date,
        "stats": stats,
        "rounds": rounds,
        "ideas": all_ideas,
    }


# ---------------------------------------------------------------------------
# Live session status
# ---------------------------------------------------------------------------


def get_live_status() -> dict:
    if not ROOM_FILE.exists():
        return {"running": False, "reason": "no_room_file"}

    content = ROOM_FILE.read_text(encoding="utf-8")
    mtime = ROOM_FILE.stat().st_mtime
    age = int(time.time() - mtime)
    is_running = age < 600  # modified in last 10 minutes

    # Current round
    round_matches = list(re.finditer(r"## Round (\d+)", content))
    current_round = int(round_matches[-1].group(1)) if round_matches else 0

    # Last completed agent
    header_matches = list(
        re.finditer(
            r"### (Generator Output|Critic Response|Builder Response|Mutant Output|Editor Summary)",
            content,
        )
    )
    last_completed = None
    next_agent = "generator"
    if header_matches:
        last_header_name = header_matches[-1].group(1)
        last_completed = AGENT_HEADERS.get(last_header_name)
        next_agent = NEXT_AGENT.get(last_completed, "generator")

    # Session name
    session_m = re.search(r"# Session: (.+)", content)
    session_name = session_m.group(1).strip() if session_m else ""

    # Recent output — last 30 lines
    lines = content.splitlines()
    recent_lines = "\n".join(lines[-30:]) if len(lines) > 30 else content

    return {
        "running": is_running,
        "session_name": session_name,
        "current_round": current_round,
        "last_completed_agent": last_completed,
        "next_agent": next_agent if is_running else None,
        "last_modified_seconds": age,
        "recent_output": recent_lines,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def log_message(self, format, *args):
        pass  # Suppress request logs

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api_get(parsed)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/seeds":
            self.handle_create_seed()
        else:
            self.send_error(404, "Not Found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def handle_api_get(self, parsed):
        parts = parsed.path.split("/")

        if len(parts) >= 3 and parts[2] == "sessions":
            if len(parts) == 3:
                self.send_json(self.list_sessions())
            elif len(parts) == 4:
                self.send_json(self.get_session(parts[3]))
            else:
                self.send_error(404)

        elif len(parts) >= 3 and parts[2] == "live":
            self.send_json(get_live_status())

        else:
            self.send_error(404, "Not Found")

    def handle_create_seed(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))

            title = body.get("title", "untitled").strip() or "untitled"
            slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")

            lines = [f"# Seed: {title}\n"]
            for field, label in [
                ("domain", "Domain"),
                ("temporal_frame", "Temporal Frame"),
                ("constraints", "Constraints"),
                ("provocation", "Provocation"),
                ("anti_targets", "Anti-targets"),
            ]:
                val = body.get(field, "").strip()
                if val:
                    lines.append(f"\n## {label}\n{val}\n")

            SEEDS_DIR.mkdir(parents=True, exist_ok=True)
            seed_path = SEEDS_DIR / f"{slug}.md"
            seed_path.write_text("\n".join(lines), encoding="utf-8")

            self.send_json(
                {"success": True, "filename": f"{slug}.md", "path": str(seed_path)}
            )

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def list_sessions(self) -> list:
        sessions = []
        if not ARCHIVE_DIR.exists():
            return sessions
        for d in sorted(ARCHIVE_DIR.glob("session_*"), reverse=True):
            info = {"id": d.name, "name": d.name, "date": ""}
            meta = d / "metadata.json"
            if meta.exists():
                try:
                    m = json.loads(meta.read_text())
                    info["date"] = m.get("timestamp", "")
                    # Try to get session name from room file
                    room = d / "room_full.md"
                    if room.exists():
                        sm = re.search(
                            r"# Session: (.+)", room.read_text(encoding="utf-8")
                        )
                        if sm:
                            info["name"] = sm.group(1).strip()
                except Exception:
                    pass
            sessions.append(info)
        return sessions

    def get_session(self, session_id: str) -> dict:
        import time

        # Check cache first
        now = time.time()
        if session_id in SESSION_CACHE and session_id in SESSION_CACHE_TIME:
            if now - SESSION_CACHE_TIME[session_id] < CACHE_TTL:
                return SESSION_CACHE[session_id]

        # Parse and cache
        room = ARCHIVE_DIR / session_id / "room_full.md"
        if room.exists():
            data = parse_room_file(room)
            if data:
                SESSION_CACHE[session_id] = data
                SESSION_CACHE_TIME[session_id] = now
                return data

        return {
            "id": session_id,
            "name": session_id,
            "date": "",
            "stats": {
                "ideasGenerated": 0,
                "ideasKilled": 0,
                "specsBuilt": 0,
                "hybridsCreated": 0,
                "roundsCompleted": 0,
                "ideasSurvived": 0,
                "avgCompositeScore": 0,
            },
            "rounds": [],
            "ideas": [],
        }

    def send_json(self, data):
        body = json.dumps(data, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Creative Office UI Server")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    httpd = HTTPServer(("", args.port), DashboardHandler)
    print(f"Creative Office Dashboard → http://localhost:{args.port}")
    print(f"Workspace:  {BASE_DIR}")
    print(f"Archive:    {ARCHIVE_DIR}")
    print("Ctrl+C to stop\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
