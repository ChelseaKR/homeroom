"""The optional question-answering layer (ADR 0003).

Everything in this package answers about one school at a time, from that
school's published records and a committed corpus of CDE's own definitions, and
nothing it produces reaches a reader without passing the verifier. The package
imports the ``anthropic`` SDK lazily and only in :mod:`homeroom.ask.provider`,
so the rest of the project stays stdlib-only and ``make verify`` needs no
credential.
"""
