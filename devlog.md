This is a limited, toy kubernetes scheduler. It is basically a rebuild of https://github.com/snakescott/takehome-k8s with substantially more intention behind its design and implementation. This document is a development log.

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
