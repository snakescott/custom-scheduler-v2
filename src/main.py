import time
import sys

def main():
    """
    Main function that prints a message every second.
    """
    try:
        while True:
            print("Running...", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
        sys.exit(0)

if __name__ == "__main__":
    main() 