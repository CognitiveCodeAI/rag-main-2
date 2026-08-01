# Contributing to NPR

Thank you for helping improve Near-Perfect RAG. NPR is designed for evidence-sensitive document workflows, so correctness, provenance, privacy, and clear validation matter as much as feature velocity.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you begin

- Use [GitHub Discussions](https://github.com/CognitiveCodeAI/rag-main-2/discussions) for questions and design exploration.
- Use the structured issue forms for reproducible bugs and concrete feature requests.
- Follow [SECURITY.md](SECURITY.md) for vulnerabilities; never disclose them in a public issue.
- Never upload client documents, privileged legal material, protected health information, personal data, or credentials.

## Development setup

Prerequisites:

- Docker Desktop or Docker Engine with Compose
- Python 3.12
- Node.js 20.9 or newer
- npm
- an OpenAI API key for embeddings, answer generation, and default OCR paths

Clone and initialize:

```bash
git clone https://github.com/CognitiveCodeAI/rag-main-2.git
cd rag-main-2
./dev init
./dev up
```

Useful endpoints:

- Frontend: `http://localhost:3000`
- API documentation: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health?check_services=true`

See [SETUP.md](SETUP.md) for manual setup, troubleshooting, and platform notes.

## Branch and pull-request workflow

1. Create a focused branch from the latest `main`.
2. Keep unrelated changes in separate pull requests.
3. Use a concise conventional commit where practical, such as `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, or `chore:`.
4. Complete the pull-request template, including risks, rollback, and exact test evidence.
5. Resolve review feedback and keep CI green.
6. Do not force-push shared branches or bypass repository safety rules.

## Code standards

### Backend

- Keep behavior deterministic where safety or auditability depends on it.
- Prefer explicit types, bounded work, actionable errors, and fail-closed handling.
- Add positive and negative tests for behavior changes.
- Preserve tenant and node ACL filtering before content reaches downstream models.
- Treat graph scores and model output as relevance signals, not verified truth.

Run the default backend suite:

```bash
cd backend
venv/bin/python -m pytest -q
```

Integration tests are opt-in and require the documented infrastructure:

```bash
cd backend
RUN_INTEGRATION_TESTS=1 venv/bin/python -m pytest -q
```

### Frontend

- Follow existing React, TypeScript, accessibility, and component patterns.
- Preserve keyboard navigation, visible focus, meaningful labels, and responsive layouts.
- Do not label evidence verified unless the backend returned a verified record.

Run frontend checks:

```bash
cd frontend
npm test
npm run lint
npx tsc --noEmit
npm run build
```

### Migrations

- Use the next Alembic revision number and provide both `upgrade` and `downgrade` where safe.
- Test a clean migration to `head` and the affected downgrade/upgrade cycle.
- Document operational sequencing, data backfills, and rollback limitations.

## High-assurance review requirements

Changes involving authentication, ACLs, tenant isolation, retrieval, answer generation, citations, evidence highlighting, or document provenance must include:

- exact allowed and denied cases;
- wrong-document, wrong-version, wrong-page, or stale-hash negative controls where applicable;
- proof that unavailable evidence is not promoted to verified;
- representative regression coverage;
- a safe fallback and rollback path;
- documentation that separates synthetic evaluation from production validation.

## Documentation

When behavior, setup, configuration, APIs, or operations change:

- update `README.md`, `SETUP.md`, or the relevant runbook;
- keep commands copy/paste-ready and consistent with CI;
- update `CHANGELOG.md` under `Unreleased` for user-visible changes;
- remove stale instructions in the same pull request.

## Reporting a bug

Use the bug form and include:

- environment and service versions;
- minimal safe reproduction steps;
- expected and actual behavior;
- sanitized logs or screenshots;
- the affected document type using synthetic data whenever possible.

## Review and release expectations

Maintainers may request additional security, provenance, load, or domain evaluation before accepting a change. Passing unit tests does not by itself authorize a feature for legal, clinical, or other high-stakes production use.

See [MAINTAINING.md](MAINTAINING.md) and [RELEASING.md](RELEASING.md) for stewardship and release policy.
