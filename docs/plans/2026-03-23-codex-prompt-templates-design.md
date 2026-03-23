# Codex Prompt Templates Design

**Goal:** Move Codex prompt text out of Python and into editable Markdown templates, while requiring `git worktree` usage for implementation and fix tasks.

## Decisions

- Store prompts in a top-level `prompts/` directory as:
- `prompts/implement.md`
- `prompts/fix.md`
- `prompts/review.md`
- Keep `review` focused on review/comments only. It must not mention creating a new branch, new PR, or `git worktree`.
- Keep `implement` and `fix` templates responsible for the workflow wording, including the requirement to create a dedicated worktree and branch per task.
- Change `CodexRunner._build_prompt()` into a small template renderer that:
- selects the template by mode
- builds a stable context dict
- replaces `{{variable_name}}` placeholders

## Template Format

- Use double-brace placeholders such as `{{title}}`, `{{url}}`, `{{repo_full_name}}`.
- Avoid `str.format()` so Markdown code blocks and braces do not require escaping.
- Unknown placeholders stay unchanged so template edits fail softly instead of corrupting the whole render.

## Context Variables

- `title`
- `url`
- `repo_full_name`
- `repo_forked`
- `default_branch`
- `repo_context`

## Error Handling

- Missing template files should raise immediately so configuration problems are visible during tests and local runs.
- No config layer is added yet; the default template location is part of the application layout to keep the feature minimal.

## Test Coverage

- Add unit coverage proving:
- `implement` prompt is loaded from Markdown and includes the worktree instruction.
- `fix` prompt is loaded from Markdown and includes the worktree instruction.
- `review` prompt is loaded from Markdown and does not include the worktree instruction.
- Existing runner test continues to verify prompt persistence in the `runs` table.
