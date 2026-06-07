"""Privacy & data-protection controls (see PRIVACY.md).

Encryption at rest, authentication + RBAC, and transport hardening. Every control
is config-gated (see app/config.py) and OFF by default so the open demo runs
unchanged; switching it on in backend/.env gives the real, enforced behaviour.
"""
