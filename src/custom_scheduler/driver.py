import os
import sys
import time

from kubernetes import client, config

from custom_scheduler.api_components import execute_scheduling_loop


def main():
    """
    Main function that prints status information every second.
    Includes timestamp, scheduler name, and namespace from environment variables.
    """
    scheduler_name = os.environ.get("SCHEDULER_NAME", "unknown")
    namespace = os.environ.get("POD_NAMESPACE", "unknown")
    
    config.load_incluster_config()
    api = client.CoreV1Api()

    try:
        # We need some way to drive the scheduling loop. One approach is 
        # to drive it from a watch, e.g. w.stream(v1.list_namespaced_pod, namespace),
        # but this schedules a single pod at a time, and for gang scheduling,
        # we need to schedule multiple pods at once.
        # So for now, we'll just run the scheduling loop every second. The main
        # tradeoff is that this loop is slower than the watch.
        # https://github.com/snakescott/custom-scheduler-v2/issues/2
        while True:
            execute_scheduling_loop(scheduler_name, namespace, api)
            # TODO(snakescott): consider appropriate sleep approach
            # https://github.com/snakescott/custom-scheduler-v2/issues/1
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main() 