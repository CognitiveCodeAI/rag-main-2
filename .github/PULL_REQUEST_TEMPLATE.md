## What changed?

Describe the user-visible and technical changes.

## Why?

Explain the problem, motivation, and linked issue (`Closes #123`) where applicable.

## Risk and safety

- What can fail?
- Does this affect ACLs, authentication, tenant isolation, citations, provenance, highlighting, migrations, external APIs, or stored data?
- What is the rollback path?

## Validation

- [ ] Relevant backend tests pass.
- [ ] Frontend tests, lint, type checking, and build pass when applicable.
- [ ] Integration tests cover affected service boundaries.
- [ ] Migrations were rehearsed in both directions when applicable.
- [ ] Documentation and configuration examples are updated.
- [ ] No secrets, client documents, personal data, or generated sensitive artifacts are included.

List exact commands and results:

```text
commands and results
```

## Evidence-sensitive checklist

Complete when the change affects answers or source review:

- [ ] Unsupported claims fail closed or abstain.
- [ ] Citations resolve only to authorized packed context.
- [ ] Wrong document, version, page, hash, or quote cannot be labeled verified.
- [ ] Approximate or unavailable evidence is clearly distinguished.
- [ ] Representative single-hop and multi-hop behavior was checked.

## Notes for reviewers

Call out the files, decisions, tradeoffs, or follow-up work that deserve extra attention.
