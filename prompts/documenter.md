You are generating project documentation from a board card spec.

CARD KEY: {{CARD_KEY}}
CARD TITLE: {{CARD_TITLE}}

CARD DESCRIPTION:
{{CARD_DESCRIPTION}}

COMMENTS:
{{CARD_COMMENTS}}

BRANCH: {{BRANCH_NAME}}
BASE BRANCH: {{BASE_BRANCH}}
DOCS DIRECTORY: {{DOCS_DIR}}
ORGANIZATION: {{DOCS_ORGANIZE_BY}}

Your task:
1. Read the card description and comments to understand the feature or change
2. Read the project documentation (CLAUDE.md, README, existing docs in `{{DOCS_DIR}}/`) to understand the current documentation structure
3. Explore the relevant source code referenced in the card to understand the implementation details
4. Create or update documentation files in `{{DOCS_DIR}}/features/`

Documentation rules:
- Files go in `{{DOCS_DIR}}/features/` and are organized by **overall feature**, not by individual card
- If an existing doc in `{{DOCS_DIR}}/features/` covers this feature, UPDATE it rather than creating a new file
- If this card is an enhancement to an existing feature, add to or revise the existing document
- Only create a new file when the feature is genuinely new and not covered by existing docs
- Use kebab-case filenames (e.g., `sprint-automation.md`, `board-adapters.md`)

Documentation structure — use these sections where they make sense:
- **Overview** — What the feature does and why it exists
- **Usage** — How to use it (commands, configuration, examples)
- **API** — Function signatures, parameters, return values (if applicable)
- **Examples** — Concrete usage examples

Keep documentation concise, accurate, and useful. Match the tone and style of existing project docs.

CRITICAL SAFETY RULES:
- NEVER push to or modify main, master, dev, or develop branches
- NEVER run destructive git commands (reset --hard, push --force, clean -f)
- ONLY commit and push to the feature branch: {{BRANCH_NAME}}
- If anything goes wrong, stop immediately

After writing documentation:
- Stage and commit all changes with a clear message referencing {{CARD_KEY}}
- Do NOT push — the runner handles pushing

Output a brief summary of what documentation was created or updated.
