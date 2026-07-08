# TextTraits Agent Instructions

After completing any requested build, code change, or website/app update, commit and push the finished work to GitHub by default. Do this automatically unless the user explicitly says not to push, asks for local-only work, or the work cannot be safely pushed because required verification failed or credentials/secrets would be exposed.

When pushing from a dirty worktree, stage only the files related to the completed request and leave unrelated local changes alone.
