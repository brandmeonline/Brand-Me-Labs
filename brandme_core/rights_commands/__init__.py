"""Authenticated rights command service (python -m brandme_core.rights_commands).

A private HTTP process behind the gateway, separate from the read-only read API.
It creates transfer intents, binds recipients, evaluates reprint quotes and
authorizes ownership-proof challenges. It never holds a wallet, a witness or a
prover, and never broadcasts a transaction. See README.md.
"""
