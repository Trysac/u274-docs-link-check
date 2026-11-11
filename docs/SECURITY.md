# Security notes

## Threat model

`trysac-docs-link-check` reads documentation files and, only through a caller-supplied checker,
the network. The main risks are:

- **Supply chain**: a compromised dependency or tool. Mitigation: no runtime dependencies; the
  development tools are pinned in `uv.lock` and updated deliberately.
- **Leaked secrets**: tokens committed by mistake. Mitigation: `gitleaks` runs in the local gates
  where available; `.env` files are git-ignored.
- **Insecure code**: shell injection, weak hashes, unsafe deserialization. Mitigation: Ruff's
  `S` rules in lint and a `security` check (Bandit, high severity fails, `# nosec` ignored); fix the
  code instead of silencing it.
- **Untrusted input**: callers may pass hostile strings. Mitigation: validate input and fail with
  explicit exceptions; never `eval`, `exec` or deserialize untrusted data.

## Publishing

Releases are published to PyPI with trusted publishing (OIDC) when available, never with a
long-lived token stored in the repository.

To report a vulnerability, see [SECURITY.md](../SECURITY.md).
