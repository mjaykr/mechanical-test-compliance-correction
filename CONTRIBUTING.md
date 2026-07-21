# Contributing

1. Open an issue describing the proposed change and its mechanical-testing use
   case.
2. Create a focused branch.
3. Add or update tests for numerical changes.
4. Run `pytest` and `ruff check .`.
5. Document new assumptions, units, and validity limits.

Corrections that silently alter stress values, discard raw measurements, or
claim an assumed modulus was measured will not be accepted.

