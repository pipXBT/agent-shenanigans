# Cleanup scope discipline

The rules every code-cleanup fork inherits during recon. They constrain *how far* a
fork goes — the "when to stop / don't over-correct" guard that the per-concern
mandates (dedup, dead code, weak types, …) don't supply on their own.

Recon reads this file aloud so it enters the shared conversation and every fork
inherits it. If a project ships its own `.agent/rules.md`, those rules are read too
and **win over these on conflict**.

## Primary bias to correct

A cleanup agent's dominant failure mode is **over-correction**: broadening scope past
its mandate, inventing abstractions "for flexibility," deleting code whose external
reachability it never checked, and disguising a behavior change as a tidy-up. Every
rule below cuts off one of those.

## Decision rules (every fork obeys)

1. **Clean within your mandate only.** Working code is not automatically *done* — but
   only tidy what your mandate names. When cleanup starts spreading into unrelated
   areas, cut back to the smallest change that satisfies the mandate. Report the rest
   as follow-ups; don't chase it.
2. **Separate structural change from behavioral change.** Never disguise a feature,
   migration, or redesign as cleanup. Preserve observable behavior. Never delete or
   weaken a failing test to make the suite green.
3. **No speculative abstraction.** *Removing* a wrapper / interface / parameter-object
   / superclass that has no real caller is in scope. *Adding* one is not — don't
   introduce a layer for hypothetical future flexibility.
4. **Reachability before deletion.** Delete dead or dispensable code only after
   checking reflected, serialized, generated, plugin-facing, dynamically-dispatched,
   and test-only uses. Grep the full tree first.
5. **Rule of Three for duplication.** Tolerate two occurrences. Consolidate on the
   third — unless the similarity is coincidental (same shape today, different reasons
   to change tomorrow).
6. **Untested area = legacy.** If the code you're about to change has no trustworthy
   test, characterize it with one first, or downgrade your change to a dry-run report.
   Don't rewrite blind.
7. **Evidence before edits.** A finding without grep output, an AST match, or tool
   output does not touch code.
8. **Prove every change.** Typecheck and tests pass after each batch, or the batch
   reverts.

## Stop conditions — a fork is DONE when

- the mandated smell is gone in the files it owns, **and**
- the next change would be speculative, cross into another fork's mandate, or alter
  behavior.

Everything past that line is a follow-up note, not an edit.

## Provenance & what was deliberately left out

These eight are distilled from the language-agnostic rule books in
[`ciembor/agent-rules-books`](https://github.com/ciembor/agent-rules-books) (Maciej
Ciemborowicz — the repo Matt Pocock forked), which in turn distill *Clean Code*
(Martin), *Refactoring* (Fowler), *A Philosophy of Software Design* (Ousterhout), and
*Working Effectively with Legacy Code* (Feathers).

Only the rules that encode an **agent failure mode** were kept. Deliberately excluded
as net-negative pressure for an automated cleanup pass:

- **DDD (Evans/Vernon ×3)** — aggregates, bounded contexts, anticorruption layers.
  Manufactures heavyweight modeling on ordinary code.
- **Clean Architecture's mandatory ports/adapters / inward-dependency rule** — one
  strong opinion that fights the "deep module" philosophy above and bloats small
  codebases. (Only "keep components acyclic" survives — it lives in the cycles fork.)
- **PoEAA pattern catalogue** — dated enterprise-Java patterns; the source repo's own
  compatibility matrix marks it conflicting with DDD.
- **Clean Code's literal "tiny functions" dogma** — taken at face value, an agent
  shreds readable functions into a confetti of one-call helpers, which rule 3 forbids.
