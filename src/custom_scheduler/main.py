import os
import sys
import time

from kubernetes import client, config

from .k8s import execute_scheduling_loop


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
        while True:
            execute_scheduling_loop(scheduler_name, namespace, api)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main() 