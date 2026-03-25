Address requested changes for this task.
Title: {{title}}
URL: {{url}}
{{repo_context}}
Read all comments and failed ci about this pull request. Apply fixes and update the branch.

Use git worktree to reuse(default to `{REPO_DIR}/.worktrees/pr-fix-{ISSUE_NUMBER}`) or create a dedicated worktree for this task.
Push updates to fork repository '{{repo_forked}}' (not upstream).
Ensure PR targets upstream '{{repo_full_name}}' branch '{{default_branch}}'.

You must ensure
1. all comments are well resolved by new commits.
2. all failed cis will be resolved by new commits.

If you modify the request, please label it `agent-reviewable` and remove `agent-changed` label.
