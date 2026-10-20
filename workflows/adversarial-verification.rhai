let meta = #{
    name: "adversarial-verification",
    description: "Run a writing-plans file one task at a time with skeptic, teeth, gate, and receipts (workflows/CONTRACT.md).",
    when_to_use: "Started by the execute skill with the args in workflows/CONTRACT.md section 1, at effort xhigh. Every run is fresh; a restart reads the run state.",
    phases: [
        #{ title: "Preflight", detail: "args, branch, clean tree" },
        #{ title: "Plan", detail: "dependency graph, complexity, run state" },
        #{ title: "Review", detail: "three reviewers, one verifier per finding, one fix" },
    ],
};

// Grok executor for workflows/CONTRACT.md. Agents return raw output; every check runs
// here in plain Rhai against the fields they return, and a missing field fails closed.
// Rhai functions see no script variables, so the run lives in one map, `st`, and the
// steps are methods on it (`this`). A failed check throws #{kind: "fail"}: it fails the
// attempt inside a task and stops the run anywhere else. #{kind: "stop"} always stops.

const GROK_MODEL = "grok-4.7";

// rules/modes.md without its marker line; tests/workflows/test_rhai_static.py keeps them equal.
const MODES = "- In interactive sessions and in agents this repo starts: caveman at `ultracave` and ponytail at `full`, unless the user or the task prompt sets another level. Code, comments, commits, and docs stay normal English.\n- On Grok, where these plugins' hooks do not run, an interactive session reads the caveman plugin's `skills/ultracave/SKILL.md` and the ponytail skill at `full` at session start (the path is in `grok inspect`).\n- Effort `xhigh` for every agent this repo starts unless the user says a task is simple. Never use Fable. \"Opus 5\" means Opus 5.5.\n- For agents this repo starts, if another skill or prompt names a weaker model or lower effort, this file wins unless the user says otherwise. It does not change the models other tools choose for their own agents.\n- A headless run whose output a program parses (`claude -p`, `grok --prompt-file`, Plamen workers) writes normal prose in its required format. Debate seats instead follow the modes their prompt names. This rule wins over every line above for those runs.";

// The git port, CONTRACT.md section 4.
const GIT_RULES = `You are the git step of a scripted workflow. Run only the commands of the one action named on the line below that starts with "git action:", in order, and stop at the first failure. Do not judge or fix anything. Then, whatever happened, fill every report field. String fields hold the command's stdout with trailing newlines removed.

".git" means the directory "git rev-parse --absolute-git-dir" prints. <base> is the action's base parameter; an action without one has no base.

Report fields:
- head: git rev-parse HEAD
- tree: git rev-parse HEAD^{tree}
- branch: git branch --show-current
- default_branch: git symbolic-ref --quiet --short refs/remotes/origin/HEAD with the leading "origin/" removed; "" when that command fails
- porcelain: git status --porcelain --untracked-files=all
- untracked: git ls-files --others --exclude-standard, one entry per line
- last_message: git log -1 --format=%B
- name_status: git diff --no-renames --name-status <base> HEAD; "" without a base
- diff_file: mkdir -p .git/agent-shenanigans/diff, write the output of git diff --no-renames <base>..HEAD to .git/agent-shenanigans/diff/<base>..<head>.patch (<head> is the head field), and report that file's absolute path; "" without a base. Never copy the diff text into the report.
- base_is_ancestor: true when git merge-base --is-ancestor <base> HEAD exits 0; false without a base
- state_json: set only by read_state and write_state; "" otherwise
- ok: true when every action command exited 0 and every field command succeeded. merge-base --is-ancestor exiting 1 is a success (false); a failing symbolic-ref gives default_branch "".
- error: "", or the failing command and the first 2000 characters of its stderr

Actions:
- snapshot(base): no commands. base may be "".
- checkout_branch(name): git switch <name> when git rev-parse --verify --quiet refs/heads/<name> succeeds, else git switch -c <name>
- read_state(plan_hash): cat .git/agent-shenanigans/<plan_hash>.json into state_json. A missing file gives state_json "" with ok true.
- write_state(plan_hash, json): mkdir -p .git/agent-shenanigans; write json byte for byte to .git/agent-shenanigans/<plan_hash>.json.tmp; mv it to .git/agent-shenanigans/<plan_hash>.json; cat the result into state_json
- teeth_revert(base, paths): .git/agent-shenanigans/aside/teeth/ must be absent or empty. Run git diff --no-renames --name-status <base> HEAD. For each path in paths: status M, T, or D: git checkout <base> -- <path>; status A: move the path to .git/agent-shenanigans/aside/teeth/<path>, creating parent folders. Any other status, or a path the diff does not list, fails the action.
- teeth_restore(): git restore --source=HEAD --staged --worktree -- :/ then rm -rf .git/agent-shenanigans/aside/teeth
- reset_keep(sha): git reset --keep <sha>
- move_untracked_aside(since): move every path git ls-files --others --exclude-standard lists to .git/agent-shenanigans/aside/<since>.<n>/<path>, where n is the first integer from 1 whose folder does not exist (one n per call)
- amend_trailer(trailer): before=$(git rev-parse HEAD^); git commit --amend --no-edit --trailer "<trailer>"; test "$(git rev-parse HEAD^)" = "$before". For this action only, base_is_ancestor is that last command's result.`;

