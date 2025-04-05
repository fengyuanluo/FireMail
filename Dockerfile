# --- Builder Stage ---
FROM node:22-alpine AS builder

# Copy application files
COPY . /app

# Enable pnpm
RUN corepack enable pnpm

# Install and build frontend
WORKDIR /app/frontend
RUN pnpm install
RUN pnpm install dayjs # 漏了一个依赖
RUN pnpm build

# --- Final Stage ---
FROM alpine

# Environment variables
ENV HOST=0.0.0.0 \
    FLASK_PORT=5000 \
    WS_PORT=8765 \
    FRONTEND_PORT=3000 \
    TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JWT_SECRET_KEY=huohuo_email_secret_key

# Install Python
RUN apk add --no-cache py3-pip caddy bash

# Copy necessary files from builder stage
COPY --from=builder /app /app

# Set working directory
WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

# Expose port
EXPOSE 80

# Startup command
RUN chmod +x /app/docker-entrypoint.sh
ENTRYPOINT ["/app/docker-entrypoint.sh"]
