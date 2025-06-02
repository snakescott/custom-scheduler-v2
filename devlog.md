This is a limited, toy kubernetes scheduler. It is basically a rebuild of https://github.com/snakescott/takehome-k8s with substantially more intention behind its design and implementation. This document is a development log.

**20250601 13:00-18:00 Pacific**

Roughly three and a half hours of dev in this window (longer session). Code implementation of gang scheduling based on pod annotations (`custom-scheduling.k8s.io/group-name` and `custom-scheduling.k8s.io/min-available`). In order to close [issues/14](https://github.com/snakescott/custom-scheduler-v2/issues/14) what remains is:

* Real world testing on minikube
* Potentially some cleanup and docs

**20250601 9:30-10:00 Pacific**

Short session, basically smoke testing basic [preemption](https://github.com/snakescott/custom-scheduler-v2/issues/13). Ran into interesting (retrospectively unsurprising) consistency issues with a 1s sleep between polling loops, so increased to 5s; some notes in [issues/1](https://github.com/snakescott/custom-scheduler-v2/issues/1).

Gang scheduling, testing, and cleanup are major remaining areas. There's been about 4h total of dev here so far.

**20250531 19:30-21:30 Pacific**

About 90m of dev time during this block. Full impl and test of basic scheduling and impl but not yet minikube testing of preemption. Found a few interesting bugs that were likely in the takehome-k8s version as well:

* Didn't correct check `schedulerName` matching -- and while test case covered this it was shadowed by lexographic ordering nuances. [d732e1b7ed8ad1baa4f33ce4e2d622436dac4f7d](https://github.com/snakescott/custom-scheduler-v2/commit/d732e1b7ed8ad1baa4f33ce4e2d622436dac4f7d)
* Longstanding bug in python kubernetes library that caused crash after binding due to incorrect reponse deserialization. Fixed in [8d474e3187a9a8953c44dce0c12925d03caf14f2](https://github.com/snakescott/custom-scheduler-v2/commit/8d474e3187a9a8953c44dce0c12925d03caf14f2).

I do miss having PRs (vs just commits) to refer back to, maybe I will enable branch protection...

**20250531 15:15-16:00 Pacific**

Cleanup, docs, and filing issues.

For now functionality is split up into three areas:
1) Core has no remote dependencies and should contain as much algorithmic complexity as possible
2) api_components houses functionality that calls the k8s API. Methods here typically recieve an api object as an argument, and mix read/writes to the k8s API with calls to methods in core.
3) driver has the outermost functionality, basically the main that is invoked on boot, creation of the k8s api object, and the polling/watching functionality that drives calls
to methods in api_components.



**20250531 9:00-11:00 Pacific**

Did about an hour of dev during this two hour window. Largely focused on on initial structure/scaffolding. Cursor did a lot of the work here, but there was a variety of bugfix/tweaks on top, including

* using python:3.12-slim instead of cursor suggested python:3.9-slim (picks up datetime.UTC)
* Reordering Containerfile to copy src after installing dependencies (better caching since src changes much more frequently than deps)
* Various refactors

Functionality at this point is the ability to poll for state from inside the container, as seen in
```
➜  custom-scheduler git:(main) ✗ kubectl logs -l app=custom-scheduler
Scheduler custom-scheduler, state:
State at 2025-05-31T22:34:27.595004+00:00
Namespace: default
Nodes: 1
Pods: 4
Scheduler custom-scheduler, state:
State at 2025-05-31T22:34:28.611293+00:00
Namespace: default
Nodes: 1
Pods: 4
```
