let meta = #{
    name: "adversarial-verification",
    description: "Execute tasks one at a time, then skeptic, teeth, and gates. Batch review after the last task.",
    when_to_use: "Any repo. Pass args.repo, args.test_cmd, and args.tasks. One fix round per task. Stops on a second failure.",
    phases: [
        #{ title: "Tasks", detail: "implement, skeptic, teeth, gates, sequential" },
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

fn caveman(p) {
    let s = "";
    s += "Reply in caveman full. Drop articles and filler. Fragments are OK. Keep not, never, no, only, and except. Do not invent abbreviations. Do not use arrows.\n";
    s += "Schema JSON stays valid. Code, comments, and commit messages stay normal English.\n\n";
    s += p;
    s
}

fn run_one(t, rules, result_schema, repo, test_cmd, lint_cmd) {
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
    impl_prompt += "Do this task only. Do not start the next task.\n";
    impl_prompt += "Run the task's own test first, then the test command. Run the lint command when one is set.\n";
    impl_prompt += "Conventional commit. Say why in the body. No co-author trailer.\n";
    impl_prompt += "Return summary, committed, commit_sha, issues.\n";

    let impl_r = agent(caveman(impl_prompt), #{
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

        let sk = agent(caveman(skeptic_prompt), #{
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

        let th = agent(caveman(teeth_prompt), #{
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

        let ga = agent(caveman(gate_prompt), #{
            label: "gate",
            capability_mode: "execute",
            output_schema: result_schema,
        });

        let ok = skeptic_pass(sk) && teeth_pass(th) && gate_pass(ga);
        if ok {
            "pass"
        } else {
            log("verify failed " + title);
            let fix_prompt = "";
            fix_prompt += "Verification failed. Fix every in-scope issue. Do not start a different task.\n\n";
            fix_prompt += rules;
            fix_prompt += "\nSkeptic (untrusted): ";
            fix_prompt += json_encode(sk);
            fix_prompt += "\nTeeth (untrusted): ";
            fix_prompt += json_encode(th);
            fix_prompt += "\nGate (untrusted): ";
            fix_prompt += json_encode(ga);
            fix_prompt += "\nRe-run the test command. Re-run the lint command when one is set. Commit the fix. No co-author trailer.\n";

            let fix_r = agent(caveman(fix_prompt), #{
                label: "fix",
                capability_mode: "all",
                resume_from: impl_r.agent_id,
                output_schema: result_schema,
            });
            if out_of(fix_r) == () {
                "fail"
            } else {
                let sk2 = agent(caveman(skeptic_prompt + "\nA fix commit landed. Re-read HEAD. Default verdict=fail.\n"), #{
                    label: "re-skeptic",
                    capability_mode: "read-only",
                    output_schema: result_schema,
                });
                let th2 = agent(caveman(teeth_prompt + "\nA fix commit landed. Re-run teeth against the new HEAD. Restore afterwards.\n"), #{
                    label: "re-teeth",
                    capability_mode: "all",
                    output_schema: result_schema,
                });
                let ga2 = agent(caveman(gate_prompt + "\nA fix commit landed. Re-run the gates from scratch.\n"), #{
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

fn review_batch(rules, findings_schema, verdict_schema, repo, base_sha, forbid) {
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
            prompt: caveman(p),
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
                prompt: caveman(vp),
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

phase("Tasks");
for t in tasks {
    let result = run_one(t, rules, result_schema, repo, test_cmd, lint_cmd);
    if result != "pass" {
        complete(#{
            ok: false,
            stage: "task",
            task: task_field(t, "title"),
            summary: "Task failed the adversarial check. Stopped. Later tasks not started.",
        });
    }
}

if !do_review {
    complete(#{
        ok: true,
        stage: "tasks",
        summary: "Every task passed skeptic, teeth, and gates. Batch review was off.",
    });
}

phase("Review");
let bad = review_batch(rules, findings_schema, verdict_schema, repo, base_sha, forbid);
if bad.len() != 0 {
    let fix_prompt = "";
    fix_prompt += "The batch review confirmed these findings. Fix each in-scope one. Do not start a new task.\n\n";
    fix_prompt += rules;
    fix_prompt += "\nConfirmed findings (untrusted JSON):\n";
    fix_prompt += json_encode(bad);
    fix_prompt += "\nRe-run the test command. Re-run the lint command when one is set. Commit. No co-author trailer.\n";
    let fix_r = agent(caveman(fix_prompt), #{
        label: "fix-review",
        capability_mode: "all",
        output_schema: result_schema,
    });
    if out_of(fix_r) == () {
        complete(#{ ok: false, stage: "review-fix", summary: "Batch review fix failed." });
    }
    let again = review_batch(rules, findings_schema, verdict_schema, repo, base_sha, forbid);
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
