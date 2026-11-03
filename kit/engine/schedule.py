#!/usr/bin/env python3
"""The morning sweep in Windows Task Scheduler, for the current user only (no admin rights).
  schedule.py on [--at HH:MM]   register (or update) the daily task: 08:30 by default
  schedule.py off               remove it
  schedule.py status            registered or not, next and last run
  schedule.py xml [--at HH:MM]  print the task definition (nothing registered)
The task runs engine/sweep_daily.py with pythonw (no window), as soon as possible after a missed start (laptop
asleep at 08:30), on battery too, only with a network connection, and never twice at once.
"""
import datetime as dt, hashlib, os, pathlib, re, subprocess, sys, tempfile
from xml.sax.saxutils import escape
from _common import HOME, KIT, opt, die, today

def task_name():
    """One task per install: two folders never share a task."""
    return "foundry-kit daily sweep " + hashlib.sha1(str(HOME).lower().encode()).hexdigest()[:8]

def pythonw():
    exe = pathlib.Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return w if w.exists() else exe

def xml(at="08:30"):
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at): die("--at takes a time such as 08:30")
    start = dt.datetime.combine(today() + dt.timedelta(days=1), dt.time.fromisoformat(at)).isoformat(timespec="seconds")
    script = KIT / "engine" / "sweep_daily.py"
    e = lambda s: escape(str(s))
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Job search: reads the careers sites, the Job Alerts label and the job-search APIs every morning, and files new roles for /sweep to rank. Remove it with: python engine/schedule.py off</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{e(pythonw())}</Command>
      <Arguments>"{e(script)}"</Arguments>
      <WorkingDirectory>{e(HOME)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""

def schtasks(*args):
    if os.name != "nt": die("Task Scheduler is Windows only")
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, encoding="mbcs", errors="replace")

def on(args):
    at = opt(args, "--at", "08:30")
    body = xml(at)
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "task.xml"
        f.write_text(body, encoding="utf-16")
        p = schtasks("/Create", "/TN", task_name(), "/XML", str(f), "/F")
    if p.returncode != 0: print(f"COULDN'T REGISTER the morning sweep: {(p.stderr or p.stdout).strip()}"); return 1
    print(f"morning sweep: on, every day at {at} (or as soon as the computer is on and online after that)")
    return 0

def off(args):
    p = schtasks("/Delete", "/TN", task_name(), "/F")
    print("morning sweep: off" if p.returncode == 0 else "morning sweep: wasn't registered")
    return 0

def status(args):
    p = schtasks("/Query", "/TN", task_name(), "/V", "/FO", "LIST")
    if p.returncode != 0: print("morning sweep: off (python engine/schedule.py on)"); return 1
    info = {}
    for line in p.stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1); info.setdefault(k.strip(), v.strip())
    print(f"morning sweep: on; next run {info.get('Next Run Time', '?')}; last run {info.get('Last Run Time', '?')} "
          f"(result {info.get('Last Result', '?')})")
    return 0

def main(a):
    if not a: print(__doc__); return 1
    cmd, rest = a[0], a[1:]
    if cmd == "xml": print(xml(opt(rest, "--at", "08:30"))); return 0
    if cmd == "on": return on(rest)
    if cmd == "off": return off(rest)
    if cmd == "status": return status(rest)
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
