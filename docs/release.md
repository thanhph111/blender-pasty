# Release

This is the release path for GitHub and extensions.blender.org.

The rule is simple: `main` proves the commit, and a tag publishes that exact commit.

Two GitHub Actions workflows support that rule:

- `.github/workflows/checks.yml` (`Checks`) runs the fast profile on pull requests and the full profile on pushes to `main`. A successful full `main` run uploads `pasty-release-package`.
- `.github/workflows/release.yml` (`Release`) runs on `v*` tags and manual dispatches. It looks for a successful full `Checks` run for the tagged commit, downloads that package, and publishes it.

The `Release` workflow does not rerun the matrix or wait for it. If `Checks` is not green yet, `Release` fails immediately. Wait for `Checks` to pass, then rerun `Release`.

## Version notes

`CHANGELOG.md` is the source for release notes.

Write release notes for users instead of copying raw commit logs. At release time:

1. Put the useful notes under `Unreleased`.
2. Keep only sections that have entries.
3. Keep user-facing notes in plain language.

Use these version bumps:

- Patch version for bug fixes, such as `0.1.1`.
- Minor version for new user features, such as `0.2.0`.
- Major version only when a release changes or removes existing user behavior.

The extension version lives in `blender_manifest.toml`. `pyproject.toml` uses a fixed tooling placeholder with uv package mode disabled, so release version bumps do not need a lockfile refresh.

## Prepare

Set the version:

```bash
VERSION=<version>
```

Replace `<version>` with the version you are shipping.

Make sure `CHANGELOG.md` has user-facing notes under `Unreleased`, then prepare the release files:

```bash
mise run release prepare "$VERSION"
```

That command updates `blender_manifest.toml` and moves the `Unreleased` changelog notes into a dated version section.

Review the diff, then run the local release gate:

```bash
mise run lint
mise run test
mise run test package
mise run test clipboard all
mise run test linux all
```

Commit the release changes and merge or push that commit to `main`. Wait for the full `Checks` workflow on `main` to pass.

Hosted GitHub runners do not give this repo a dependable real desktop session for Blender clipboard checks on macOS and Windows. Run `mise run test clipboard all` locally on those platforms before a release.

## Publish to GitHub

Preview the notes:

```bash
mise run --quiet release notes -- "$VERSION"
```

Optionally run the same preflight checks that `ship` will run:

```bash
mise run release ship "$VERSION" --dry-run
```

Ship the release:

```bash
mise run release ship "$VERSION"
```

`ship` checks the clean tree, release notes, manifest version, uv lockfile, missing tag, and that the current commit is already on `origin/main`. It then creates and pushes the signed tag and watches the `Release` workflow.

The `Release` workflow checks that the tag points to a commit on `main` with a successful full `Checks` run, then downloads the `pasty-release-package` artifact from that run.

The full `Checks` profile covers the hosted headless and live clipboard targets chosen by `.github/workflows/scripts/plan_targets.py`.

The full `main` check keeps the release package artifact for a limited time. Ship the release while that artifact is still available.

The workflow creates or updates a draft GitHub release with:

- `dist/pasty-*.zip`
- release notes copied from `CHANGELOG.md`

Review the draft release in GitHub, then publish it.

## Recover

If a tag points at the wrong commit, remove the tag and recreate it after fixing the release commit:

```bash
VERSION=<version>
git tag -d "v$VERSION"
git push origin ":refs/tags/v$VERSION"
mise run release ship "$VERSION"
```

Remove a known-bad tag because a tag is the "publish this exact commit" signal.

If the full `Checks` run is still running, wait for it to pass and rerun `Release`. If it failed, fix the commit on `main` and tag the fixed commit. If the package artifact expired, rerun the passing `Checks` workflow before rerunning `Release`.

## Initial Blender Extensions submission

The initial Blender Extensions submission is manual:

1. Publish the GitHub release first.
2. Download the `pasty-*.zip` asset from the GitHub release.
3. Open <https://extensions.blender.org/submit/>.
4. Sign in with Blender ID.
5. Upload the same `pasty-*.zip` that the release workflow used.
6. Fill in the listing text.
7. Add screenshots and GIFs.
8. Submit for review.

The extension is held for review before it appears publicly.

## Blender Extensions API uploads

Version uploads can use the Blender Extensions API after the extension exists on the site.

Create an API token in your Blender Extensions account, then store it as a GitHub secret named:

```text
BLENDER_EXTENSION_TOKEN
```

Set a GitHub repository variable named:

```text
BLENDER_EXTENSIONS_ID
```

Use the extension slug shown on Blender Extensions after the initial submission. If Blender accepts the default slug, set it to:

```text
pasty
```

Publish the GitHub release first, then start the upload:

```bash
VERSION=<version>
mise run release upload "$VERSION"
```

The upload job verifies that the tag points to a commit on `main` with a successful full `Checks` run. It then downloads the `pasty-*.zip` asset from the GitHub release and sends that same zip to Blender Extensions. It does not rerun the matrix.

Even with API upload, Blender Extensions can still review or moderate releases. Treat the API as "upload without browser clicks", not as a way around review.
