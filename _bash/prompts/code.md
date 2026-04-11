You are implementing a project card.

CARD KEY: {{CARD_KEY}}
CARD TITLE: {{CARD_TITLE}}

CARD DESCRIPTION:
{{CARD_DESCRIPTION}}

COMMENTS (may include reviewer feedback from a previous attempt):
{{CARD_COMMENTS}}

Your task:
1. Read the project documentation to understand the architecture and coding standards
2. Read the card description carefully — it contains acceptance criteria, technical context, and testing requirements
3. Follow the test-first approach:
   a. Write or update tests that cover the acceptance criteria
   b. Implement the feature/fix to make the tests pass
   c. Run the full test suite to ensure nothing is broken
4. Make sure the project builds successfully
5. Commit your changes with a clear message referencing the card key ({{CARD_KEY}})
6. Push the branch to origin

CRITICAL SAFETY RULES:
- NEVER push to or modify main, master, dev, or develop branches
- NEVER run destructive git commands (reset --hard, push --force, clean -f)
- ONLY commit and push to the feature branch: {{BRANCH_NAME}}
- If anything goes wrong, stop immediately

SENSITIVE DATA RULES:
- NEVER hardcode API keys, tokens, passwords, secrets, or credentials in source code
- NEVER read or log the contents of .env or any file containing secrets
- Use environment variables or config references — never embed actual values
- If tests need credentials, use clearly fake placeholders like `test-token-do-not-use`

CRITICAL CODE RULES:
- Follow the existing architecture and patterns in the codebase
- Use the project's logging conventions, not console methods
- No TODO comments or placeholder implementations
- Handle errors properly
- No comments unless the logic is non-obvious
- Check existing patterns in the codebase before creating new ones

After completing:
- Run the test suite and ensure all tests pass
- Run the build and ensure it succeeds
- Stage and commit all changes
- Push to origin with: git push -u origin {{BRANCH_NAME}}

Output a brief summary of what you implemented and any notes for the reviewer.
