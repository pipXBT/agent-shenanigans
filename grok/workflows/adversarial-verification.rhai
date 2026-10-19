let meta = #{
    name: "adversarial-verification",
    description: "Split the build into dependent tasks, then implement one at a time with skeptic, teeth, and gates.",
    when_to_use: "Any repo. Pass args.repo, args.test_cmd, and args.tasks. Optional args.ponytail is full or ultra. One fix round per task. Stops on a second failure.",
    phases: [
        #{ title: "Plan", detail: "phases, subprojects, tasks, deps, model tier" },
        #{ title: "Tasks", detail: "implement, skeptic, teeth, gates, dependency order" },
        #{ title: "Review", detail: "three reviewers, one skeptic per finding" },
    ],
};

fn trimmed(s) {
    if type_of(s) == "string" {
        s.trim();
        s
    } else {
        ""
    }
}

fn as_bool(v, fallback) {
    if v == () { fallback } else if type_of(v) == "bool" { v } else { fallback }
}

fn as_str(v) {
    if v == () { "" } else if type_of(v) == "string" { v } else { "" }
}

fn out_of(slot) {
    if slot == () {
        ()
    } else if !slot.success {
        ()
    } else if slot.output == () {
        ()
    } else if type_of(slot.output) != "map" {
        ()
    } else {
        slot.output
    }
}

fn gate_pass(slot) {
    let o = out_of(slot);
    if o == () { false } else { as_bool(o.test_ok, false) && as_bool(o.clippy_ok, false) }
}

fn skeptic_pass(slot) {
    let o = out_of(slot);
    if o == () { false } else { trimmed(as_str(o.verdict)) == "pass" }
}

fn teeth_pass(slot) {
    let o = out_of(slot);
    if o == () { false } else { as_bool(o.teeth_ok, false) && as_bool(o.restored, false) }
}

fn task_field(t, name) {
    if t == () {
        ""
    } else if type_of(t) != "map" {
        ""
    } else if t[name] == () {
        ""
    } else {
        as_str(t[name])
    }
}

let result_schema = #{
    "type": "object",
    "properties": #{
        "summary": #{ "type": "string" },
        "committed": #{ "type": "boolean" },
        "commit_sha": #{ "type": "string" },
        "verdict": #{ "type": "string" },
        "evidence": #{ "type": "string" },
        "test_ok": #{ "type": "boolean" },
        "clippy_ok": #{ "type": "boolean" },
        "teeth_ok": #{ "type": "boolean" },
        "restored": #{ "type": "boolean" },
        "issues": #{ "type": "array", "items": #{ "type": "string" } },
    },
};

let findings_schema = #{
    "type": "object",
    "properties": #{
        "findings": #{
            "type": "array",
            "maxItems": 8,
            "items": #{
                "type": "object",
                "properties": #{
                    "file": #{ "type": "string" },
                    "issue": #{ "type": "string" },
                    "severity": #{ "type": "string" },
                },
            },
        },
        "summary": #{ "type": "string" },
    },
};

let verdict_schema = #{
    "type": "object",
    "properties": #{
        "real": #{ "type": "boolean" },
        "reason": #{ "type": "string" },
        "evidence": #{ "type": "string" },
        "severity": #{ "type": "string" },
    },
};

let repo = if args == () { "" } else { trimmed(as_str(args.repo)) };
let test_cmd = if args == () { "" } else { trimmed(as_str(args.test_cmd)) };
let lint_cmd = if args == () { "" } else { trimmed(as_str(args.lint_cmd)) };
let branch = if args == () { "" } else { trimmed(as_str(args.branch)) };
let extra_rules = if args == () { "" } else { as_str(args.rules) };
let forbid = if args == () { "" } else { as_str(args.forbid) };
let base_sha = if args == () { "" } else { trimmed(as_str(args.base_sha)) };
let do_review = if args == () { true } else if args.review == () { true } else { as_bool(args.review, true) };
let ponytail = "full";
if args != () && args.ponytail != () && trimmed(as_str(args.ponytail)) == "ultra" {
    ponytail = "ultra";
}

