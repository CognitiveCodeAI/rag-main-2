# Maintaining NPR

This guide covers repository stewardship. Application setup and deployment are documented separately in [SETUP.md](SETUP.md) and [backend/docs/DEPLOYMENT_GUIDE.md](backend/docs/DEPLOYMENT_GUIDE.md).

## Maintainer responsibilities

- Keep `main` releasable and require passing CI for merged changes.
- Protect document provenance, tenant isolation, citation integrity, and fail-closed behavior.
- Triage security reports privately and follow [SECURITY.md](SECURITY.md).
- Keep setup, deployment, support, and release documentation current.
- Avoid representing synthetic evaluation results as production legal or clinical validation.
- Preserve a reversible rollout path for migrations and feature flags.

## Pull-request workflow

1. Keep each pull request focused on one coherent change.
2. Require a clear problem statement, risk assessment, and validation evidence.
3. Confirm all required GitHub Actions checks pass.
4. Require explicit review of migrations, ACL behavior, external API use, and provenance changes.
5. Prefer squash merging unless commit history materially improves auditability.
6. Delete merged branches automatically.

Direct force pushes and branch deletion are blocked on `main`. Emergency changes still use a pull request so CI and the audit trail remain intact.

## Issue triage

- Confirm the report contains reproducible evidence and no confidential data.
- Apply a type label (`bug`, `enhancement`, `docs`, `security`, or `chore`) and priority where justified.
- Move support questions to Discussions.
- Handle suspected vulnerabilities through private advisories.
- Close stale or superseded issues with a concise explanation.

## Dependency and security maintenance

- Review Dependabot pull requests weekly.
- Treat critical and high-severity findings as release blockers unless a documented risk acceptance applies.
- Keep GitHub secret scanning, push protection, and Dependabot security updates enabled.
- Never commit production secrets, client documents, or generated data containing sensitive material.

## High-assurance changes

Changes touching ACLs, citations, highlighting, ingestion provenance, authentication, or tenant boundaries require:

- positive and negative tests;
- fail-closed behavior for missing or conflicting provenance;
- relevant integration coverage;
- a documented rollback path;
- representative human review before a production default-on decision.

## Releases

Use [RELEASING.md](RELEASING.md) and [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). Git tags and GitHub Releases describe code already merged to `main`; they are not a substitute for deployment approval.
