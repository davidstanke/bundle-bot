---
trigger: always_on
---

# Do Not Reference `solution/` Outside the `solution/` Directory

When planning, researching, designing, or implementing code anywhere outside the `solution/` directory (such as in the repository root `app/` or `tests/` directories):

- **NEVER** read, view, search, grep, glob, diff, or otherwise inspect the `solution/` directory or any files inside `solution/`.
- **NEVER** use the `solution/` directory as a reference, template, or resource when generating plans (`/plan`, `/grill-me`), dispatching subagents (`/teamwork`, `/teamwork-preview`, `research`, `self`), or writing code and tests outside `solution/`.
- Only access or modify files inside `solution/` when the user is explicitly working inside `solution/` (e.g., when the working directory is `solution/` or the user explicitly asks to run, evaluate, deploy, or edit the `solution/` directory itself).

