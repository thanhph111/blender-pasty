# Release

This is the release path for GitHub and extensions.blender.org.

The release uses two GitHub Actions workflows:

- `.github/workflows/release-candidate.yml` (`Release candidate`) runs the full checks on a `release/**` branch and uploads one package artifact.
- `.github/workflows/release.yml` (`Release`) promotes that same package from a tag into a draft GitHub release.

Keep this rule simple: build once, then promote the same zip. A tag must not rebuild or retest.

## Changelog

`CHANGELOG.md` is the source for release notes.

Keep it human-written. Do not paste raw commit logs into it. At release time:

1. Move the useful `Unreleased` entries into a new version section.
2. Use the date format `YYYY-MM-DD`.
3. Keep only sections that have entries.
4. Keep user-facing notes in plain language.

Use these version bumps:

- Patch version for bug fixes, such as `0.1.1`.
- Minor version for new user features, such as `0.2.0`.
- Major version only when a release changes or removes existing user behavior.

## Before release

1. Update `CHANGELOG.md`.
2. Update `blender_manifest.toml`.
3. Keep `pyproject.toml` version in sync.
4. Run the local checks:

   ```bash
   mise run lint
   mise run test
   mise run test package
   ```

5. Check the built package in `dist/`.

## Release candidate

Create a release branch from the commit you want to ship:

```bash
git switch -c release/v0.1.0
git push origin release/v0.1.0
```

This starts `Release candidate`. It runs the full matrix:

- Linux on Blender 4.2, 4.5, and current stable
- Windows on Blender 4.2, 4.5, and current stable
- macOS Apple Silicon on Blender 4.2, 4.5, and current stable

The workflow uploads one artifact named `pasty-release-package`. It contains:

- `dist/pasty-*.zip`
- `dist/SHA256SUMS`

Use the workflow run ID from this candidate when promoting manually. You can find it in the workflow URL:

```text
https://github.com/<owner>/<repo>/actions/runs/<run_id>
```

You can also list recent builds:

```bash
gh run list --workflow release-candidate.yml
```

## GitHub release

The GitHub release workflow reads the matching section from `CHANGELOG.md`. It does not build the zip. It finds a successful `Release candidate` run for the same commit and downloads `pasty-release-package`.

To preview the notes locally:

```bash
mise run --quiet release-notes -- 0.1.0
```

After the release candidate passes, create and push a signed annotated tag:

```bash
git tag -s v0.1.0 -m "Pasty 0.1.0"
git push origin v0.1.0
```

The workflow creates or updates a draft GitHub release with:

- `dist/pasty-*.zip`
- `dist/SHA256SUMS`
- release notes copied from `CHANGELOG.md`

Review the draft release in GitHub, then publish it.

If the automatic build lookup ever cannot find the right run, start the release workflow manually and pass the `Release candidate` run ID.

## Failed tag recovery

If a tag points at the wrong commit or starts a broken release workflow, remove the tag and recreate it after the release branch build passes:

```bash
git tag -d v0.1.0
git push origin :refs/tags/v0.1.0
git tag -s v0.1.0 -m "Pasty 0.1.0"
git push origin v0.1.0
```

Do not leave a known-bad tag in the repository. A tag is the "promote this exact build" signal.

## First Blender Extensions submission

The first Blender Extensions submission is manual:

1. Build the zip:

   ```bash
   mise run test package
   ```

2. Open <https://extensions.blender.org/submit/>.
3. Sign in with Blender ID.
4. Upload `dist/pasty-0.1.0.zip`.
5. Fill in the listing text.
6. Add screenshots and GIFs.
7. Submit for review.

The extension is held for review before it appears publicly.

## Later Blender Extensions releases

Later version uploads can use the Blender Extensions API after the extension exists on the site.

Create an API token in your Blender Extensions account, then store it as a GitHub secret named:

```text
BLENDER_EXTENSION_TOKEN
```

Set a GitHub repository variable named:

```text
BLENDER_EXTENSIONS_ID
```

For Pasty this should probably be:

```text
pasty
```

Then run the release workflow manually, pass the tag, and enable the Blender Extensions upload input.

The API call shape is:

```bash
mise run --quiet release-notes -- 0.1.0 > dist/RELEASE_NOTES.md
curl -X POST "https://extensions.blender.org/api/v1/extensions/$BLENDER_EXTENSIONS_ID/versions/upload/" \
  -H "Authorization: Bearer $BLENDER_EXTENSION_TOKEN" \
  -F "version_file=@dist/pasty-0.1.0.zip" \
  -F "release_notes=<dist/RELEASE_NOTES.md"
```

Even with API upload, Blender Extensions can still review or moderate releases. Treat the API as "upload without browser clicks", not as a way around review.