let tasks = [];
if args != () && args.tasks != () && type_of(args.tasks) == "array" {
    for t in args.tasks {
        tasks.push(t);
    }
} else if args != () && trimmed(as_str(args.title)) != "" {
    tasks.push(#{
        title: as_str(args.title),
        brief: as_str(args.brief),
        plan: as_str(args.plan),
    });
}

if repo == "" || test_cmd == "" || tasks.len() == 0 {
    pause("verification", "Pass args.repo, args.test_cmd, and args.tasks (or args.title plus args.brief). Optional: lint_cmd, branch, rules, forbid, base_sha, review.");
}

let rules = "";
rules += "Repo: ";
rules += repo;
rules += "\ncd there before any command.\n";
if branch != "" {
    rules += "Commit only on branch ";
    rules += branch;
    rules += ".\n";
}
rules += "Never commit to main. Never push. Never git stash. Never add a Co-Authored-By trailer.\n";
rules += "Stage only files this task changed. Do not stage secrets or .grok/.\n";
rules += "Test command: ";
rules += test_cmd;
rules += "\n";
if lint_cmd != "" {
    rules += "Lint command: ";
    rules += lint_cmd;
    rules += "\n";
} else {
    rules += "No lint command. Do not invent one.\n";
}
if extra_rules != "" {
    rules += "Caller rules:\n";
    rules += extra_rules;
    rules += "\n";
}
if forbid != "" {
    rules += "Do not change these. A finding that only restates them is out of scope:\n";
    rules += forbid;
    rules += "\n";
}

fn modes(p, level) {
    let s = "";
    s += "Follow the caveman skill at ultra and the ponytail skill at ";
    s += level;
    s += ".\n";
    s += "Caveman ultra: drop articles and filler. Fragments are OK. Keep not, never, no, only, and except. Do not invent abbreviations. Do not use arrows. State each fact once.\n";
    s += "Ponytail ";
    s += level;
    s += ": smallest change that finishes the task. No extra options, wrappers, or abstractions. Deletion beats addition. A bug fix goes in the shared code. End with what you skipped and the risk.\n";
    if level == "ultra" {
        s += "Question any part the need does not justify. Do not build that part.\n";
    }
    s += "Code, comments, commit messages, and schema JSON stay normal English.\n";
    s += "This run is Grok. Use the strongest Grok model. Effort is xhigh. Do not lower effort. Never use Fable.\n";
    s += "A Claude run of the same task uses effort xhigh and the recorded Claude model: Haiku 5.5, Sonnet 5.5, or Opus 5.5. Opus 5 means Opus 5.5.\n\n";
    s += p;
    s
}

fn listed(ids, id) {
    let hit = false;
    for x in ids {
        if x == id { hit = true; }
    }
    hit
}

fn as_str_list(v) {
    let out = [];
    if v != () && type_of(v) == "array" {
        for item in v {
            let s = trimmed(as_str(item));
            if s != "" { out.push(s); }
        }
    }
    out
}

fn complexity_of(raw) {
    if raw == "low" || raw == "medium" || raw == "high" { raw } else { "high" }
}

fn claude_model_for(complexity) {
    if complexity == "low" {
        "Haiku 5.5"
    } else if complexity == "medium" {
        "Sonnet 5.5"
    } else {
        "Opus 5.5"
    }
}

fn next_claude(model) {
    if model == "Haiku 5.5" {
        "Sonnet 5.5"
    } else if model == "Sonnet 5.5" {
        "Opus 5.5"
    } else {
        "Opus 5.5"
    }
}

fn deps_done(t, done_ids) {
    let ok = true;
    for d in t.depends_on {
        if !listed(done_ids, d) { ok = false; }
    }
    ok
}

fn ready_tasks(pending, done_ids) {
    let out = [];
    for t in pending {
        if deps_done(t, done_ids) { out.push(t); }
    }
    out
}

