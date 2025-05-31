import os
import time
import sys
from datetime import datetime, timezone


def main():
    """
    Main function that prints status information every second.
    Includes timestamp, scheduler name, and namespace from environment variables.
    """
    scheduler_name = os.environ.get("SCHEDULER_NAME", "unknown")
    namespace = os.environ.get("POD_NAMESPACE", "unknown")
    
    try:
        while True:
            current_time = datetime.now(timezone.utc)
            print(
                f"Running at {current_time.isoformat()} "
                f"[scheduler={scheduler_name}, namespace={namespace}]",
                flush=True
            )
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main() 