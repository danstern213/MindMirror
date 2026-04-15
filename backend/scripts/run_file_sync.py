#!/usr/bin/env python3
"""Entry point for the file sync watcher."""

import sys
import os

# Add the scripts directory to the path
scripts_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, scripts_dir)

# Now import and run the watcher
from file_sync.watcher import main

if __name__ == "__main__":
    main()