fn without_id(pending, id) {
    let out = [];
    for t in pending {
        if t.id != id { out.push(t); }
    }
    out
}

fn shares_file(a, b) {
    if a.files.len() == 0 || b.files.len() == 0 {
        true
    } else {
        let hit = false;
        for x in a.files {
            for y in b.files {
                if x == y { hit = true; }
            }
        }
        hit
    }
}

fn wave_note(ready) {
    let ids = "";
    let n = 0;
    let parallel_ok = true;
    for t in ready {
        if n > 0 { ids += ", "; }
        ids += t.id;
        n += 1;
    }
    for a in ready {
        for b in ready {
            if a.id != b.id && shares_file(a, b) { parallel_ok = false; }
        }
    }
    if n > 1 && parallel_ok {
        log("parallel-eligible " + ids + " — run one at a time so gates read one HEAD");
    } else if n > 1 {
        log("sequential " + ids + " — shared or unknown files");
    } else if n == 1 {
        log("sequential " + ids);
    }
}

fn normalize_plan(plan) {
    if plan == () || type_of(plan) != "map" || plan["phases"] == () || type_of(plan["phases"]) != "array" {
        #{ ok: false, error: "Plan agent returned no phases.", tasks: [] }
    } else {
        let tasks = [];
        let seen = [];
        let order = 0;
        let bad = "";
        for stage in plan["phases"] {
            let subs = if stage == () { () } else { stage["subprojects"] };
            if bad == "" && (subs == () || type_of(subs) != "array") {
                bad = "A phase is missing subprojects.";
            } else if bad == "" {
                let stage_name = task_field(stage, "name");
                for sub in subs {
                    let task_list = if sub == () { () } else { sub["tasks"] };
                    if bad == "" && (task_list == () || type_of(task_list) != "array") {
                        bad = "A subproject is missing tasks.";
                    } else if bad == "" {
                        let sub_name = task_field(sub, "name");
                        for task in task_list {
                            if bad == "" {
                                let id = task_field(task, "id");
                                let title = task_field(task, "title");
                                if id == "" || title == "" {
                                    bad = "A task is missing id or title.";
                                } else if listed(seen, id) {
                                    bad = "Duplicate task id " + id;
                                } else {
                                    seen.push(id);
                                    let complexity = complexity_of(task_field(task, "complexity"));
                                    let model = claude_model_for(complexity);
                                    let given = task_field(task, "claude_model");
                                    if given != "" && given != model {
                                        log("model tier corrected " + id);
                                    }
                                    let deps = if task == () { [] } else { as_str_list(task["depends_on"]) };
                                    let files = if task == () { [] } else { as_str_list(task["files"]) };
                                    tasks.push(#{
                                        id: id,
                                        title: title,
                                        brief: task_field(task, "brief"),
                                        plan: task_field(task, "plan"),
                                        depends_on: deps,
                                        complexity: complexity,
                                        claude_model: model,
                                        grok_model: "strongest Grok",
                                        grok_effort: "xhigh",
                                        files: files,
                                        phase_name: stage_name,
                                        subproject: sub_name,
                                        order: order,
                                    });
                                    order += 1;
                                }
                            }
                        }
                    }
                }
            }
        }
        if bad != "" {
            #{ ok: false, error: bad, tasks: [] }
        } else if tasks.len() == 0 {
            #{ ok: false, error: "Plan agent returned no tasks.", tasks: [] }
        } else {
            let missing = "";
            for t in tasks {
                for d in t.depends_on {
                    if !listed(seen, d) && missing == "" {
                        missing = "Task " + t.id + " depends on unknown id " + d;
                    }
                }
            }
            if missing != "" {
                #{ ok: false, error: missing, tasks: [] }
            } else {
                #{ ok: true, error: "", tasks: tasks }
            }
        }
    }
}

