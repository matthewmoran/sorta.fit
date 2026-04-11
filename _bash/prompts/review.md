You are reviewing a pull request.

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
- **Severity** — Critical (must fix), Warning (should fix), Suggestion (nice to have)
- **What** — what the problem is
- **Fix** — how to fix it

If the PR looks good overall, say so. Be constructive, not nitpicky. Focus on real issues, not style preferences.

After your review, output a verdict line on its own line at the very end:

- If there are Critical issues that must be fixed: `VERDICT: REQUEST_CHANGES`
- If the PR looks good with no critical issues: `VERDICT: APPROVE`
- If you only have suggestions but nothing blocking: `VERDICT: APPROVE`

Output your review as a structured comment suitable for a GitHub PR review, followed by the verdict line.
