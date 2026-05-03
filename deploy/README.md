# 배포 템플릿

가비아 g1 / Ubuntu 22.04 / Postgres 16 / nginx + Let's Encrypt 기준 배포 자료.

## 파일

| 파일 | 위치 | 역할 |
|------|------|------|
| `medisync.service` | `/etc/systemd/system/medisync.service` | FastAPI uvicorn 데몬 |
| `nginx-medisync.conf` | `/etc/nginx/sites-available/medisync` | 리버스 프록시 + SPA |
| `pg-backup.sh` | `/home/ubuntu/pharma-project/deploy/pg-backup.sh` | 매일 PG 덤프 cron |

## 1회성 배포 절차 요약

```bash
# 0. 가비아 콘솔에서 g1 인스턴스 + 도메인 발급, 보안그룹 22/80/443 오픈

# 1. 시스템 패키지
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.10 python3.10-venv git nginx \
  postgresql-16 postgresql-contrib build-essential libpq-dev

# 2. Postgres DB/유저
sudo -u postgres psql <<EOF
CREATE USER medisync WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE medisync OWNER medisync;
EOF

# 3. 코드 + venv
cd /home/ubuntu
git clone <repo> pharma-project
cd pharma-project/backend
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
playwright install-deps

# 4. .env 작성 (.env.example 복사 후 값 채움)
cp .env.example .env
vim .env

# 5. DB 스키마 + 시드
alembic upgrade head
python scripts/seed_hospitals.py

# 6. systemd 등록
sudo cp ../deploy/medisync.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now medisync

# 7. 프런트 빌드 (로컬에서)
cd frontend && echo "VITE_API_URL=https://your-domain.com" > .env.production
npm run build
scp -r dist ubuntu@<서버IP>:/home/ubuntu/pharma-project/frontend/

# 8. nginx
sudo cp /home/ubuntu/pharma-project/deploy/nginx-medisync.conf /etc/nginx/sites-available/medisync
sudo sed -i 's/your-domain.com/실제도메인/g' /etc/nginx/sites-available/medisync
sudo ln -sf /etc/nginx/sites-available/medisync /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# 9. HTTPS
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# 10. 백업 cron
chmod +x /home/ubuntu/pharma-project/deploy/pg-backup.sh
echo "localhost:5432:medisync:medisync:실제비번" > ~/.pgpass
chmod 600 ~/.pgpass
crontab -e   # → "0 4 * * * /home/ubuntu/pharma-project/deploy/pg-backup.sh >> /home/ubuntu/backups/cron.log 2>&1"
```

## 배포 후 코드 업데이트 (재배포)

```bash
# 백엔드 코드 변경
ssh ubuntu@server
cd ~/pharma-project
git pull
cd backend
source .venv/bin/activate
pip install -r requirements.txt    # 의존성 변경 시
alembic upgrade head                # 새 마이그레이션 있으면
sudo systemctl restart medisync

# 프런트 변경 (로컬에서 빌드 후 scp)
cd frontend && npm run build
scp -r dist ubuntu@server:/home/ubuntu/pharma-project/frontend/
# nginx 는 정적 파일이라 reload 불필요
```

## 로그 / 트러블슈팅

```bash
# 백엔드 로그
journalctl -u medisync -f

# nginx 에러
sudo tail -f /var/log/nginx/error.log

# Postgres 로그
sudo tail -f /var/log/postgresql/postgresql-16-main.log

# 서비스 상태
systemctl status medisync nginx postgresql
```
