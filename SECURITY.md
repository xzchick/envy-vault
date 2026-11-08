# Security policy

ENVY Vault is an offline, local tool: no server, no network calls, no accounts —
so there is no hosted surface to attack. The parts that matter are the
cryptography (AES-256-GCM with an scrypt-derived key) and the file handling
(never overwrite an existing file, never follow symlinks).

## Reporting a vulnerability

Please report security issues **privately**, using GitHub's *"Report a
vulnerability"* button under this repository's **Security** tab, rather than
opening a public issue. Include the version, your operating system, and steps to
reproduce. Reports are acknowledged as quickly as possible.

## Scope

In scope: the encryption envelope, key derivation, and the file read/write paths.

Out of scope: the strength of a weak passphrase you choose (use a long one — the
app enforces a 12-character minimum), and anything that requires an attacker to
already have your passphrase or local user account.