fn obj(props) { #{ "type": "object", "properties": props, "required": props.keys() } }
fn list(items) { #{ "type": "array", "items": items } }

fn schema_for(label) {
    let s = #{ "type": "string" };
    let b = #{ "type": "boolean" };
    if label == "plan" {
        let task = obj(#{ id: s, depends_on: list(s), complexity: #{ "type": "string", "enum": ["low", "medium", "high"] }, brief: s });
        obj(#{ phases: list(obj(#{ name: s, subprojects: list(obj(#{ name: s, tasks: list(task) })) })) })
    } else if label == "git" {
        obj(#{ ok: b, error: s, head: s, tree: s, branch: s, default_branch: s, porcelain: s,
            untracked: list(s), name_status: s, diff_file: s, last_message: s, base_is_ancestor: b, state_json: s })
    } else if label == "test" {
        obj(#{ test_exit: #{ "type": "integer" }, lint_exit: #{ "type": ["integer", "null"] }, tail: s })
    } else if label == "implement" {
        obj(#{ summary: s, issues: list(s) })
    } else if label == "review" {
        obj(#{ findings: list(obj(#{ file: s, issue: s, severity: s })) })
    } else if label == "verify-finding" {
        obj(#{ real: b, evidence: s })
    } else if label == "fix-review" {
        obj(#{ summary: s })
    } else {
        obj(#{ verdict: #{ "type": "string", "enum": ["pass", "fail"] }, evidence: s })
    }
}

fn capability(label) {
    if label == "git" || label == "test" { "execute" } else if label == "implement" || label == "fix-review" { "all" } else { "read-only" }
}

fn output_of(r) {
    if type_of(r) == "map" && r.success == true { return r.output; }
    let why = if type_of(r) == "map" && type_of(r.output) == "string" && r.output != "" { r.output } else { "agent returned no report" };
    throw #{ kind: "stop", why: why };
}

// The one place the host spawns agents. `prompt` is one prompt, or an array of prompts run as
// one parallel batch (outputs in order, () for a failed slot). `role` keys the schema, the
// capability, and the fixture outputs; `shown` is only the label /workflows shows: a string, an
// array with one per prompt, or () for "<prefix> · <role>" inside a task, else the role.
// Fixture mode returns the role's next scripted output for each prompt instead.
fn call_agent(role, prompt, shown) {
    let label = if this.prefix == () { role } else { this.prefix + " · " + role };
    if type_of(shown) == "string" { label = shown; }
    let opts = #{
        label: label,
        capability_mode: capability(role),
        output_schema: schema_for(role),
    };
    if global::GROK_MODEL.to_lower().contains("fable") {
        throw #{ kind: "stop", why: "refused model " + global::GROK_MODEL };
    }
    let modes = global::MODES;
    modes.replace("`full`", "`" + this.args.ponytail + "`");
    let head = modes + "\n\nRun nonce: " + this.args.run_nonce + "\n\n";
    let batch = type_of(prompt) == "array";
    let prompts = if batch { prompt } else { [prompt] };
    let outs = [];
    let fx = this.args.fixture;
    if fx == () && batch {
        let jobs = [];
        for i in 0..prompts.len() {
            let job = opts;
            job.prompt = head + prompts[i];
            if type_of(shown) == "array" { job.label = shown[i]; }
            jobs.push(job);
        }
        for r in parallel(jobs) { outs.push(output_of(r)); }
    } else if fx == () {
        outs.push(output_of(agent(head + prompt, opts)));
    } else {
        let given = if type_of(fx) == "map" && type_of(fx.outputs) == "map" { fx.outputs[role] } else { () };
        for p in prompts {
            let n = this.used[role] ?? 0;
            this.used[role] = n + 1;
            outs.push(if type_of(given) == "array" && n < given.len() { given[n] } else { () });
        }
    }
    if batch { outs } else { outs[0] }
}

fn git(action, params) {
    let p = "Repo: " + this.args.repo + " (cd there first)\n\n" + global::GIT_RULES;
    p += "\n\ngit action: " + action + " " + json_encode(params);
    this.call_agent("git", p, ())
}

fn fail(why) { #{ kind: "fail", why: why } }
fn check(ok, why) { if ok != true { throw fail(why); } }
fn is_fail(e) { type_of(e) == "map" && e.kind == "fail" }
// Inside a stopping block a failed check stops the run (CONTRACT.md section 5, Failures).
fn as_stop(e) { if is_fail(e) { #{ kind: "stop", why: e.why } } else { e } }

// One field of a git report. A missing report, ok: false, a missing field, or a wrong type fails the check.
fn field_of(r, name, f, t) {
    let usable = type_of(r) == "map" && r.ok == true;
    let v = if usable { r[f] } else { () };
    if type_of(v) != t {
        let why = if usable { "missing or wrong type" } else { "report missing or not ok" };
        throw fail(name + "." + f + ": " + why);
    }
    v
}

fn text_of(v) { if type_of(v) == "string" { v } else { "" } }
fn is_str(v) { type_of(v) == "string" && v != "" }
fn named(v) { if is_str(v) { v } else { "Tasks" } }
fn lint_given(a) { is_str(a.lint_cmd) }

fn strs(v) {
    if type_of(v) != "array" { return false; }
    let ok = true;
    for x in v { if type_of(x) != "string" { ok = false; } }
    ok
}

fn names(xs) {
    let s = "";
    let n = 0;
    for x in xs {
        if n > 0 { s += ", "; }
        s += x;
        n += 1;
    }
    if n == 0 { "none" } else { s }
}

fn count_of(s, c) { s.split(c).len() - 1 }

// A state file the Claude executor wrote is indented, and its copy can come back with each
// newline as the two characters `\n`. The state holds no backslash, so turning them back is safe.
// A parse_json error ends the run even inside try, so a copy cut short returns () before it.
// shortcut: screens only shape and bracket counts; other broken JSON still ends the run.
fn parse_copy(text) {
    let t = text;
    t.replace("\\n", "\n");
    if !t.starts_with("{") || !t.ends_with("}") || t.contains("\\") || count_of(t, "{") != count_of(t, "}") ||
        count_of(t, "[") != count_of(t, "]") || count_of(t, "\"") % 2 != 0 { return (); }
    parse_json(t)
}

fn same_json(text, value) {
    let back = parse_copy(text);
    type_of(back) == "map" && json_encode(back) == json_encode(value)
}

fn tracked_clean(r, name) {
    let ok = true;
    for l in field_of(r, name, "porcelain", "string").split("\n") {
        if l != "" && !l.starts_with("??") { ok = false; }
    }
    ok
}

// The paths of a --no-renames --name-status listing.
fn changed_paths(ns) {
    let out = [];
    for l in ns.split("\n") {
        if l != "" {
            let parts = l.split("\t");
            out.push(parts[parts.len() - 1]);
        }
    }
    out
}

// Equal to a listed path, or under a listed entry that ends in "/".
fn listed(p, xs) {
    let hit = false;
    for e in xs { if e == p || (e.ends_with("/") && p.starts_with(e)) { hit = true; } }
    hit
}

fn is_docs(p) {
    p.ends_with(".md") || p.ends_with(".rst") || p.ends_with(".txt") || p.ends_with(".adoc") || p.starts_with("docs/")
}

fn matches(p, globs) {
    let hit = false;
    for g in globs { if glob_at(g.split("/"), 0, p.split("/"), 0) { hit = true; } }
    hit
}

// Whole-path glob: a "**" segment spans zero or more whole segments; * and ? stay in one.
fn glob_at(gs, i, ps, j) {
    if i == gs.len() { return j == ps.len(); }
    if gs[i] == "**" {
        for k in j..=ps.len() { if glob_at(gs, i + 1, ps, k) { return true; } }
        return false;
    }
    j < ps.len() && seg_match(gs[i], ps[j]) && glob_at(gs, i + 1, ps, j + 1)
}

fn seg_match(g, s) {
    let gi = 0;
    let si = 0;
    let star = -1;
    let mark = 0;
    while si < s.len() {
        if gi < g.len() && g[gi] != '*' && (g[gi] == '?' || g[gi] == s[si]) {
            gi += 1;
            si += 1;
        } else if gi < g.len() && g[gi] == '*' {
            star = gi;
            mark = si;
            gi += 1;
        } else if star >= 0 {
            gi = star + 1;
            mark += 1;
            si = mark;
        } else {
            return false;
        }
    }
    while gi < g.len() && g[gi] == '*' { gi += 1; }
    gi == g.len()
}

fn is_hash(v) {
    if type_of(v) != "string" || v.len() != 64 { return false; }
    let ok = true;
    for c in v { if !"0123456789abcdef".contains(c) { ok = false; } }
    ok
}

fn tasks_ok(ts) {
    if type_of(ts) != "array" { return false; }
    let ids = [];
    for t in ts {
        if type_of(t) != "map" || !is_str(t.id) || ids.contains(t.id) || type_of(t.title) != "string"
            || !strs(t.files) || !strs(t.tests) || !["code", "refactor", "docs", "test"].contains(t.kind)
            || !["marker", "derived"].contains(t.kind_source)
            || (t.complexity != () && !["low", "medium", "high"].contains(t.complexity)) {
            return false;
        }
        ids.push(t.id);
    }
    true
}

fn check_args() {
    let a = this.args;
    check(type_of(a) == "map", "args: missing");
    let bad = [];
    for k in ["repo", "test_cmd", "plan_path", "run_nonce"] { if !is_str(a[k]) { bad.push(k); } }
    for k in ["lint_cmd", "branch"] { if a[k] != () && type_of(a[k]) != "string" { bad.push(k); } }
    if !is_hash(a.plan_hash) { bad.push("plan_hash"); }
    if type_of(a.rules) != "map" || !strs(a.rules.high_risk) || !strs(a.rules.test_globs) { bad.push("rules"); }
    if !strs(a.forbid) { bad.push("forbid"); }
    if a.review != () && type_of(a.review) != "bool" { bad.push("review"); }
    if !["full", "ultra"].contains(a.ponytail) { bad.push("ponytail"); }
    if !tasks_ok(a.tasks) { bad.push("tasks"); }
    check(bad.len() == 0, "args: missing or wrong type: " + names(bad));
    check(a.level == () || ["lite", "full"].contains(a.level), "args.level: " + json_encode(a.level) + " is not \"lite\" or \"full\"");
    this.level = a.level ?? "lite";
}

// The teeth value of a task that did not run teeth (CONTRACT.md section 5, Levels).
fn skipped(kind) { if this.level == "lite" { "skipped:lite" } else { "skipped:" + kind } }

// P1/P2: resolve the branch, refuse the default branch, require a clean tree.
fn preflight() {
    let P1 = this.git("snapshot", #{ base: "" });
    let cur = field_of(P1, "P1", "branch", "string");
    let dflt = field_of(P1, "P1", "default_branch", "string");
    let B = this.args.branch ?? cur;
    check(dflt != "", "P1.default_branch: empty, the default branch cannot be determined");
    check(B != "", "P1.branch: empty, HEAD is detached");
    check(B != dflt, "P1.default_branch: " + B + " is the default branch");
    check(field_of(P1, "P1", "porcelain", "string") == "", "P1.porcelain: the tree is not clean");
    if this.args.branch != () && this.args.branch != cur {
        let P2 = this.git("checkout_branch", #{ name: B });
        check(field_of(P2, "P2", "branch", "string") == B, "P2.branch: not on " + B + " after checkout");
        check(field_of(P2, "P2", "porcelain", "string") == "", "P2.porcelain: the tree is not clean after checkout");
    }
    B
}

fn plan_prompt() {
    let a = this.args;
    let p = "You plan the run of an implementation plan. Do not change anything.\nRepo: " + a.repo;
    p += "\nPlan file: " + a.plan_path + "\n\nTasks:\n";
    for t in a.tasks {
        p += "- id " + t.id + ": " + t.title + " (kind " + t.kind + "; files: " + names(t.files);
        p += "; tests: " + names(t.tests) + ")\n";
    }
    p += "\nRead each task's section in the plan file with read_file and grep; do not answer from memory. ";
    p += "Group the tasks into phases and subprojects. Return every task above exactly once, with:\n";
    p += "- id: exactly as listed\n";
    p += "- depends_on: the ids of the tasks that must land before it, never its own\n";
    p += "- complexity: low, medium, or high. low: one file, and the plan quotes the change. ";
    p += "medium: a few files, the plan is clear, and judgment stays local. ";
    p += "high: a design choice, security, money, or a gap in the plan.\n";
    p += "- brief: the task's full text from the plan file, verbatim";
    p
}

// The plan stage: graph checks and complexity in code, then Kahn order by waves.
fn plan_order() {
    let plan = this.call_agent("plan", this.plan_prompt(), ());
    check(type_of(plan) == "map" && type_of(plan.phases) == "array", "plan.phases: missing");
    let entries = [];
    for ph in plan.phases {
        check(type_of(ph) == "map" && type_of(ph.subprojects) == "array", "plan: a phase has no subprojects list");
        for sp in ph.subprojects {
            check(type_of(sp) == "map" && type_of(sp.tasks) == "array", "plan: a subproject has no tasks list");
            for e in sp.tasks {
                let x = e;
                if type_of(x) == "map" {
                    x.phase = named(ph.name);
                    x.subproject = named(sp.name);
                }
                entries.push(x);
            }
        }
    }
    let ids = [];
    for t in this.args.tasks { ids.push(t.id); }
    let by_id = #{};
    for e in entries {
        let id = if type_of(e) == "map" { e.id } else { () };
        check(type_of(id) == "string" && ids.contains(id), "plan: task ids differ from the plan file");
        check(!by_id.contains(id), "plan: a task id appears more than once");
        by_id[id] = e;
    }
    check(by_id.len() == ids.len(), "plan: task ids differ from the plan file");
    let tasks = [];
    for t in this.args.tasks {
        let e = by_id[t.id];
        let deps_ok = type_of(e.depends_on) == "array";
        if deps_ok { for d in e.depends_on { if d == t.id || !ids.contains(d) { deps_ok = false; } } }
        check(deps_ok, "plan: task " + t.id + " depends_on names an unknown id or itself");
        check(type_of(e.brief) == "string", "plan: task " + t.id + " has no brief");
        let c = t.complexity ?? e.complexity;
        check(["low", "medium", "high"].contains(c), "plan: task " + t.id + " complexity is not low, medium, or high");
        let floor = t.files.len() > 3;
        for p in t.files { if matches(p, this.args.rules.high_risk) { floor = true; } }
        let x = t;
        x.depends_on = e.depends_on;
        x.brief = e.brief;
        x.complexity = if floor && c == "low" { "medium" } else { c };
        x.phase = e.phase;
        x.subproject = e.subproject;
        tasks.push(x);
    }
    let placed = [];
    let order = [];
    while order.len() < tasks.len() {
        let wave = [];
        let left = [];
        for t in tasks {
            if !placed.contains(t.id) {
                left.push(t.id);
                let ready = true;
                for d in t.depends_on { if !placed.contains(d) { ready = false; } }
                if ready { wave.push(t); }
            }
        }
        check(wave.len() > 0, "plan: dependency cycle among " + names(left));
        let wave_ids = [];
        for t in wave {
            wave_ids.push(t.id);
            placed.push(t.id);
            order.push(t);
        }
        log("parallel-eligible: " + names(wave_ids));
    }
    order
}

fn write_state() {
    // The git agent copies the file back by hand; a copy that does not parse back gets one fresh agent.
    for attempt in 0..2 {
        let W = this.git("write_state", #{ plan_hash: this.args.plan_hash, json: json_encode(this.state) });
        if same_json(field_of(W, "W", "state_json", "string"), this.state) { return; }
    }
    check(false, "W.state_json: differs from the state written");
}

fn state_ok(s, hash) {
    if type_of(s) != "map" || s.plan_hash != hash || type_of(s.run_start) != "string" || type_of(s.tasks) != "map" {
        return false;
    }
    let ok = true;
    for id in s.tasks.keys() {
        let t = s.tasks[id];
        if type_of(t) != "map" || type_of(t.pre) != "string" || (t.receipt != () && type_of(t.receipt) != "string") {
            ok = false;
        }
    }
    ok
}

// The newest receipt: the one no other done task starts from. Following pre links from it
// must visit every done task and end at run_start, so a corrupt state never resets below it.
fn restart_target(state, done) {
    if done.len() == 0 { return state.run_start; }
    let tips = [];
    for id in done {
        let starts = false;
        for o in done { if o != id && state.tasks[o].pre == state.tasks[id].receipt { starts = true; } }
        if !starts { tips.push(id); }
    }
    check(tips.len() == 1, "ST.state_json: the receipts do not form one chain");
    let by_receipt = #{};
    for id in done { by_receipt[state.tasks[id].receipt] = id; }
    let sha = state.tasks[tips[0]].receipt;
    let steps = 0;
    while by_receipt.contains(sha) && steps <= done.len() {
        sha = state.tasks[by_receipt[sha]].pre;
        steps += 1;
    }
    check(steps == done.len() && sha == state.run_start, "ST.state_json: the receipts do not chain back to run_start");
    state.tasks[tips[0]].receipt
}

// Fresh run or restart. Returns the ids done in an earlier run.
fn run_state() {
    // Same hand-copy risk as write_state: a read that does not parse gets one fresh agent.
    let ST = ();
    let text = "";
    let state = ();
    for attempt in 0..2 {
        ST = this.git("read_state", #{ plan_hash: this.args.plan_hash });
        text = field_of(ST, "ST", "state_json", "string");
        if text == "" { break; }
        state = parse_copy(text);
        if type_of(state) == "map" { break; }
    }
    let done = [];
    if text == "" {
        this.state = #{ plan_hash: this.args.plan_hash, run_start: field_of(ST, "ST", "head", "string"), tasks: #{} };
        this.write_state();
        return done;
    }
    check(state_ok(state, this.args.plan_hash), "ST.state_json: not a run state for this plan");
    let R0 = this.git("snapshot", #{ base: state.run_start });
    check(field_of(R0, "R0", "base_is_ancestor", "bool"), "R0.base_is_ancestor: HEAD does not descend from run_start");
    check(field_of(R0, "R0", "porcelain", "string") == "", "R0.porcelain: the tree is dirty (an interrupted teeth step?)");
    let head = field_of(R0, "R0", "head", "string");
    for id in state.tasks.keys() {
        let receipt = state.tasks[id].receipt;
        if receipt != () {
            let Rr = this.git("snapshot", #{ base: receipt });
            if field_of(Rr, "R(" + id + ")", "base_is_ancestor", "bool") { done.push(id); }
        }
    }
    let X = restart_target(state, done);
    if head != X {
        let RK = this.git("reset_keep", #{ sha: X });
        check(field_of(RK, "RK", "head", "string") == X, "RK.head: the reset did not land on " + X);
        check(field_of(RK, "RK", "porcelain", "string") == "", "RK.porcelain: the tree is not clean after the reset");
    }
    for id in state.tasks.keys() { if !done.contains(id) { state.tasks[id].receipt = (); } }
    this.state = state;
    this.write_state();
    done
}

fn implement_prompt(t, pre, failure) {
    let a = this.args;
    let p = "Implement one task from a plan. Work in " + a.repo + ", on the current branch.\n";
    p += "Task " + t.id + ": " + t.title + " (kind " + t.kind + ")\n";
    p += "Files: " + names(t.files) + "\nTests: " + names(t.tests) + "\n";
    p += "Never touch paths matching: " + names(a.forbid) + "\nTest command: " + a.test_cmd + "\n";
    if lint_given(a) { p += "Lint command: " + a.lint_cmd + "\n"; }
    p += "\nBrief:\n" + t.brief;
    if failure != "" {
        p += "\n\nAn earlier attempt at this task failed: " + failure;
        p += "\nThe branch is back at the pre-task commit " + pre + ". Start again from there.";
    }
    p += "\n\nRead the files the brief names before editing. Do this task only; do not start the next one. ";
    p += "TDD when the task names a test. Run the test command, and the lint command when one is set.\n";
    p += "Conventional commit; say why in the body. Stage only files this task changed. Never push. No co-author trailer.\n";
    p += "Commit your work and leave the tree clean.";
    p
}

fn test_prompt() {
    let a = this.args;
    let p = "Repo: " + a.repo + " (cd there first)\n\n";
    p += "You are the test step of a scripted workflow. Do not judge or fix anything.\n1. Run: " + a.test_cmd + "\n2. ";
    if lint_given(a) { p += "Run: " + a.lint_cmd; } else { p += "There is no lint command; skip this step."; }
    p += "\nReport test_exit (the exit code of step 1), lint_exit (the exit code of step 2, or null when it was skipped), ";
    p += "and tail (the last 200 lines of their combined output).";
    p
}

// Readers get the diff as a file: a git agent copying a long diff into its report came back
// short or refused (77 000 characters, 2026-10-20).
fn diff_line(file) {
    "Read the whole diff from " + file + " with read_file (in parts when it is long)."
}

fn skeptic_prompt(t, name_status, diff_file, changed) {
    let a = this.args;
    let q = "Does the diff do what the brief says, and nothing outside it?";
    if t.kind == "refactor" {
        q = "Is behaviour unchanged?";
        let edits = [];
        for p in changed { if listed(p, t.tests) || matches(p, a.rules.test_globs) { edits.push(p); } }
        if edits.len() > 0 {
            q += " It changes test files (" + names(edits) + "): confirm no assertion was removed or weakened.";
        }
    } else if t.kind == "docs" {
        q = "Does the diff change documentation only?";
    } else if t.kind == "test" {
        q = "Do the new tests assert real behaviour?";
    }
    let p = "You are the skeptic for one task of a plan. Read the repo at " + a.repo + " as needed; change nothing.\n";
    p += "Task " + t.id + ": " + t.title + " (kind " + t.kind + ")\n";
    p += "Files: " + names(t.files) + "\nTests: " + names(t.tests) + "\nForbidden paths: " + names(a.forbid) + "\n\n";
    p += "Brief:\n" + t.brief + "\n\nChanged paths (git diff --name-status):\n" + name_status + "\n\nDiff: " + diff_line(diff_file);
    p += "\n\nQuestion: " + q + "\n";
    p += "Fail closed: return verdict \"pass\" only when the answer is clearly yes, else \"fail\". ";
    p += "evidence quotes the lines you checked.";
    p
}

fn set_result(k, v) {
    let i = this.results.len() - 1;
    this.results[i][k] = v;
}

// Steps 2-6 of one attempt (CONTRACT.md section 5). A fail fails the attempt; a stop ends the run.
// Task review-fix (kind ()) runs fix-review in step 2 and takes its kind from what it changed.
fn attempt(t, B, pre, failure) {
    let a = this.args;
    if t.kind == () {
        this.call_agent("fix-review", this.fix_prompt(t, pre), this.prefix + " · implement");
    } else {
        this.call_agent("implement", this.implement_prompt(t, pre, failure), ());
    }
    let S2 = this.git("snapshot", #{ base: pre });
    let H = field_of(S2, "S2", "head", "string");
    check(H != pre, "S2.head: equals the pre-task commit, nothing was committed");
    check(field_of(S2, "S2", "base_is_ancestor", "bool"), "S2.base_is_ancestor: the pre-task commit is not an ancestor of HEAD");
    check(field_of(S2, "S2", "porcelain", "string") == "", "S2.porcelain: the tree is not clean after implement");
    let T = field_of(S2, "S2", "tree", "string");
    let name_status = field_of(S2, "S2", "name_status", "string");
    let changed = changed_paths(name_status);
    if t.kind == () {
        let prod = false;
        let docs = true;
        for p in changed {
            if listed(p, t.files) && !is_docs(p) { prod = true; }
            if !listed(p, t.files) || !is_docs(p) { docs = false; }
        }
        t.kind = if prod { "code" } else if docs { "docs" } else { "test" };
        this.set_result("teeth", "skipped:" + t.kind);
    }

    // Steps 3 and 4 run at level full only.
    if this.level == "full" {
        check(S2.ok == true, "S2.ok: " + text_of(S2.error));
        let sk = this.call_agent("skeptic", this.skeptic_prompt(t, name_status, field_of(S2, "S2", "diff_file", "string"), changed), ());
        let sk = if type_of(sk) == "map" { sk } else { #{} };
        check(sk.verdict == "pass", "skeptic.verdict: " + json_encode(sk.verdict) + ": " + text_of(sk.evidence));

        if t.kind == "code" {
            let P = [];
            for p in changed { if listed(p, t.files) && !listed(p, t.tests) { P.push(p); } }
            check(P.len() > 0, "S2.name_status: no production path in files changed");
            this.set_result("teeth", "ran");
            let TR = this.git("teeth_revert", #{ base: pre, paths: P });
            let TT = this.call_agent("test", this.test_prompt(), this.prefix + " · teeth");
            let RS = this.git("teeth_restore", #{});
            try {
                check(field_of(RS, "RS", "head", "string") == H, "RS.head: HEAD moved during teeth");
                check(field_of(RS, "RS", "tree", "string") == T, "RS.tree: the tree changed during teeth");
                check(tracked_clean(RS, "RS"), "RS.porcelain: tracked changes remain after the teeth restore");
            } catch (e) {
                throw as_stop(e);
            }
            check(field_of(TR, "TR", "head", "string") == H, "TR.head: the teeth revert did not run on HEAD");
            let te = if type_of(TT) == "map" { TT.test_exit } else { () };
            check(type_of(te) == "i64" && te != 0, "TT.test_exit: " + json_encode(te) + ", the tests do not fail without the change");
        }
    }

    // Step 5: the docs scope check runs at both levels, before the tests.
    if t.kind == "docs" {
        let bad = "";
        for p in changed {
            if bad == "" && (!is_docs(p) || listed(p, t.tests) || matches(p, a.rules.test_globs)) { bad = p; }
        }
        check(bad == "", "S2.name_status: " + bad + " is not a documentation path");
    }
    let G1 = this.call_agent("test", this.test_prompt(), this.prefix + " · gate");
    let G1 = if type_of(G1) == "map" { G1 } else { #{} };
    check(G1.test_exit == 0, "G1.test_exit: " + json_encode(G1.test_exit) + ", the tests fail");
    if lint_given(a) { check(G1.lint_exit == 0, "G1.lint_exit: " + json_encode(G1.lint_exit) + ", lint fails"); }
    let G2 = this.git("snapshot", #{ base: pre });
    check(field_of(G2, "G2", "head", "string") == H, "G2.head: HEAD moved after implement");
    let branch = field_of(G2, "G2", "branch", "string");
    check(branch == B, "G2.branch: " + branch + " is not " + B);
    check(branch != field_of(G2, "G2", "default_branch", "string"), "G2.default_branch: on the default branch");
    check(tracked_clean(G2, "G2"), "G2.porcelain: tracked changes are not committed");
    for p in changed_paths(field_of(G2, "G2", "name_status", "string")) {
        check(listed(p, t.files) || listed(p, t.tests), "G2.name_status: " + p + " is outside files and tests");
        check(!matches(p, a.forbid), "G2.name_status: " + p + " matches forbid");
    }

    let S6 = this.git("snapshot", #{ base: "" });
    check(field_of(S6, "S6", "head", "string") == H, "S6.head: HEAD moved after the gate");
    check(tracked_clean(S6, "S6"), "S6.porcelain: tracked changes appeared after the gate");
    let trailer = "Task-Id: " + a.plan_hash.sub_string(0, 12) + "/" + t.id;
    try {
        let A = this.git("amend_trailer", #{ trailer: trailer });
        let err = if type_of(A) == "map" { text_of(A.error) } else { "missing" };
        check(type_of(A) == "map" && A.ok == true, "A.ok: " + err);
        let receipt = field_of(A, "A", "head", "string");
        check(receipt != H, "A.head: the amend made no new commit");
        check(field_of(A, "A", "tree", "string") == field_of(G2, "G2", "tree", "string"), "A.tree: the amend changed the tree");
        check(field_of(A, "A", "base_is_ancestor", "bool"), "A.base_is_ancestor: the amend changed the parent");
        check(field_of(A, "A", "last_message", "string").split("\n").contains(trailer), "A.last_message: no line " + trailer);
        this.state.tasks[t.id].receipt = receipt;
        this.write_state();
        if field_of(A, "A", "untracked", "array").len() > 0 {
            let MU = this.git("move_untracked_aside", #{ since: pre });
            check(field_of(MU, "MU", "untracked", "array").len() == 0, "MU.untracked: files remain after moving them aside");
            check(field_of(MU, "MU", "porcelain", "string") == "", "MU.porcelain: the tree is not clean");
        }
    } catch (e) {
        throw as_stop(e);
    }
}

// F1-F3: back to the pre-task commit with a clean tree. Any failed check here stops the run.
fn restore(pre) {
    let F1 = this.git("teeth_restore", #{});
    check(tracked_clean(F1, "F1"), "F1.porcelain: tracked changes remain after the restore");
    let F2 = this.git("reset_keep", #{ sha: pre });
    check(field_of(F2, "F2", "head", "string") == pre, "F2.head: the reset did not land on " + pre);
    let last = F2;
    let last_name = "F2";
    if field_of(F2, "F2", "untracked", "array").len() > 0 {
        let F3 = this.git("move_untracked_aside", #{ since: pre });
        check(field_of(F3, "F3", "untracked", "array").len() == 0, "F3.untracked: files remain after moving them aside");
        last = F3;
        last_name = "F3";
    }
    check(field_of(last, last_name, "porcelain", "string") == "", last_name + ".porcelain: the tree is not clean");
}

// Step 1: the pre-task commit, recorded in the run state.
fn begin(id) {
    let S1 = this.git("snapshot", #{ base: "" });
    check(field_of(S1, "S1", "porcelain", "string") == "", "S1.porcelain: the tree is not clean");
    let pre = field_of(S1, "S1", "head", "string");
    this.state.tasks[id] = #{ pre: pre, receipt: () };
    this.write_state();
    pre
}

// Step 1, then at most two attempts: Grok retries once, with a new agent on the same model.
fn run_task(t, B) {
    this.results.push(#{ id: t.id, outcome: "fail", attempts: 0, teeth: this.skipped(t.kind), model: "" });
    let pre = this.begin(t.id);
    let failure = "";
    let passed = false;
    let n = 0;
    while !passed && n < 2 {
        n += 1;
        this.set_result("attempts", n);
        this.set_result("model", global::GROK_MODEL);
        this.set_result("teeth", this.skipped(t.kind));
        try {
            this.attempt(t, B, pre, failure);
            passed = true;
        } catch (e) {
            if !is_fail(e) { throw e; }
            failure = "attempt " + n.to_string() + ": " + e.why;
        }
        if !passed { this.restore(pre); }
    }
    check(passed, "task " + t.id + " failed 2 attempts; last: " + failure);
    this.set_result("outcome", "pass");
}

// [display name, dimension]
const DIMENSIONS = [
    ["behaviour", "the behaviour the plan claims, and the interactions between the tasks"],
    ["failures", "failure paths, lost work, and a success report that is false"],
    ["invariants", "forbidden changes, and broken invariants named in the rules"],
];

fn review_prompt(dimension, name_status, diff_file) {
    let a = this.args;
    let p = "You review the whole branch after a plan ran. Read the repo at " + a.repo + " as needed; change nothing.\n";
    p += "Dimension: " + dimension + "\nRules: " + json_encode(a.rules) + "\nForbidden paths: " + names(a.forbid) + "\n\n";
    p += "Changed paths (git diff --name-status):\n" + name_status + "\n\nDiff from the run start: " + diff_line(diff_file);
    p += "\n\nRead the changed files with read_file before answering; do not answer from memory. ";
    p += "Report only real problems in your dimension. Each finding has file (a repo-relative path), issue, and severity. ";
    p += "Return an empty list when there are none.";
    p
}

fn verify_prompt(f, name_status, diff_file) {
    let p = "A reviewer reported this finding about the branch. Try to prove it wrong. Read the repo at " + this.args.repo + " as needed; change nothing.\n";
    p += "File: " + f.file + "\nIssue: " + f.issue + "\nSeverity: " + text_of(f.severity) + "\n\n";
    p += "Changed paths (git diff --name-status):\n" + name_status + "\n\nDiff from the run start: " + diff_line(diff_file);
    p += "\n\nReturn real true only when the code confirms the problem, with the evidence (path, lines, what they do). ";
    p += "Otherwise return real false.";
    p
}

fn fix_prompt(t, pre) {
    let a = this.args;
    let p = "Fix the confirmed review findings below. Work in " + a.repo + ", on the current branch (at " + pre + ").\n";
    p += "Files: " + names(t.files) + "\nTests: " + names(t.tests) + "\n";
    p += "Change only those paths. Never touch paths matching: " + names(a.forbid) + "\nTest command: " + a.test_cmd + "\n";
    if lint_given(a) { p += "Lint command: " + a.lint_cmd + "\n"; }
    p += "\nFindings:\n" + t.brief + "\n\n";
    p += "Conventional commit; say why in the body. Never push. No co-author trailer.\n";
    p += "Commit your work and leave the tree clean.";
    p
}

// CONTRACT.md section 7: three reviewers, one verifier per finding, one fix as task review-fix.
fn review_stage(B) {
    let a = this.args;
    let RV = this.git("snapshot", #{ base: this.state.run_start });
    let ns = field_of(RV, "RV", "name_status", "string");
    let diff_file = field_of(RV, "RV", "diff_file", "string");
    let prompts = [];
    let labels = [];
    for d in global::DIMENSIONS {
        prompts.push(this.review_prompt(d[1], ns, diff_file));
        labels.push("review · " + d[0]);
    }
    let findings = [];
    for rv in this.call_agent("review", prompts, labels) {
        check(type_of(rv) == "map" && type_of(rv.findings) == "array", "review.findings: a reviewer returned no usable report");
        for f in rv.findings {
            check(type_of(f) == "map" && type_of(f.file) == "string" && type_of(f.issue) == "string",
                "review.findings: a reviewer returned no usable report");
            findings.push(f);
        }
    }
    if findings.len() == 0 { return "review: 0 findings, none confirmed"; }
    let prompts = [];
    let labels = [];
    for f in findings {
        prompts.push(this.verify_prompt(f, ns, diff_file));
        labels.push("verify · " + f.file);
    }
    let verdicts = this.call_agent("verify-finding", prompts, labels);
    let confirmed = [];
    for i in 0..findings.len() {
        let v = verdicts[i];
        check(type_of(v) == "map" && type_of(v.real) == "bool" && type_of(v.evidence) == "string",
            "verify-finding: a verifier returned no usable report");
        let ev = v.evidence;
        ev.trim();
        if v.real && ev != "" {
            let f = findings[i];
            f.evidence = ev;
            confirmed.push(f);
        }
    }
    if confirmed.len() == 0 { return "review: " + findings.len().to_string() + " findings, none confirmed"; }

    // Fix scope in code: confirmed paths, deduplicated, minus forbid, split by rules.test_globs.
    let seen = [];
    let files = [];
    let tests = [];
    let brief = "";
    for f in confirmed {
        if !seen.contains(f.file) && !matches(f.file, a.forbid) {
            if matches(f.file, a.rules.test_globs) { tests.push(f.file); } else { files.push(f.file); }
        }
        seen.push(f.file);
        if brief != "" { brief += "\n"; }
        brief += "- " + f.file + ": " + f.issue + " (" + text_of(f.severity) + "). Evidence: " + f.evidence;
    }
    check(files.len() + tests.len() > 0, "review: every confirmed finding is in a forbidden path");
    let t = #{ id: "review-fix", title: "Fix confirmed review findings", files: files, tests: tests, kind: (), brief: brief };

    this.current = t.id;
    this.prefix = "review · task " + t.id;
    this.results.push(#{ id: t.id, outcome: "fail", attempts: 0, teeth: "skipped:test", model: global::GROK_MODEL });
    let pre = this.begin(t.id);
    this.set_result("attempts", 1);
    try {
        this.attempt(t, B, pre, "");
    } catch (e) {
        if !is_fail(e) { throw e; }
        this.restore(pre);
        throw fail("task review-fix failed; " + e.why);
    }
    this.set_result("outcome", "pass");
    this.current = ();
    "review: fixed " + confirmed.len().to_string() + " confirmed findings"
}

fn run_all() {
    phase("Preflight");
    this.check_args();
    let B = this.preflight();
    this.stage = "plan";
    phase("Plan");
    let order = this.plan_order();
    this.stage = "preflight";
    let done = this.run_state();
    this.stage = "task";
    for t in order {
        this.current = t.id;
        if done.contains(t.id) {
            this.results.push(#{ id: t.id, outcome: "done-before", attempts: 0, teeth: this.skipped(t.kind), model: "" });
        } else {
            phase(t.phase);
            this.prefix = t.subproject + " · task " + t.id;
            this.run_task(t, B);
        }
    }
    this.current = ();
    this.prefix = ();
    let note = "";
    if this.level == "full" {
        this.stage = "review";
        phase("Review");
        note = if this.args.review == false { "" } else { "; " + this.review_stage(B) };
    }
    this.stage = "done";
    note
}

let st = #{ args: args, stage: "preflight", current: (), prefix: (), results: [], used: #{}, state: (), level: () };
let result = ();
try {
    let note = st.run_all();
    result = #{ ok: true, stage: "done", task: (), summary: st.results.len().to_string() + " tasks passed" + note, tasks: st.results, level: st.level };
} catch (e) {
    if type_of(e) != "map" || (e.kind != "fail" && e.kind != "stop") { throw e; }
    result = #{ ok: false, stage: st.stage, task: st.current, summary: e.why, tasks: st.results, level: st.level };
}
// Grok's agent call reports no model and takes no effort (effort xhigh is set at launch).
result.summary += "; model and effort: requested only";
complete(result);
