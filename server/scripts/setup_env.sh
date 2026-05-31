#!/bin/bash
# PAGE_TOKEN_SECRET 环境变量配置脚本 (Linux/macOS)
# 用法: source scripts/setup_env.sh  或  bash scripts/setup_env.sh
# 注意: 必须使用 source 执行才能在当前 shell 中设置环境变量

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
GRAY='\033[0;90m'
NC='\033[0m'

echo -e "${CYAN}========================================"
echo -e "  Delta Sharing - PAGE_TOKEN_SECRET 配置"
echo -e "========================================${NC}"
echo ""

# 生成安全的随机密钥 (32字节 = 64位十六进制字符)
SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || python -c "import secrets; print(secrets.token_hex(32))")

if [ -z "$SECRET" ]; then
    echo -e "${RED}[ERROR] 无法生成随机密钥。请确保 openssl 或 python3 已安装。${NC}"
    exit 1
fi

echo -e "${GREEN}[OK] 已生成安全的随机密钥${NC}"
echo ""

# 检测当前是否被 source 执行
if [ "${BASH_SOURCE[0]}" != "${0}" ]; then
    # 被 source 执行，可以设置环境变量
    export PAGE_TOKEN_SECRET="$SECRET"
    echo -e "${YELLOW}[当前会话] 环境变量已设置:${NC}"
    echo -e "  export PAGE_TOKEN_SECRET=${MAGENTA}${SECRET}${NC}"
else
    # 被直接执行，提供手动设置命令
    echo -e "${YELLOW}[注意] 请使用 'source' 执行此脚本以在当前 shell 中设置环境变量:${NC}"
    echo -e "  ${MAGENTA}source scripts/setup_env.sh${NC}"
    echo ""
    echo -e "${YELLOW}或手动执行:${NC}"
    echo -e "  export PAGE_TOKEN_SECRET=${MAGENTA}${SECRET}${NC}"
    echo ""
fi

echo ""
echo -e "${CYAN}========================================"
echo -e "  永久配置方法 (请选择一种):"
echo -e "========================================${NC}"
echo ""

echo -e "${YELLOW}[方法1] ~/.bashrc 或 ~/.zshrc (推荐):${NC}"
echo -e "${GRAY}  将以下行添加到 ~/.bashrc 或 ~/.zshrc:${NC}"
echo -e "  ${MAGENTA}export PAGE_TOKEN_SECRET=${SECRET}${NC}"
echo ""

echo -e "${YELLOW}[方法2] /etc/environment (系统级):${NC}"
echo -e "${GRAY}  sudo 编辑 /etc/environment，添加:${NC}"
echo -e "  ${MAGENTA}PAGE_TOKEN_SECRET=${SECRET}${NC}"
echo ""

echo -e "${YELLOW}[方法3] systemd service (如果使用 systemd 管理服务):${NC}"
echo -e "${GRAY}  在 service 文件中添加:${NC}"
echo -e "  ${MAGENTA}Environment=PAGE_TOKEN_SECRET=${SECRET}${NC}"
echo ""

echo -e "${YELLOW}[方法4] .env.local 文件 (项目级):${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../server/.env.local"

if [ ! -f "$ENV_FILE" ]; then
    echo "PAGE_TOKEN_SECRET=$SECRET" > "$ENV_FILE"
    echo -e "  ${GREEN}已创建文件: $ENV_FILE${NC}"
elif grep -q "PAGE_TOKEN_SECRET=" "$ENV_FILE" 2>/dev/null; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/PAGE_TOKEN_SECRET=.*/PAGE_TOKEN_SECRET=$SECRET/" "$ENV_FILE"
    else
        sed -i "s/PAGE_TOKEN_SECRET=.*/PAGE_TOKEN_SECRET=$SECRET/" "$ENV_FILE"
    fi
    echo -e "  ${GREEN}已更新文件: $ENV_FILE${NC}"
else
    echo "" >> "$ENV_FILE"
    echo "PAGE_TOKEN_SECRET=$SECRET" >> "$ENV_FILE"
    echo -e "  ${GREEN}已更新文件: $ENV_FILE${NC}"
fi
echo ""

echo -e "${CYAN}========================================"
echo -e "  验证:"
echo -e "========================================${NC}"
if [ -n "${PAGE_TOKEN_SECRET}" ]; then
    echo -e "  当前值: ${MAGENTA}${PAGE_TOKEN_SECRET}${NC}"
else
    echo -e "  ${YELLOW}请执行: source scripts/setup_env.sh${NC}"
fi
echo ""

echo -e "${GREEN}[DONE] 配置完成!${NC}"
