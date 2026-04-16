#!/bin/bash
# PropGuard AI — Database Migration
# Usage:
#   ./scripts/db-migrate.sh new "add_orders_table"   # Create new migration
#   ./scripts/db-migrate.sh push                       # Apply to Supabase
#   ./scripts/db-migrate.sh status                     # Check migration status
#   ./scripts/db-migrate.sh diff                       # Show pending changes

set -e
cd "$(dirname "$0")/.."

case "$1" in
  new)
    NAME="${2:-unnamed}"
    TIMESTAMP=$(date +%Y%m%d%H%M%S)
    FILE="supabase/migrations/${TIMESTAMP}_${NAME}.sql"
    echo "-- Migration: ${TIMESTAMP}_${NAME}" > "$FILE"
    echo "-- Created: $(date)" >> "$FILE"
    echo "" >> "$FILE"
    echo "Created: $FILE"
    echo "Edit the file, then run: ./scripts/db-migrate.sh push"
    ;;
  push)
    echo "Applying migrations to Supabase..."
    supabase db push --linked
    echo "Done."
    ;;
  status)
    supabase migration list --linked
    ;;
  diff)
    supabase db diff --linked
    ;;
  *)
    echo "Usage: $0 {new|push|status|diff} [name]"
    echo ""
    echo "Examples:"
    echo "  $0 new add_orders_table    # Create migration file"
    echo "  $0 push                     # Apply to production"
    echo "  $0 status                   # List applied migrations"
    ;;
esac
