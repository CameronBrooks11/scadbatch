# Cutting a release

A release is one pushed tag. Everything after that is `.github/workflows/release.yml`, except
one approval and the archive step.

## Before the tag

1. Everything intended for the release is merged, and `main` is green. Check the per-check list
   rather than a watch's exit status, and confirm the run's `headSha` matches the commit you are
   about to tag:

   ```sh
   gh pr list                                   # nothing in flight you meant to include
   gh run list --branch main --limit 3
   gh run view <id> --json headSha --jq .headSha
   ```

2. Set the version in `pyproject.toml` and move the `## [Unreleased]` section of
   `CHANGELOG.md` under the new version with today's date, leaving a fresh empty `Unreleased`
   above it. Add the compare link at the bottom.

3. Update `CITATION.cff`: `version` and `date-released`.

4. Open that as its own pull request, like any other change, and merge it. The tag goes on the
   merged commit, not on a branch.

## The tag

The `verify` job compares the tag with the packaged version as plain strings:

```sh
version=$(...)                 # from the built distribution
tag="${GITHUB_REF_NAME#v}"
test "$version" = "$tag"
```

So `v2.0.0rc1` requires `version = "2.0.0rc1"` exactly. A difference in spelling that PEP 440
would normalise away — `2.0.0-rc1`, `2.0.0.rc1` — still fails this check.

```sh
git checkout main && git pull
git tag v2.0.0
git push origin v2.0.0
```

The workflow triggers on tags matching `v*.*.*` and nothing else.

## What runs, in order

| job | what it does |
| --- | --- |
| `verify` | the tree at the tag passes the gate, and the tag matches the packaged version |
| `dist` | builds the sdist and the wheel |
| `binaries` | freezes a one-file binary on Linux, macOS and Windows |
| `pypi` | needs all three, then **waits for an approval**, then publishes |
| `github-release` | needs all three, creates the release and attaches the binaries |

The Linux `binaries` job gives the frozen GUI a display and checks that it **opens a window**:
a GUI that starts enters `mainloop()` and never returns, so the timeout's exit status 124 is the
pass and anything else is a fault. Matching the output instead cannot tell a missing module from
a missing display — PyInstaller prints `Failed to execute script` for every unhandled exception.

`pypi` waits on all three because **PyPI never accepts a second upload of a version**. If a
binary fails for something needing a code change, publishing first would burn the version number
with nothing to go back to.

## The approval

`pypi` names the `pypi` environment, which has a `required_reviewers` rule. Verified from the
API rather than from the workflow file, because an `environment:` key alone gates nothing —
GitHub creates an environment with no rules the first time a workflow names one:

```sh
gh api repos/CameronBrooks11/scadbatch/environments \
  --jq '.environments[] | {name, rules: [.protection_rules[].type]}'
```

Approve it in the run's page, or:

```sh
gh api repos/CameronBrooks11/scadbatch/actions/runs/<id>/pending_deployments \
  -f state=approved -F environment_ids='[<id>]'
```

Publishing uses PyPI trusted publishing over OIDC: no token exists anywhere, and `id-token:
write` is granted to that one job and nowhere else. A trusted publisher is configured with the
repository, the **workflow filename** and the environment name ([PyPI's
documentation](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/) walks
through exactly that), so renaming `release.yml` breaks publishing until the PyPI configuration
is updated to match.

## After the workflow

5. Check the result rather than the workflow's say-so:

   ```sh
   curl -s https://pypi.org/pypi/scadbatch/json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['info']['version'], sorted(d['releases']))"
   uvx --from scadbatch==<version> scadbatch --help
   ```

6. The GitHub release is a prerelease unless the tag is exactly `vN.N.N` —
   `^v[0-9]+\.[0-9]+\.[0-9]+$`, so `v2.0.0rc1` is marked prerelease automatically.

7. **Zenodo.** With the Zenodo–GitHub integration enabled for the repository, publishing the
   GitHub release archives it and mints a DOI: one for the version plus a concept DOI covering
   all versions. Put the concept DOI in `CITATION.cff` and the README badge. This is the step
   that is not automated and not yet done — `CITATION.cff` carries a commented-out `doi:` field
   for it, and the integration has to be switched on first.

## Rehearsing without spending a version

A tag whose version does not match `pyproject.toml` fails `verify` immediately, which blocks
`pypi` — while `binaries` still runs in full. So a throwaway tag exercises the expensive,
platform-dependent half for free:

```sh
git tag v0.0.0-smoke && git push origin v0.0.0-smoke
# watch the binaries job; then
git tag -d v0.0.0-smoke && git push origin :refs/tags/v0.0.0-smoke
gh run delete <id>
```

This is worth doing when anything in the `binaries` job has changed. Two releases were burned on
that job being subtly wrong, and neither failure could be reproduced locally.

## If a release fails

- **Before `pypi` ran** — nothing was published. Delete the tag, fix, re-tag:

  ```sh
  git tag -d v2.0.0 && git push origin :refs/tags/v2.0.0
  ```

- **After `pypi` ran** — the number is spent: PyPI does not accept a second upload for a version
  that already exists. Fix forward with the next patch version.
