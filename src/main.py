import sys
import time
from kubernetes import client, config


def main():
    """
    Main function that prints a message every second.
    """
    config.load_incluster_config()
    v1=client.CoreV1Api()
    try:
        while True:
            print("Running...", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
        sys.exit(0)

if __name__ == "__main__":
    main() 