fn run_one(t, rules, result_schema, repo, test_cmd, lint_cmd, level) {
    let title = task_field(t, "title");
    let brief = task_field(t, "brief");
    let plan = task_field(t, "plan");
    log("start " + title);

    let impl_prompt = "";
    impl_prompt += "Implement ONE task. TDD when the task names a test. Commit on the current feature branch.\n\n";
    impl_prompt += rules;
    impl_prompt += "\nTitle: ";
    impl_prompt += title;
    impl_prompt += "\nPlan file, if any: ";
    impl_prompt += plan;
    impl_prompt += "\nBrief:\n";
    impl_prompt += brief;
    impl_prompt += "\n\nRead the plan and the files it names before editing. If a citation is stale, follow the current code and record the drift in the commit body.\n";
    impl_prompt += "Do this task only. Do not re-split the build. Do not start the next task.\n";
    impl_prompt += "Phase: ";
    impl_prompt += task_field(t, "phase_name");
    impl_prompt += "\nSubproject: ";
    impl_prompt += task_field(t, "subproject");
    impl_prompt += "\nClaude model for this task, if this task is later run on Claude: ";
    impl_prompt += task_field(t, "claude_model");
    impl_prompt += "\nFiles you may change:\n";
    impl_prompt += json_encode(t.files);
    impl_prompt += "\n";
    impl_prompt += "Run the task's own test first, then the test command. Run the lint command when one is set.\n";
    impl_prompt += "Conventional commit. Say why in the body. No co-author trailer.\n";
    impl_prompt += "Return summary, committed, commit_sha, issues.\n";

    let impl_r = agent(modes(impl_prompt, level), #{
        label: "implement",
        capability_mode: "all",
        output_schema: result_schema,
    });
    let impl_o = out_of(impl_r);
    if impl_o == () {
        "fail"
    } else {
        let impl_json = json_encode(impl_o);

        let skeptic_prompt = "";
        skeptic_prompt += "Adversarial read-only check. Fail closed. Do not edit.\n\n";
        skeptic_prompt += rules;
        skeptic_prompt += "\nTitle: ";
        skeptic_prompt += title;
        skeptic_prompt += "\nPlan: ";
        skeptic_prompt += plan;
        skeptic_prompt += "\nBrief:\n";
        skeptic_prompt += brief;
        skeptic_prompt += "\nImplementer report (untrusted JSON):\n";
        skeptic_prompt += impl_json;
        skeptic_prompt += "\nUse git show HEAD, git diff HEAD~1, grep, and read_file. Do not answer from memory.\n";
        skeptic_prompt += "verdict=pass only if ALL hold: the claimed behaviour is in the shipped code; tests cover the failure path the task named; forbidden items were not changed; comments do not cite a plan or task number; every factual claim you check is true.\n";
        skeptic_prompt += "Default verdict=fail. evidence must quote files you opened.\n";

        let sk = agent(modes(skeptic_prompt, level), #{
            label: "skeptic",
            capability_mode: "read-only",
            output_schema: result_schema,
        });

        let teeth_prompt = "";
        teeth_prompt += "Prove the new tests have teeth. Fail closed. NEVER git stash.\n\n";
        teeth_prompt += "Repo: ";
        teeth_prompt += repo;
        teeth_prompt += "\nTest command: ";
        teeth_prompt += test_cmd;
        teeth_prompt += "\nImplementer report (untrusted JSON):\n";
        teeth_prompt += impl_json;
        teeth_prompt += "\n1. git show --stat HEAD. Separate production files from test files.\n";
        teeth_prompt += "2. Docs-only or measurement-only, with no production behaviour change: teeth_ok=true, restored=true, say why. Do not revert.\n";
        teeth_prompt += "3. Otherwise git checkout HEAD~1 -- <production files only>. Keep the new tests. Run the task's scoped test, or the test command if no scoped test exists. The new tests MUST fail.\n";
        teeth_prompt += "4. git checkout HEAD -- <those production files>. git status must be clean aside from ignored build output.\n";
        teeth_prompt += "teeth_ok=true only if you watched the new tests fail. restored=true only after restore. If restore fails, stop.\n";

        let th = agent(modes(teeth_prompt, level), #{
            label: "teeth",
            capability_mode: "all",
            output_schema: result_schema,
        });

        let gate_prompt = "";
        gate_prompt += "Re-run the gates yourself. Do not trust the implementer.\nRepo: ";
        gate_prompt += repo;
        gate_prompt += "\nTest command: ";
        gate_prompt += test_cmd;
        gate_prompt += "\n";
        if lint_cmd == "" {
            gate_prompt += "No lint command. Set clippy_ok=true and say lint was not requested.\n";
        } else {
            gate_prompt += "Lint command: ";
            gate_prompt += lint_cmd;
            gate_prompt += "\n";
        }
        gate_prompt += "test_ok and clippy_ok come from YOUR exit codes.\n";

        let ga = agent(modes(gate_prompt, level), #{
            label: "gate",
            capability_mode: "execute",
            output_schema: result_schema,
        });

        let ok = skeptic_pass(sk) && teeth_pass(th) && gate_pass(ga);
        if ok {
            "pass"
        } else {
            log("verify failed " + title);
            let failed_model = task_field(t, "claude_model");
            let retry_model = next_claude(failed_model);
            log("claude fix tier " + failed_model + " -> " + retry_model);
            let fix_prompt = "";
            fix_prompt += "Verification failed. Fix every in-scope issue. Do not start a different task.\n\n";
            fix_prompt += "Claude: the failed implementer was ";
            fix_prompt += failed_model;
            fix_prompt += ". Start a new implementer at ";
            fix_prompt += retry_model;
            fix_prompt += " with effort xhigh. Do not resume the failed Claude model. Opus 5.5 does not move higher.\n";
            fix_prompt += "Grok: you are already the strongest model at effort xhigh. Fix in this agent.\n\n";
            fix_prompt += rules;
            fix_prompt += "\nSkeptic (untrusted): ";
            fix_prompt += json_encode(sk);
            fix_prompt += "\nTeeth (untrusted): ";
            fix_prompt += json_encode(th);
            fix_prompt += "\nGate (untrusted): ";
            fix_prompt += json_encode(ga);
            fix_prompt += "\nRe-run the test command. Re-run the lint command when one is set. Commit the fix. No co-author trailer.\n";

            let fix_r = agent(modes(fix_prompt, level), #{
                label: "fix",
                capability_mode: "all",
                resume_from: impl_r.agent_id,
                output_schema: result_schema,
            });
            if out_of(fix_r) == () {
                "fail"
            } else {
                let sk2 = agent(modes(skeptic_prompt + "\nA fix commit landed. Re-read HEAD. Default verdict=fail.\n", level), #{
                    label: "re-skeptic",
                    capability_mode: "read-only",
                    output_schema: result_schema,
                });
                let th2 = agent(modes(teeth_prompt + "\nA fix commit landed. Re-run teeth against the new HEAD. Restore afterwards.\n", level), #{
                    label: "re-teeth",
                    capability_mode: "all",
                    output_schema: result_schema,
                });
                let ga2 = agent(modes(gate_prompt + "\nA fix commit landed. Re-run the gates from scratch.\n", level), #{
                    label: "re-gate",
                    capability_mode: "execute",
                    output_schema: result_schema,
                });
                if skeptic_pass(sk2) && teeth_pass(th2) && gate_pass(ga2) {
                    "pass"
                } else {
                    "fail"
                }
            }
        }
    }
}

