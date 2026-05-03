#!/bin/bash
# 매일 새벽 4시에 cron 으로 실행. crontab -e 에 다음 라인 추가:
#   0 4 * * * /home/ubuntu/pharma-project/deploy/pg-backup.sh >> /home/ubuntu/backups/cron.log 2>&1
#
# DB 비밀번호는 ~/.pgpass 에 저장하면 -W 없이 자동 인증.
# .pgpass 형식 (퍼미션 600 필수):
#   localhost:5432:medisync:medisync:실제비번
#   chmod 600 ~/.pgpass

set -euo pipefail

BACKUP_DIR="/home/ubuntu/backups"
DB_NAME="medisync"
DB_USER="medisync"
DATE=$(date +%Y%m%d-%H%M)
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR"

OUT="$BACKUP_DIR/medisync-$DATE.sql.gz"
pg_dump -U "$DB_USER" -h localhost "$DB_NAME" | gzip > "$OUT"
echo "[$(date)] backup ok: $OUT ($(du -h "$OUT" | cut -f1))"

# 7일 이상 된 백업 정리
find "$BACKUP_DIR" -name "medisync-*.sql.gz" -mtime +$RETENTION_DAYS -delete -print
