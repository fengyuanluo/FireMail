#!/bin/bash
set -e

# 创建必要的数据目录
mkdir -p /app/backend/data

# 设置环境变量
export HOST="${HOST:-0.0.0.0}"
export FLASK_PORT="${FLASK_PORT:-5000}"
export WS_PORT="${WS_PORT:-8765}"
export FRONTEND_PORT="${FRONTEND_PORT:-3000}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-huohuo_email_secret_key}"
export TZ="${TZ:-Asia/Shanghai}"

echo "花火邮箱助手正在启动..."
echo "后端API地址: http://$HOST:$FLASK_PORT"
echo "WebSocket服务地址: ws://$HOST:$WS_PORT"
echo "前端服务地址: http://$HOST:80"
echo "注册功能: 默认开启，第一个注册的用户为管理员，之后管理员可在系统设置中控制"

# 创建前端环境变量文件
mkdir -p /app/frontend/dist
cat > /app/frontend/dist/env-config.js << EOF
// 环境配置
window.API_URL = '/api';  // 使用相对路径
window.WS_URL = '/ws';    // 使用相对路径
console.log('env-config.js已加载，API_URL:', window.API_URL, 'WS_URL:', window.WS_URL);
EOF

echo "已创建环境配置文件，内容如下:"
cat /app/frontend/dist/env-config.js

# 确保Caddy日志目录存在
mkdir -p /var/log/caddy

# 检查Caddy配置文件
echo "检查Caddy配置..."
caddy validate --config /app/Caddyfile || (echo "Caddy配置错误" && exit 1)

# 启动Nginx服务
echo "启动Caddy服务..."
caddy run --config /app/Caddyfile &

# 启动Python后端应用
cd /app
echo "启动后端服务..."
exec python3 ./backend/app.py --host "$HOST" --port "$FLASK_PORT" --ws-port "$WS_PORT" 
