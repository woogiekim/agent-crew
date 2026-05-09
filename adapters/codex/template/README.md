# Codex Compatibility Template

This directory contains only Codex-specific template assets that cannot be shared
with the provider-neutral `core/` source.

Canonical hooks, commands, and agent guidance live under `core/`. The Codex
setup flow composes `.codex/` by combining those canonical assets with the
adapter-specific files in this template.

Do not treat generated `.codex/` output as a source of truth.
