#!/bin/bash
# Wrapper script to run the file sync watcher with correct Python path

cd /Users/danstern/Documents/big-brain/backend/scripts
export PYTHONPATH="/Users/danstern/Documents/big-brain/backend/scripts:$PYTHONPATH"

exec /usr/bin/python3 -m file_sync.watcher "$@"
