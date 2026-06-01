# Release

This is the release path for GitHub and extensions.blender.org.

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
4. Run the full local check:

   ```bash
   mise run lint
   mise run test
   mise run test package
   ```

5. Check the built package in `dist/`.

## GitHub release

The GitHub release workflow reads the matching section from `CHANGELOG.md`.

To preview the notes locally:

```bash
mise run --quiet release-notes -- 0.1.0
```

Create and push a tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The workflow creates or updates a draft GitHub release with:

- `dist/pasty-*.zip`
- `dist/SHA256SUMS`
- release notes copied from `CHANGELOG.md`

Review the draft release in GitHub, then publish it.

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

Then run the release workflow manually and enable the Blender Extensions upload input.

The API call shape is:

```bash
mise run --quiet release-notes -- 0.1.0 > dist/RELEASE_NOTES.md
curl -X POST "https://extensions.blender.org/api/v1/extensions/$BLENDER_EXTENSIONS_ID/versions/upload/" \
  -H "Authorization: Bearer $BLENDER_EXTENSION_TOKEN" \
  -F "version_file=@dist/pasty-0.1.0.zip" \
  -F "release_notes=<dist/RELEASE_NOTES.md"
```

Even with API upload, Blender Extensions can still review or moderate releases. Treat the API as "upload without browser clicks", not as a way around review.
