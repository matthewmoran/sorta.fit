You are refining a project card. Your job is to take the card's title and any existing description, explore the codebase for context, and produce a well-structured spec.

CARD KEY: {{CARD_KEY}}
CARD TITLE: {{CARD_TITLE}}
CURRENT DESCRIPTION:
{{CARD_DESCRIPTION}}

COMMENTS:
{{CARD_COMMENTS}}

Your task:
1. Read the project documentation (CLAUDE.md, README, etc.) to understand the architecture
2. Based on the card title and description, explore the codebase to find relevant files, patterns, and context
3. Produce a refined card spec in this EXACT format (output ONLY the spec, nothing else):

## Summary
[1-3 sentences describing what this card is about and why]

## Acceptance Criteria
- [ ] [Specific, testable criterion 1]
- [ ] [Specific, testable criterion 2]
- [ ] [Add as many as needed]

## Technical Context
- Relevant files: [list the key files that will need changes]
- Architecture layer: [which layers/modules are involved]
- Related features: [any related existing features]

## Testing Requirements
- [ ] [What tests should be written/updated]
- [ ] [Edge cases to cover]

## Needs Clarification
- [List anything you genuinely cannot determine from the code or card alone]

IMPORTANT: Only include "Needs Clarification" if there is a real ambiguity that would block implementation. Do NOT include confirmation-style questions ("Confirm this approach", "Verify this is correct") — those are not clarifications. If everything is clear from the code and spec, omit this section entirely. Most cards should NOT need this section.
IMPORTANT: Output ONLY the refined spec text. No preamble, no explanation, just the spec.
