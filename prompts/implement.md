Implement the GitHub issue.
Title: {{title}}
URL: {{url}}
{{repo_context}}
Please make the required code changes and push updates.

Use git worktree to create a dedicated worktree for this task, new branch should be follow `{REPO_DIR}/.worktrees/issue-{ISSUE_NUMBER}-{yyyymmdd}-{hhhh}`. Create and use a fresh branch inside that worktree so multiple tasks can run in parallel safely.

Push the branch to fork repository '{{repo_forked}}' (not upstream).
Create a PR from fork '{{repo_forked}}' to upstream '{{repo_full_name}}' targeting '{{default_branch}}'.
In the new PR description, include `Fixes #{{issue_number}}` so GitHub auto-closes the issue when the PR merges.

After you create a new pull request, please label it `agent-reviewable`
