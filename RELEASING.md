# Releasing NPR

NPR follows [Semantic Versioning](https://semver.org/) and maintains user-facing changes in [CHANGELOG.md](CHANGELOG.md).

The repository is currently in controlled-pilot status. Do not create a production-stable release until the release checklist, security gates, representative-domain validation, and operational readiness requirements are satisfied.

## Release preparation

1. Start from a clean checkout of the exact `main` commit to be released.
2. Confirm [CHANGELOG.md](CHANGELOG.md) has a dated version entry with only shipped behavior.
3. Complete [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).
4. Run the complete backend and frontend checks through `./dev test` and verify GitHub Actions is green.
5. Rehearse migrations on a production-like database, including rollback where supported.
6. Verify ACL, provenance, citation, highlighting, and unsupported-answer safety gates.
7. Confirm backups, restore procedures, monitoring, alerting, and deployment rollback are ready.
8. Obtain domain approval for any legal or clinical pilot claims.

## Versioning

- **Patch**: backward-compatible bug or security fixes.
- **Minor**: backward-compatible features or optional API additions.
- **Major**: incompatible API, storage, or operational changes.

Pre-1.0 releases may use `v0.x.y` while the public contract and production operations mature.

## Tag and publish

After the release commit is merged and CI passes:

```bash
git switch main
git pull --ff-only origin main
git tag -s vX.Y.Z -m "NPR vX.Y.Z"
git push origin vX.Y.Z
gh release create vX.Y.Z --verify-tag --generate-notes --title "NPR vX.Y.Z"
```

Use an annotated tag if signed tags are not configured. Review generated notes before publishing, and add upgrade, migration, rollback, and known-limitation guidance.

## After publishing

- Verify installation and startup from the published tag.
- Confirm health checks and a representative end-to-end query.
- Monitor error rate, latency, fallback rate, and evidence-verification failures.
- Announce only capabilities that are enabled and validated in the released configuration.
- Open follow-up issues for deferred work and prepare an incident response if rollback thresholds are crossed.
