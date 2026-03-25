Previous implement run completed, but no linked pull request was detected.
Title: {{title}}
URL: {{url}}
{{repo_context}}
{{delivery_context}}
Do not re-implement the fix from scratch.

Reuse the existing worktree(`{REPO_DIR}/.worktrees/pr-fix-{ISSUE_NUMBER}`) and branch if they already exist for this issue. Verify the branch contains the implementation commit, push it to fork repository '{{repo_forked}}', and create or update the pull request from fork '{{repo_forked}}' to upstream '{{repo_full_name}}' targeting '{{default_branch}}'.

The pull request description must include `Fixes #{{issue_number}}` so GitHub links it back to the issue.

If a matching pull request already exists, update it instead of opening another one. After the pull request exists, ensure it has the `agent-reviewable` label.
