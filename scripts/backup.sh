#!/bin/bash

################################################################################
# G-Track PostgreSQL Backup Script
# 
# This script performs daily backups of the G-Track database
# Setup: chmod +x backup.sh
# Schedule with cron: 0 2 * * * /home/ubuntu/g-track-backend/backup.sh
#
################################################################################

# Configuration
BACKUP_DIR="/backups/gtrack"
LOG_FILE="/var/log/gtrack/backup.log"
DB_NAME="gtrack_db"
DB_USER="gtrack_user"
DB_HOST="localhost"
DB_PORT="5432"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.sql.gz"

# Email configuration (optional)
EMAIL="admin@example.com"
SUBJECT="G-Track Database Backup Report - $TIMESTAMP"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

################################################################################
# Functions
################################################################################

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error_exit() {
    log "${RED}ERROR: $1${NC}"
    send_email_alert "FAILED" "$1"
    exit 1
}

send_email_alert() {
    local status=$1
    local message=$2
    
    if command -v mail &> /dev/null; then
        echo -e "Backup Status: $status\n\nMessage: $message" | \
        mail -s "$SUBJECT" "$EMAIL"
    fi
}

################################################################################
# Main Script
################################################################################

log "=========================================="
log "Starting G-Track Database Backup"
log "=========================================="

# Create backup directory if it doesn't exist
if [ ! -d "$BACKUP_DIR" ]; then
    log "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR" || error_exit "Failed to create $BACKUP_DIR"
fi

# Check if PostgreSQL is running
if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" &> /dev/null; then
    error_exit "PostgreSQL server is not running or not accessible"
fi

# Perform backup
log "Backing up database: $DB_NAME"
log "Backup file: $BACKUP_FILE"

if PGPASSWORD="$DB_PASSWORD" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --no-password \
    --format=plain \
    --verbose \
    2>> "$LOG_FILE" | gzip > "$BACKUP_FILE"; then
    
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log "${GREEN}✓ Backup completed successfully${NC}"
    log "Backup size: $BACKUP_SIZE"
else
    error_exit "Backup failed - see log for details"
fi

# Verify backup file
if [ ! -f "$BACKUP_FILE" ]; then
    error_exit "Backup file was not created"
fi

if [ ! -s "$BACKUP_FILE" ]; then
    error_exit "Backup file is empty"
fi

log "Verifying backup integrity..."
if gzip -t "$BACKUP_FILE" 2>> "$LOG_FILE"; then
    log "${GREEN}✓ Backup verification passed${NC}"
else
    error_exit "Backup file is corrupted"
fi

# Remove old backups (keep last 30 days)
log "Cleaning up backups older than $RETENTION_DAYS days"
OLD_BACKUPS=$(find "$BACKUP_DIR" -name "backup_*.sql.gz" -mtime +$RETENTION_DAYS)

if [ -z "$OLD_BACKUPS" ]; then
    log "No old backups to remove"
else
    echo "$OLD_BACKUPS" | while read OLD_FILE; do
        log "Removing: $OLD_FILE"
        rm -f "$OLD_FILE"
    done
fi

# Summary statistics
TOTAL_BACKUPS=$(find "$BACKUP_DIR" -name "backup_*.sql.gz" | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)

log "=========================================="
log "Backup Summary"
log "=========================================="
log "Total backups stored: $TOTAL_BACKUPS"
log "Total backup directory size: $TOTAL_SIZE"
log "Backup retention period: $RETENTION_DAYS days"
log "Latest backup: $BACKUP_FILE ($BACKUP_SIZE)"
log "=========================================="

# Optional: Upload to cloud storage
# Uncomment and configure for AWS S3, Google Cloud, or other services
# aws s3 cp "$BACKUP_FILE" s3://your-bucket/gtrack-backups/

log "${GREEN}✓ Backup process completed successfully${NC}"

# Send success email
send_email_alert "SUCCESS" "Database backup completed successfully.\n\nFile: $BACKUP_FILE\nSize: $BACKUP_SIZE\nTotal backups: $TOTAL_BACKUPS"

exit 0