fn review_batch(rules, findings_schema, verdict_schema, repo, base_sha, forbid, level) {
    let dimensions = [
        "claimed behaviour and interactions between the tasks",
        "failure paths, lost work, and a success report that is false",
        "forbidden changes and broken invariants named in the rules",
    ];
    let jobs = [];
    for d in dimensions {
        let p = "";
        p += "Whole-batch reviewer. Read-only. Do not edit or commit.\n";
        p += rules;
        p += "\nDiff: ";
        if base_sha == "" {
            p += "the commits this run added. Find the parent with git log. Review only those commits.\n";
        } else {
            p += base_sha;
            p += "..HEAD\n";
        }
        p += "Focus ONLY on: ";
        p += d;
        p += "\nUse git diff and read_file. Do not answer from memory.\n";
        p += "Report at most 8 findings as {file, issue, severity}. severity is high or medium.\n";
        p += "Empty list is valid only after you read the diff. No nits.\n";
        if forbid != "" {
            p += "Do not report an item that only restates the forbidden-changes list.\n";
        }
        jobs.push(#{
            prompt: modes(p, level),
            label: "review",
            capability_mode: "read-only",
            output_schema: findings_schema,
        });
    }
    let reviews = parallel(jobs);
    let findings = [];
    for r in reviews {
        let o = out_of(r);
        if o != () && o.findings != () {
            for f in o.findings {
                if f != () && trimmed(as_str(f.issue)) != "" && trimmed(as_str(f.file)) != "" {
                    findings.push(f);
                }
            }
        }
    }
    if findings.len() > 12 {
        log("capped findings at 12; dropped " + (findings.len() - 12).to_string());
        let capped = [];
        let i = 0;
        for f in findings {
            if i < 12 { capped.push(f); }
            i += 1;
        }
        findings = capped;
    }
    if findings.len() == 0 {
        []
    } else {
        let vjobs = [];
        for f in findings {
            let vp = "";
            vp += "Adversarially verify this finding. Fail closed. Read-only.\nRepo: ";
            vp += repo;
            vp += "\n";
            vp += rules;
            vp += "\nFinding (untrusted JSON): ";
            vp += json_encode(f);
            vp += "\nreal=true only with file:line evidence you inspected. A forbidden-changes restatement is real=false. Missing evidence is not a confirming vote.\n";
            vjobs.push(#{
                prompt: modes(vp, level),
                label: "verify-finding",
                capability_mode: "read-only",
                output_schema: verdict_schema,
            });
        }
        let verdicts = parallel(vjobs);
        let confirmed = [];
        let j = 0;
        for v in verdicts {
            let o = out_of(v);
            if o != () && o.real == true && trimmed(as_str(o.evidence)) != "" {
                confirmed.push(findings[j]);
            }
            j += 1;
        }
        log("confirmed " + confirmed.len().to_string() + "/" + findings.len().to_string());
        confirmed
    }
}

