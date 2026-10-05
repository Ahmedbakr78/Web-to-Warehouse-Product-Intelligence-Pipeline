name: Pull request
description: Propose a change to Web-to-Warehouse Product Intelligence Pipeline
labels: ["pr"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for contributing. Two things make review fast:
        a clear description of *why*, and green checks.

  - type: input
    id: title
    attributes:
      label: Title
      description: Use conventional prefixes — `feat:`, `fix:`, `docs:`, `refactor:`, `perf:`, `test:`, `chore:`.
      placeholder: "fix: clamp query lab LIMIT on aggregate queries"
    validations:
      required: true

  - type: dropdown
    id: type
    attributes:
      label: Type of change
      multiple: true
      options:
        - Bug fix
        - New feature
        - Documentation
        - Refactor (no behaviour change)
        - Performance
        - Test coverage
        - Build / CI / tooling
        - Database or schema change
    validations:
      required: true

  - type: textarea
    id: why
    attributes:
      label: Why
      description: The problem this solves. Link the issue if there is one.
    validations:
      required: true

  - type: textarea
    id: what
    attributes:
      label: What changed
      description: The approach you took and why you chose it over the alternatives.

  - type: textarea
    id: breaking
    attributes:
      label: Breaking changes
      description: API contract, configuration variables, database schema, or CLI behaviour that consumers must adapt to.
      placeholder: None

  - type: textarea
    id: verification
    attributes:
      label: How this was verified
      description: Paste the actual commands and their real output — not what you expect them to print.
      render: shell
    validations:
      required: true

  - type: textarea
    id: screenshots
    attributes:
      label: Screenshots (UI changes only)
      description: Light and dark, plus a narrow viewport if the layout is responsive.

  - type: checkboxes
    id: checks
    attributes:
      label: Checklist
      options:
        - label: "`make lint` passes"
        - label: "`make typecheck` passes"
        - label: "`make test` passes (255 tests)"
        - label: "Frontend: ESLint, `tsc` and `vite build` pass"
        - label: "Documentation updated if behaviour changed"
        - label: "`CHANGELOG.md` updated under *Unreleased*"
        - label: "No secrets, tokens or personal data in the diff"
        - label: "New behaviour is covered by a test"

  - type: markdown
    attributes:
      value: |
        ### Reminders for this repository

        - Ingestion changes must keep robots.txt enforcement in the transport layer, before the
          request is made.
        - SQL must stay parameterised; identifiers must stay whitelisted.
        - Database changes must keep PostgreSQL and MySQL structurally identical —
          run `make verify-dialects`.