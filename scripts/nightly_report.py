#!/usr/bin/env python3
import datetime

def main():
    d = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Nightly run at {d} - all systems nominal.")

if __name__ == "__main__":
    main()
