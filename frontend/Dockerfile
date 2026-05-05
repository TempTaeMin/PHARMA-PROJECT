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

# SPA fallback 설정 — nginx.conf 별도 파일에서 (legacy builder heredoc 미지원 회피)
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
