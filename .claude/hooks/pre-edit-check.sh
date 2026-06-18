#!/bin/bash
# Pre-edit hook: warns before editing API files without process verification reminder
# Triggered before file edits on prana-api files

FILE="$1"

if [[ "$FILE" == *"prana-api"* ]]; then
  echo "⚠️  PRANA API FILE EDIT"
  echo "After this edit, if testing:"
  echo "  1. netstat -ano | findstr ':8000'  → must see exactly 1 PID"
  echo "  2. Kill all PIDs on :8000"
  echo "  3. Start fresh: python -m uvicorn main:app --port 8000"
  echo "  4. Confirm 1 PID before testing"
fi

if [[ "$FILE" == *"prana-db/schema.sql"* ]]; then
  echo "⚠️  SCHEMA EDIT — Remember to:"
  echo "  1. Create a migration in prana-db/migrations/"
  echo "  2. Never DROP COLUMN on live table — additive only"
  echo "  3. Update seeds if new NOT NULL columns added"
fi
