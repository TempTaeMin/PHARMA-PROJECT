# 1단계: Vite 빌드
FROM node:20-alpine AS builder
WORKDIR /app

# 빌드 시 주입될 API URL (docker-compose build args 로 전달)
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# 2단계: nginx 정적 서빙
FROM nginx:alpine

# SPA fallback (try_files /index.html)
RUN rm /etc/nginx/conf.d/default.conf
COPY <<'EOF' /etc/nginx/conf.d/default.conf
server {
  listen 80;
  server_name _;
  root /usr/share/nginx/html;
  index index.html;

  # 정적 자원 캐시
  location ~* \.(js|css|png|jpg|jpeg|gif|svg|woff2?|ttf)$ {
    expires 30d;
    add_header Cache-Control "public, max-age=2592000";
  }

  # SPA — 라우트 fallback
  location / {
    try_files $uri /index.html;
  }
}
EOF

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
