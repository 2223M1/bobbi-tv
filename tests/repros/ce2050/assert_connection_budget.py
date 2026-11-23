#!/usr/bin/env python3
"""Turn the real localhost dual-address observation into an explicit regression gate.
A missing dual-stack fixture is INCONCLUSIVE, never a product pass.
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--observation",type=Path,help="Evaluate an existing immutable observation instead of rerunning sockets")
    p.add_argument("--budget-tolerance",type=float,default=.4)
    p.add_argument("--max-back-seconds",type=float,default=.5)
    a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    observation=a.observation or a.output.with_name(a.output.stem+"-observation.json")
    if a.observation is None:
        cmd=[sys.executable,str(Path(__file__).with_name("probe_multihost_connect.py")),
             "--repo",str(a.repo.resolve()),"--output",str(observation.resolve())]
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1")
        try:
            completed=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=15)
            if completed.returncode:
                r={"schema":1,"status":"INCONCLUSIVE","reason":"Fixture or probe could not complete",
                   "returncode":completed.returncode,"stderr":completed.stderr[-4000:]}
                a.output.write_text(json.dumps(r,indent=2)+"\n")
                print(json.dumps(r));return 2
        except subprocess.TimeoutExpired:
            r={"schema":1,"status":"FAIL","reason":"Probe exceeded 15 seconds",
               "scope":"Only this local fixture subprocess was terminated"}
            a.output.write_text(json.dumps(r,indent=2)+"\n");print(json.dumps(r));return 1
    r=json.loads(observation.read_text())
    checks={
        "shared_total_budget":r["elapsed_seconds"] <= r["request_budget_seconds"]+a.budget_tolerance,
        "back_response":r["seconds_after_back"] <= a.max_back_seconds,
        "zero_workers_at_return":not r["workers_at_return"],
        "real_dns_and_connect":r["simulated_getaddrinfo"] is False and r["simulated_connect"] is False,
    }
    report={"schema":1,"status":"PASS" if all(checks.values()) else "FAIL",
            "observation":observation.name,"checks":checks,
            "observed_elapsed_seconds":r["elapsed_seconds"],
            "observed_seconds_after_back":r["seconds_after_back"],
            "absolute_budget_seconds":r["request_budget_seconds"],
            "budget_tolerance_seconds":a.budget_tolerance,"max_back_seconds":a.max_back_seconds,
            "threshold_origin":"Reviewer proposed regression criteria, not a claim of device response certification"}
    a.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))
    return 0 if report["status"]=="PASS" else 1
if __name__=="__main__":
    raise SystemExit(main())