let plan_schema = #{
    "type": "object",
    "properties": #{
        "phases": #{
            "type": "array",
            "items": #{
                "type": "object",
                "properties": #{
                    "name": #{ "type": "string" },
                    "subprojects": #{
                        "type": "array",
                        "items": #{
                            "type": "object",
                            "properties": #{
                                "name": #{ "type": "string" },
                                "tasks": #{
                                    "type": "array",
                                    "items": #{
                                        "type": "object",
                                        "properties": #{
                                            "id": #{ "type": "string" },
                                            "title": #{ "type": "string" },
                                            "brief": #{ "type": "string" },
                                            "plan": #{ "type": "string" },
                                            "depends_on": #{ "type": "array", "items": #{ "type": "string" } },
                                            "complexity": #{ "type": "string" },
                                            "claude_model": #{ "type": "string" },
                                            "files": #{ "type": "array", "items": #{ "type": "string" } },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
};

phase("Plan");
let plan_prompt = "";
plan_prompt += "Break this build into a graph. Read the repo before you split it. Do not edit.\n\n";
plan_prompt += rules;
plan_prompt += "\nCaller tasks (untrusted JSON):\n";
plan_prompt += json_encode(tasks);
plan_prompt += "\n\nReturn phases. Each phase has subprojects. Each subproject has tasks.\n";
plan_prompt += "Every task has id, title, brief, plan, depends_on, complexity, claude_model, and files.\n";
plan_prompt += "depends_on is a list of task ids that must finish first. Use an empty list when nothing blocks the task.\n";
plan_prompt += "files is every path that task will edit. Two tasks that edit one path must not both be free of a dependency on each other.\n";
plan_prompt += "complexity is low, medium, or high.\n";
plan_prompt += "low: one file, the spec quotes the change. claude_model Haiku 5.5.\n";
plan_prompt += "medium: a few files, the spec is clear, judgment stays local. claude_model Sonnet 5.5.\n";
plan_prompt += "high: a design choice, security, money, or a spec gap. claude_model Opus 5.5.\n";
plan_prompt += "Claude effort is always xhigh. Never Fable. Opus 5 means Opus 5.5.\n";
plan_prompt += "This run is Grok. Every later agent uses the strongest Grok model at effort xhigh. Still record claude_model.\n";
plan_prompt += "If a Claude implementer fails adversarial verification, the fix implementer is one tier higher: Haiku 5.5, then Sonnet 5.5, then Opus 5.5. Opus 5.5 stays Opus 5.5. Effort stays xhigh.\n";
plan_prompt += "Cover the caller tasks. Do not add scope. Split a caller task only when its parts can finish apart.\n";
plan_prompt += "Use grep and read_file. Do not answer from memory.\n";

