# Release Guide

This guide documents the workflow for cutting a new Vortex release and publishing it to PyPI.

## Prerequisites
- Access to the repository with permission to push tags.
- Configured GitHub secrets:
  - `TEST_PYPI_API_TOKEN` for TestPyPI uploads.
  - `PYPI_API_TOKEN` for production PyPI uploads.
- Installed tooling: `python -m pip install -r requirements-dev.txt`.

## Workflow
1. Ensure the `main` branch is green in CI and the changelog is up-to-date.
2. Update `vortex/__init__.py` with the new semantic version if needed.
3. Regenerate the changelog using Conventional Commit history:
   ```bash
   git log --pretty=format:"%s" <last-tag>..HEAD
   ```
4. Commit the changelog and version bump using a conventional commit message, for example:
   ```bash
   git commit -am "chore(release): cut 1.1.0"
   ```
5. Tag the release:
   ```bash
   git tag v1.1.0
   git push origin v1.1.0
   ```
6. The `Publish` workflow runs automatically:
   - Lints, tests, and builds the distribution.
   - Publishes to TestPyPI using the provided token.
   - Requires manual approval for the `pypi` environment before uploading to production PyPI.

## Manual Verification
After TestPyPI publish completes:
1. Install from TestPyPI to verify:
   ```bash
   python -m pip install --index-url https://test.pypi.org/simple/ vortex-ai
   ```
2. Run smoke tests:
   ```bash
   vortex --help
   pytest -q
   ```

## Post-Release
- Announce the release with highlights from `CHANGELOG.md`.
- Create or update GitHub milestones for the next cycle.
- Close any issues resolved by the release.
