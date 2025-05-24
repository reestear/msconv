#!/bin/bash

rm -rf logs/*
if [ $? -eq 0 ]; then
    echo "Logs cleared successfully."
else
    echo "Failed to clear logs."
fi
