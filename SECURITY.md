# Security Policy

## Supported Versions

Security fixes are applied to the latest version on `main`.

| Version | Supported |
| ------- | --------- |
| Latest tagged release | Yes |
| `main` | Development support |
| Older releases | Best effort |

## Reporting a Vulnerability

Please do not open public issues for security vulnerabilities.

Use one of these private channels:

- Open a [private GitHub Security Advisory](https://github.com/CognitiveCodeAI/rag-main-2/security/advisories/new).
- If advisories are unavailable, contact the maintainer directly via the email listed on the repository owner profile.

Include:

- Affected component(s)
- Reproduction steps or proof of concept
- Impact assessment
- Any suggested mitigation

Do not include real client documents, protected health information, privileged
legal material, personal data, or production credentials. Use synthetic data
and the minimum proof needed to demonstrate the issue.

## In scope

Security reports may include authentication or authorization bypasses,
cross-tenant disclosure, prompt-injection paths that escape documented safety
boundaries, citation or provenance tampering, unsafe file handling, secret
exposure, dependency vulnerabilities with a demonstrated impact, and remote
code execution.

General support requests, model-quality disagreements without a security
boundary violation, and reports against unsupported third-party deployments
belong in [GitHub Discussions](https://github.com/CognitiveCodeAI/rag-main-2/discussions).

## Response Expectations

- Initial acknowledgement: within 72 hours
- Triage status update: within 7 days
- Fix timeline: depends on severity and complexity

Please allow a reasonable remediation window before public disclosure. We will
coordinate attribution and advisory publication with the reporter when
appropriate.

## Disclosure

After a fix is available, we may publish a security advisory with:

- Affected versions
- Mitigation steps
- Upgrade guidance
