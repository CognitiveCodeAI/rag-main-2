# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Public release readiness docs:
  - `RELEASE_CHECKLIST.md`
  - `CONTRIBUTING.md`
  - `SECURITY.md`
  - `.github/workflows/ci.yml`
- Professional repository governance:
  - Code of Conduct, support, maintainer, and release guides
  - structured bug and feature issue forms
  - pull-request template and CODEOWNERS
  - EditorConfig for consistent cross-platform formatting

### Changed

- CI now validates backend unit tests and frontend lint/build on pull requests and pushes to default branches.
- CI now supports manual runs, cancels superseded branch runs, and applies job timeouts.
- README now presents verified setup requirements, project status, CI badges, navigation, and community links.

## [1.0.0] - YYYY-MM-DD

### Added

- Initial public release.
