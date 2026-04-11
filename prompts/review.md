You are reviewing a pull request. Review ONLY the diff provided below — do not check out branches, run tests, or explore the repository. If you need context about a file, use the Read tool to read it directly.

CARD KEY: {{CARD_KEY}}
PR URL: {{PR_URL}}

Here is the full diff:
{{PR_DIFF}}

Review this PR for:

1. **Code Quality** — Clean code, consistent naming, no dead code, proper error handling
2. **Architecture** — Follows the project's established patterns and conventions
3. **Testing** — Tests cover the acceptance criteria, edge cases handled
4. **Security** — No hardcoded secrets/tokens/credentials (even in tests or docs), no injection vulnerabilities, proper input validation, no .env values or internal URLs in committed files
5. **Performance** — No N+1 queries, no unnecessary re-renders, efficient algorithms

For each issue found, specify:
- **File and line** — where the issue is
- **Severity** — Critical (must fix), Warning (must fix), Suggestion (nice to have)
- **What** — what the problem is
- **Fix** — how to fix it

If the PR looks good overall, say so. Be constructive, not nitpicky. Focus on real issues, not style preferences.

**Important:** Do not run git commands, check out branches, or run tests. Your only job is to review the diff above and provide feedback.

After your review, output a verdict line on its own line at the very end:

- If there are ANY Critical or Warning issues: `VERDICT: REQUEST_CHANGES`
- If the PR has only Suggestions or no issues at all: `VERDICT: APPROVE`

Warnings are blocking. Only Suggestions are non-blocking.

Output your review as a structured comment suitable for a GitHub PR review, followed by the verdict line.
