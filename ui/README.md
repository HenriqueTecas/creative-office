# Creative Office Dashboard

A visual dashboard for monitoring agent interactions in the Creative Office multi-agent brainstorming system.

## Features

- **Overview Tab**: See agent statistics, interaction flow, and session metrics
- **Interactions Tab**: Round-by-round timeline of agent contributions
- **Ideas Pipeline Tab**: Track ideas through the generation pipeline
- **Scores Tab**: Detailed breakdown of idea scores across all dimensions

## Quick Start

### Option 1: Python Server (Recommended)

```bash
# From the creative_office directory
cd ui
python server.py --port 8000
```

Then open http://localhost:8000 in your browser.

### Option 2: Direct File Access

You can open `index.html` directly in your browser, but you'll only see demo data since the API endpoints won't be available.

## Data Source

The dashboard reads from:
- `archive/session_*/room_full.md` - Full session transcripts
- `archive/session_*/metadata.json` - Session metadata

## Architecture

```
ui/
├── index.html      # Main HTML structure
├── app.js          # Dashboard logic and rendering
├── server.py       # Python API server
└── README.md       # This file
```

## API Endpoints

- `GET /api/sessions` - List all sessions
- `GET /api/sessions/{session_id}` - Get detailed session data

## Demo Mode

If no session data is available, the dashboard loads with demo data showing example agent interactions.

## Screenshots

The dashboard features:
- Dark theme with agent color coding
- Interactive charts showing score distributions
- Clickable idea cards with detailed modal views
- Real-time timeline of agent interactions

## Agent Colors

- **Generator**: Purple (#8b5cf6)
- **Critic**: Red (#ef4444)
- **Builder**: Blue (#3b82f6)
- **Mutant**: Green (#10b981)
- **Editor**: Amber (#f59e0b)
