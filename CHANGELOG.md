# Changelog

All notable changes to this project. This project adheres to semantic versioning.

## v0.2.2 — 2026-11-15

- Attach a CycloneDX SBOM to each release (covered by the signed checksums)

## v0.2.1 — 2026-11-15

- Sign release checksums with Sigstore (keyless) and attach the `.sigstore.json` bundle
- Add property/fuzz hardening tests for the AES-256-GCM + scrypt envelope

## v0.2.0 — 2026-11-14

- Add per-file progress for folder encryption/decryption
- Add an optional key-file as a second factor
- Add encrypt-folder / decrypt-folder
- Add shell-completion generation (bash and zsh)
- Add a security policy
- Factor character variety into the passphrase meter
- Docs: point install at the live v0.1.0 release

## v0.1.0

- Initial public release.
