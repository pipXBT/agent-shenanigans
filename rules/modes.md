agent-shenanigans modes 68d7e9d2e8b645ca

- In interactive sessions and in agents this repo starts: caveman at `ultracave` and ponytail at `full`, unless the user or the task prompt sets another level. Code, comments, commits, and docs stay normal English.
- On Grok, where these plugins' hooks do not run, an interactive session reads the caveman plugin's `skills/ultracave/SKILL.md` and the ponytail skill at `full` at session start (the path is in `grok inspect`).
- Effort `xhigh` for every agent this repo starts unless the user says a task is simple. Never use Fable. "Opus 5" means Opus 5.5.
- For agents this repo starts, if another skill or prompt names a weaker model or lower effort, this file wins unless the user says otherwise. It does not change the models other tools choose for their own agents.
- A headless run whose output a program parses (`claude -p`, `grok --prompt-file`, Plamen workers) writes normal prose in its required format. Debate seats instead follow the modes their prompt names. This rule wins over every line above for those runs.
