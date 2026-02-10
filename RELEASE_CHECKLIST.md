# Public Release Checklist

Use this checklist before every public release. A release is ready only when all required items pass.

## Release Gate

- [ ] `README.md` and `SETUP.md` are accurate and tested from scratch on a clean machine.
- [ ] Setup scripts (`setup.sh`, `setup.ps1`) are idempotent and complete a full local bootstrap.
- [ ] Backend and frontend quality checks pass in CI.
- [ ] No secrets, local artifacts, or proprietary files are included.
- [ ] Security disclosure process exists and is documented.
- [ ] Changelog has a clear release summary.

## 1. Documentation Quality

Owner: Maintainer

- [ ] `README.md` contains: project purpose, architecture overview, quick start, troubleshooting, API/docs links.
- [ ] `SETUP.md` contains: prerequisites, one-command setup, manual fallback path, troubleshooting, cleanup/reset.
- [ ] Every command in docs was executed at least once during this release cycle.
- [ ] Expected success outputs are documented for key checks:
  - [ ] `http://localhost:8000/health`
  - [ ] `http://localhost:8000/docs`
  - [ ] `http://localhost:3000`
- [ ] Internal-only or stale notes are removed from top-level docs.

Acceptance evidence:

- Command transcript or short log attached to PR.
- Reviewer confirms links/commands are valid.

## 2. Setup and Database Bootstrap

Owner: Maintainer

- [ ] `./setup.sh` works on Linux/macOS.
- [ ] `./setup.ps1` works on Windows PowerShell.
- [ ] Re-running setup does not fail and does not duplicate resources.
- [ ] Database setup step runs successfully (`python -m scripts.setup.setup_all`).
- [ ] Connection verification passes (`python -m scripts.setup.verify_connections`).
- [ ] Failure messages are actionable (what failed, how to fix).

Acceptance evidence:

- Fresh run output (new environment).
- Re-run output (idempotency check).

## 3. Code Quality and Comments

Owner: Maintainer

- [ ] Backend unit tests pass:
  - [ ] `cd backend && pytest tests/test_acl_unit.py -q`
- [ ] Frontend lint and build pass:
  - [ ] `cd frontend && npm run lint`
  - [ ] `cd frontend && npm run build`
- [ ] Complex logic has concise comments explaining intent (not obvious line-by-line commentary).
- [ ] Dead code, TODO placeholders, and debug prints are removed or converted to tracked issues.

Acceptance evidence:

- CI green on default branch and release PR.

## 4. Security and Safety

Owner: Maintainer

- [ ] `.env`, `venv`, `node_modules`, and local outputs are not committed.
- [ ] No API keys, tokens, passwords, or internal endpoints in docs/examples.
- [ ] `SECURITY.md` exists with a reporting path and response expectations.
- [ ] Dependency updates reviewed for critical vulnerabilities.

Acceptance evidence:

- Secret scan output attached to PR.
- Manual spot-check of changed files completed.

## 5. Repository Professionalism

Owner: Maintainer

- [ ] `CONTRIBUTING.md` explains setup, coding standards, and PR process.
- [ ] `CHANGELOG.md` includes release notes in a consistent format.
- [ ] Clear issue and PR descriptions used for all release changes.
- [ ] Version/tag strategy decided before publishing (for example: `v1.0.0`).

Acceptance evidence:

- Reviewer verifies docs are present and usable by a new contributor.

## 6. Final Dry Run Before Publish

Owner: Maintainer + External tester

- [ ] One tester with no prior context follows `README.md` only.
- [ ] One tester follows `SETUP.md` only.
- [ ] Both can run the app and open API docs without direct support.
- [ ] All friction points are fixed or tracked before tag/release.

Acceptance criteria:

- 0 blocker issues.
- No silent setup failures.
- CI passing.
