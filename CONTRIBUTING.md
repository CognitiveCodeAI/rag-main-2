# Contributing

Thanks for helping improve NPR RAG.

## Development Setup

1. Fork and clone the repository.
2. Run one of the setup scripts from repo root:
   - Linux/macOS: `./setup.sh`
   - Windows (PowerShell): `./setup.ps1`
3. Start the app:
   - `python run.py`

Key local endpoints:

- Frontend: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health?check_services=true`

## Branch and PR Workflow

- Create a feature branch from `main`.
- Keep changes focused and small when possible.
- Open a pull request with:
  - What changed
  - Why it changed
  - How you tested it
  - Any follow-up work

## Code Standards

### Backend (Python)

- Keep functions focused and testable.
- Prefer explicit error handling and actionable messages.
- Add comments only where intent is non-obvious.
- Add or update tests for behavior changes.

Run backend checks:

```bash
cd backend
pytest tests/test_acl_unit.py -q
```

### Frontend (Next.js)

- Follow existing component and naming patterns.
- Keep UI changes accessible and responsive.
- Ensure lint and build pass before opening a PR.

Run frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

## Documentation Requirements

When behavior, setup, or APIs change:

- Update `README.md` and/or `SETUP.md`.
- Keep examples copy/paste-ready.
- Remove stale instructions in the same PR.

## Reporting Bugs

Please include:

- Environment (OS, Python version, Node version)
- Steps to reproduce
- Expected behavior
- Actual behavior
- Logs/screenshots if relevant
