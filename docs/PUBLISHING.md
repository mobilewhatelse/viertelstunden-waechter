# Publishing checklist (maintainer)

State: 2026-10-25. Nothing here has been done except where marked. The repository is private; a draft release `v0.12.0`
exists. Work on the integration may continue before it is published - the draft can be edited or deleted.

## Already done

- [x] hassfest passes (`docker run --rm -v "${PWD}:/github/workspace" ghcr.io/home-assistant/hassfest:latest`)
- [x] Installation test on a fresh Home Assistant (`tests/install`)
- [x] 65 unit tests (`python -m unittest discover tests`)
- [x] `hacs.json` (name, render_readme, minimum Home Assistant 2026.3.0), `manifest.json` complete and sorted
- [x] Brand images in `custom_components/viertelstunden_waechter/brand/`
- [x] Repository description and 12 topics
- [x] Dual licence (`LICENSE`, `LICENSING.md`), README with "What is this for?", German guide, compatibility lists
- [x] History checked: one anonymous author address, no IPs, mail addresses, names or tokens in the repository
- [x] `CHANGELOG.md`, issue template for device test reports, draft release `v0.12.0`

## Before the repository becomes public

1. **Decide whether work continues first.** Update `CHANGELOG.md` ("Unreleased"), `manifest.json` version and the draft
   release text together.
2. Re-run the checks: unit tests, hassfest, and - for bigger changes - `tests/install/itest.py`.
3. Re-check for private data: `git grep -n -I -E "([0-9]{1,3}\.){3}[0-9]{1,3}|@[A-Za-z0-9.-]+\.[a-z]{2,}"` and the entity
   names of your own installation in examples and docs.
4. Check commit identity: all commits must use the anonymous GitHub address (checked 2026-10-25: yes).
5. Make sure no screenshots or documents with real values are in the repository (the marketing document lives in the
   private home repository, not here).

## Publishing

1. **GitHub Actions:** the token needs the `workflow` scope (`gh auth refresh -s workflow`, done by you). Then copy
   `docs/validate.yml.vorlage` to `.github/workflows/validate.yml` (hassfest, HACS validation, unit tests).
2. Switch the repository to **public** (Settings > General > Danger zone).
3. Run the workflow once: the HACS validation (`hacs/action`) only works for public repositories and also checks topics,
   description, `hacs.json` and the brand files.
4. **Publish the release** `v0.12.0` (edit the draft, check the text, publish). HACS installs the latest release.
5. Users can already add the repository as a custom repository in HACS (type *Integration*).
6. Optional later: a pull request to the HACS default list (`hacs/default`), requires a release, passing validation
   and an active maintainer. Read the current rules first.

## Naming and trademarks

"Home Assistant" is a trademark of the Open Home Foundation; describe the project as "for Home Assistant", do not use the
name or logo as a product name. Brand names of devices appear only in the compatibility lists as plain text.

## Commercial licence

`LICENSING.md` points to an issue titled "Commercial licence" or the GitHub profile. Decide whether a dedicated contact
address is wanted before publishing; do not put a private or company address into the repository.
