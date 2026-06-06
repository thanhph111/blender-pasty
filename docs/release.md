# Release

This is the release path for GitHub and extensions.blender.org.

The release uses two GitHub Actions workflows:

- `.github/workflows/release-candidate.yml` (`Release candidate`) runs the full checks on a `release/**` branch and uploads one package artifact.
- `.github/workflows/release.yml` (`Release`) promotes that same package from a tag into a draft GitHub release.

Keep this rule simple: build once, then promote the same zip. A tag must not rebuild or retest.

## Changelog

`CHANGELOG.md` is the source for release notes.

Write release notes for users instead of copying raw commit logs. At release time:

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
   mise run test clipboard all
   mise run test linux all
   ```

5. Check the built package in `dist/`.

## Release candidate

Create a release branch from the commit you want to ship:

```bash
git switch -c release/v0.1.0
git push origin release/v0.1.0
```

This starts `Release candidate`. It runs the full matrix:

- Linux on Blender 4.2, 4.5, and 5.1
- Windows on Blender 4.2, 4.5, and 5.1
- macOS Apple Silicon on Blender 4.2, 4.5, and 5.1
- Live clipboard checks on Linux X11 for Blender 4.2, 4.5, and 5.1
- Live clipboard checks on Linux Wayland for Blender 4.2 and 5.1

Hosted GitHub runners do not give this repo a dependable real desktop session for Blender clipboard checks on macOS and Windows. Run `mise run test clipboard all` locally on those platforms before a release when you can.

Blender 4.5 is not a hosted Linux Wayland live clipboard gate because Blender exits in headless Sway during image paste before Pasty can write a result. It is still covered by Linux X11 live clipboard checks and the full headless matrix.

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

Remove a known-bad tag because a tag is the "promote this exact build" signal.

## First Blender Extensions submission

The first Blender Extensions submission is manual:

1. Publish the GitHub release first.
2. Download the `dist/pasty-*.zip` asset from the GitHub release, or download the `pasty-release-package` artifact from the matching successful `Release candidate` run.
3. Open <https://extensions.blender.org/submit/>.
4. Sign in with Blender ID.
5. Upload the same `pasty-*.zip` that was promoted by GitHub release.
6. Fill in the listing text.
7. Add screenshots and GIFs.
8. Submit for review.

For Blender Extensions submission, use the same zip that passed the release-candidate workflow.

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

Use the extension slug shown on Blender Extensions after the first submission. If Blender accepts the default slug, set it to:

```text
pasty
```

Then run the release workflow manually, pass the tag, and enable the Blender Extensions upload input.

The API call shape is:

```bash
VERSION=<version>
mise run --quiet release-notes -- "$VERSION" > dist/RELEASE_NOTES.md
curl -X POST "https://extensions.blender.org/api/v1/extensions/$BLENDER_EXTENSIONS_ID/versions/upload/" \
  -H "Authorization: Bearer $BLENDER_EXTENSION_TOKEN" \
  -F "version_file=@dist/pasty-$VERSION.zip" \
  -F "release_notes=<dist/RELEASE_NOTES.md"
```

Even with API upload, Blender Extensions can still review or moderate releases. Treat the API as "upload without browser clicks", not as a way around review.