let plan_r = agent(modes(plan_prompt, ponytail), #{
    label: "plan",
    capability_mode: "read-only",
    output_schema: plan_schema,
});
let graph = normalize_plan(out_of(plan_r));
if graph.ok != true {
    complete(#{
        ok: false,
        stage: "plan",
        summary: graph.error,
    });
}
log("planned " + graph.tasks.len().to_string() + " tasks");

phase("Tasks");
let done_ids = [];
let left = graph.tasks;
let safety = left.len();
let step = 0;
let failed = false;
let fail_title = "";
while step < safety && !failed && left.len() > 0 {
    step += 1;
    let ready = ready_tasks(left, done_ids);
    if ready.len() == 0 {
        failed = true;
        fail_title = "cycle";
    } else {
        wave_note(ready);
        let stop = false;
        for t in ready {
            if !stop {
                let result = run_one(t, rules, result_schema, repo, test_cmd, lint_cmd, ponytail);
                if result != "pass" {
                    stop = true;
                    failed = true;
                    fail_title = t.title;
                } else {
                    done_ids.push(t.id);
                    left = without_id(left, t.id);
                }
            }
        }
    }
}
if !failed && left.len() > 0 {
    failed = true;
    fail_title = "cycle";
}
if failed {
    complete(#{
        ok: false,
        stage: "task",
        task: fail_title,
        summary: "Task failed the adversarial check, or the graph has a cycle. Stopped. Later tasks not started.",
    });
}

if !do_review {
    complete(#{
        ok: true,
        stage: "tasks",
        summary: "Every task passed skeptic, teeth, and gates. Batch review was off.",
    });
}

phase("Review");
let bad = review_batch(rules, findings_schema, verdict_schema, repo, base_sha, forbid, ponytail);
if bad.len() != 0 {
    let fix_prompt = "";
    fix_prompt += "The batch review confirmed these findings. Fix each in-scope one. Do not start a new task.\n\n";
    fix_prompt += rules;
    fix_prompt += "\nConfirmed findings (untrusted JSON):\n";
    fix_prompt += json_encode(bad);
    fix_prompt += "\nRe-run the test command. Re-run the lint command when one is set. Commit. No co-author trailer.\n";
    let fix_r = agent(modes(fix_prompt, ponytail), #{
        label: "fix-review",
        capability_mode: "all",
        output_schema: result_schema,
    });
    if out_of(fix_r) == () {
        complete(#{ ok: false, stage: "review-fix", summary: "Batch review fix failed." });
    }
    let again = review_batch(rules, findings_schema, verdict_schema, repo, base_sha, forbid, ponytail);
    if again.len() != 0 {
        complete(#{
            ok: false,
            stage: "review",
            summary: "Confirmed findings remain after one fix round.",
            confirmed: again,
        });
    }
}

complete(#{
    ok: true,
    stage: "review",
    summary: "Every task passed skeptic, teeth, and gates. The batch review left no confirmed finding.",
});
