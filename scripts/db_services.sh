#!/bin/bash

# MySQL和Redis管理脚本
# 此脚本用于管理MySQL和Redis服务，包括安装、配置、启动、停止等功能

set -e  # 遇到错误时退出

# 输出颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # 无颜色

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVER_DIR="$PROJECT_ROOT/server"
DATA_DIR="$PROJECT_ROOT/data"
MYSQL_DATA_DIR="$DATA_DIR/mysql"
REDIS_DATA_DIR="$DATA_DIR/redis"
MYSQL_CONFIG_FILE="$DATA_DIR/mysql/mysql.cnf"
REDIS_CONFIG_FILE="$DATA_DIR/redis/redis.conf"

# 打印彩色输出的函数
log_info() { echo -e "${GREEN}[信息]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
log_error() { echo -e "${RED}[错误]${NC} $1"; }
log_step() { echo -e "${BLUE}[步骤]${NC} $1"; }

# 加载环境变量
load_env() {
    if [ -f "$PROJECT_ROOT/.env" ]; then
        export $(cat "$PROJECT_ROOT/.env" | grep -v '^#' | grep -v '^$' | xargs)
    else
        log_error ".env文件不存在，请先创建.env文件"
        exit 1
    fi
}

# 检查服务是否已安装
check_mysql_installed() { command -v mysql &> /dev/null; }
check_redis_installed() { command -v redis-server &> /dev/null; }

# 处理配置文件中的环境变量
create_configs() {
    log_step "处理配置文件..."
    
    # 加载环境变量
    load_env
    
    # 确保目录存在
    mkdir -p "$(dirname "$MYSQL_CONFIG_FILE")" "$(dirname "$REDIS_CONFIG_FILE")"
    mkdir -p "$MYSQL_DATA_DIR" "$REDIS_DATA_DIR"
    
    # 检查配置文件是否存在
    if [ ! -f "$MYSQL_CONFIG_FILE" ]; then
        log_error "MySQL配置文件不存在: $MYSQL_CONFIG_FILE"
        exit 1
    fi
    
    if [ ! -f "$REDIS_CONFIG_FILE" ]; then
        log_error "Redis配置文件不存在: $REDIS_CONFIG_FILE"
        exit 1
    fi
    
    # 创建临时配置文件，处理环境变量替换
    MYSQL_TEMP_CONFIG="/tmp/mysql_$(date +%s).cnf"
    REDIS_TEMP_CONFIG="/tmp/redis_$(date +%s).conf"
    
    # 使用bash的参数扩展来处理环境变量替换
    # 这样可以正确处理 ${VAR:-default} 语法
    log_info "处理MySQL配置文件中的环境变量..."
    
    # 读取MySQL配置文件并进行环境变量替换
    while IFS= read -r line || [[ -n "$line" ]]; do
        # 使用eval来处理环境变量替换，但要小心安全性
        if [[ "$line" =~ \$\{[^}]+\} ]]; then
            # 安全地处理环境变量替换
            eval "echo \"$line\"" 2>/dev/null || echo "$line"
        else
            echo "$line"
        fi
    done < "$MYSQL_CONFIG_FILE" > "$MYSQL_TEMP_CONFIG"
    
    log_info "处理Redis配置文件中的环境变量..."
    
    # 读取Redis配置文件并进行环境变量替换
    while IFS= read -r line || [[ -n "$line" ]]; do
        # 使用eval来处理环境变量替换，但要小心安全性
        if [[ "$line" =~ \$\{[^}]+\} ]]; then
            # 安全地处理环境变量替换
            eval "echo \"$line\"" 2>/dev/null || echo "$line"
        else
            echo "$line"
        fi
    done < "$REDIS_CONFIG_FILE" > "$REDIS_TEMP_CONFIG"
    
    # 验证配置文件格式
    if [ -s "$MYSQL_TEMP_CONFIG" ] && [ -s "$REDIS_TEMP_CONFIG" ]; then
        log_info "配置文件处理完成"
        log_info "MySQL临时配置: $MYSQL_TEMP_CONFIG"
        log_info "Redis临时配置: $REDIS_TEMP_CONFIG"
        
        # 显示处理后的配置文件大小
        local mysql_size=$(wc -l < "$MYSQL_TEMP_CONFIG")
        local redis_size=$(wc -l < "$REDIS_TEMP_CONFIG")
        log_info "MySQL配置文件: $mysql_size 行"
        log_info "Redis配置文件: $redis_size 行"
    else
        log_error "配置文件处理失败"
        rm -f "$MYSQL_TEMP_CONFIG" "$REDIS_TEMP_CONFIG"
        exit 1
    fi
}

# 安装服务
install_services() {
    log_step "安装MySQL和Redis..."
    
    # 根据操作系统类型安装
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            log_info "使用Homebrew安装服务..."
            
            if ! check_mysql_installed; then
                log_info "安装MySQL..."
                if brew install mysql; then
                    log_info "MySQL安装成功"
                    # 启动MySQL服务以便后续配置
                    brew services start mysql || log_warn "MySQL服务启动失败，请手动启动"
                else
                    log_error "MySQL安装失败"
                    exit 1
                fi
            else
                log_info "MySQL已安装"
            fi
            
            if ! check_redis_installed; then
                log_info "安装Redis..."
                if brew install redis; then
                    log_info "Redis安装成功"
                    # 启动Redis服务
                    brew services start redis || log_warn "Redis服务启动失败，请手动启动"
                else
                    log_error "Redis安装失败"
                    exit 1
                fi
            else
                log_info "Redis已安装"
            fi
        else
            log_error "未找到Homebrew，请先安装Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v apt-get &> /dev/null; then
            log_info "使用apt-get安装服务..."
            
            # 更新包列表
            if ! apt-get update; then
                log_error "更新包列表失败"
                exit 1
            fi
            
            if ! check_mysql_installed; then
                log_info "安装MySQL..."
                if apt-get install -y mysql-server; then
                    log_info "MySQL安装成功"
                    # 启动MySQL服务
                    systemctl start mysql || service mysql start || log_warn "MySQL服务启动失败"
                    systemctl enable mysql || log_warn "MySQL服务自启动设置失败"
                else
                    log_error "MySQL安装失败"
                    exit 1
                fi
            else
                log_info "MySQL已安装"
            fi
            
            if ! check_redis_installed; then
                log_info "安装Redis..."
                if apt-get install -y redis-server; then
                    log_info "Redis安装成功"
                    # 启动Redis服务
                    systemctl start redis-server || service redis-server start || log_warn "Redis服务启动失败"
                    systemctl enable redis-server || log_warn "Redis服务自启动设置失败"
                else
                    log_error "Redis安装失败"
                    exit 1
                fi
            else
                log_info "Redis已安装"
            fi
        elif command -v yum &> /dev/null; then
            log_info "使用yum安装服务..."
            
            if ! check_mysql_installed; then
                log_info "安装MySQL..."
                if yum install -y mysql-server; then
                    log_info "MySQL安装成功"
                    systemctl start mysqld || service mysqld start || log_warn "MySQL服务启动失败"
                    systemctl enable mysqld || log_warn "MySQL服务自启动设置失败"
                else
                    log_error "MySQL安装失败"
                    exit 1
                fi
            else
                log_info "MySQL已安装"
            fi
            
            if ! check_redis_installed; then
                log_info "安装Redis..."
                if yum install -y redis; then
                    log_info "Redis安装成功"
                    systemctl start redis || service redis start || log_warn "Redis服务启动失败"
                    systemctl enable redis || log_warn "Redis服务自启动设置失败"
                else
                    log_error "Redis安装失败"
                    exit 1
                fi
            else
                log_info "Redis已安装"
            fi
        elif command -v dnf &> /dev/null; then
            log_info "使用dnf安装服务..."
            
            if ! check_mysql_installed; then
                log_info "安装MySQL..."
                if dnf install -y mysql-server; then
                    log_info "MySQL安装成功"
                    systemctl start mysqld || log_warn "MySQL服务启动失败"
                    systemctl enable mysqld || log_warn "MySQL服务自启动设置失败"
                else
                    log_error "MySQL安装失败"
                    exit 1
                fi
            else
                log_info "MySQL已安装"
            fi
            
            if ! check_redis_installed; then
                log_info "安装Redis..."
                if dnf install -y redis; then
                    log_info "Redis安装成功"
                    systemctl start redis || log_warn "Redis服务启动失败"
                    systemctl enable redis || log_warn "Redis服务自启动设置失败"
                else
                    log_error "Redis安装失败"
                    exit 1
                fi
            else
                log_info "Redis已安装"
            fi
        else
            log_error "不支持的Linux发行版，请手动安装MySQL和Redis"
            exit 1
        fi
    else
        log_error "不支持的操作系统: $OSTYPE"
        exit 1
    fi
    
    # 验证安装结果
    if check_mysql_installed && check_redis_installed; then
        log_info "MySQL和Redis安装完成"
    else
        log_error "安装验证失败，请检查安装过程"
        exit 1
    fi
}

# 启动服务
start_services() {
    log_step "启动服务..."
    
    # 首先处理配置文件
    create_configs
    
    # 启动MySQL
    if check_mysql_installed; then
        if ! pgrep -x "mysqld" > /dev/null; then
            log_info "启动MySQL服务..."
            if [[ "$OSTYPE" == "darwin"* ]]; then
                # macOS 优先使用 brew services，失败时尝试 mysql.server 或直接启动 mysqld
                BREW_OUT=$(brew services start mysql 2>&1 || true)
                if ! pgrep -x "mysqld" > /dev/null; then
                    log_warn "brew services 启动MySQL失败或未生效: $BREW_OUT"
                    if command -v mysql.server &> /dev/null; then
                        log_info "尝试使用 mysql.server 启动 MySQL..."
                        MYSQL_SERVER_OUT=$(mysql.server start 2>&1 || true)
                        if ! pgrep -x "mysqld" > /dev/null; then
                            log_warn "mysql.server 启动MySQL失败或未生效: $MYSQL_SERVER_OUT"
                            if command -v mysqld &> /dev/null && [ -f "$MYSQL_TEMP_CONFIG" ]; then
                                log_info "尝试使用临时配置文件直接启动 mysqld..."
                                nohup mysqld --defaults-file="$MYSQL_TEMP_CONFIG" >/dev/null 2>&1 &
                                sleep 3
                            else
                                log_warn "未找到 mysqld 可执行文件或配置文件，可能仅安装了客户端"
                            fi
                        fi
                    else
                        # 没有 mysql.server 时，直接尝试 mysqld
                        if command -v mysqld &> /dev/null && [ -f "$MYSQL_TEMP_CONFIG" ]; then
                            log_info "尝试使用临时配置文件直接启动 mysqld..."
                            nohup mysqld --defaults-file="$MYSQL_TEMP_CONFIG" >/dev/null 2>&1 &
                            sleep 3
                        fi
                    fi
                fi
            elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
                # Linux 环境：systemctl 不可用或未启用时，尝试其他方式
                if command -v systemctl &> /dev/null; then
                    MYSQL_START_OUT=$(systemctl start mysql 2>&1 || systemctl start mysqld 2>&1 || true)
                    if ! pgrep -x "mysqld" > /dev/null; then
                        log_warn "systemctl 启动MySQL失败或未生效: $MYSQL_START_OUT"
                        if echo "$MYSQL_START_OUT" | grep -qi 'System has not been booted with systemd'; then
                            log_warn "当前环境未使用systemd，改用其他方式启动MySQL"
                        fi
                        if command -v service &> /dev/null; then
                            SERVICE_OUT=$(service mysql start 2>&1 || service mysqld start 2>&1 || true)
                            if ! pgrep -x "mysqld" > /dev/null; then
                                log_warn "service 启动MySQL失败或未生效: $SERVICE_OUT"
                            fi
                        fi
                    fi
                elif command -v service &> /dev/null; then
                    SERVICE_OUT=$(service mysql start 2>&1 || service mysqld start 2>&1 || true)
                    if ! pgrep -x "mysqld" > /dev/null; then
                        log_warn "service 启动MySQL失败或未生效: $SERVICE_OUT"
                    fi
                fi
                
                # 直接启动 mysqld 作为兜底
                if ! pgrep -x "mysqld" > /dev/null; then
                    if command -v mysqld &> /dev/null && [ -f "$MYSQL_TEMP_CONFIG" ]; then
                        log_info "尝试使用临时配置文件直接启动 mysqld..."
                        nohup mysqld --defaults-file="$MYSQL_TEMP_CONFIG" >/dev/null 2>&1 &
                        sleep 3
                    else
                        log_warn "未找到 mysqld 可执行文件或配置文件，可能仅安装了客户端"
                    fi
                fi
            fi
            
            # 等待MySQL启动完成
            local wait_count=0
            while [ $wait_count -lt 30 ] && ! pgrep -x "mysqld" > /dev/null; do
                sleep 1
                ((wait_count++))
            done
            
            if pgrep -x "mysqld" > /dev/null; then
                log_info "MySQL服务已启动"
            else
                log_warn "MySQL服务启动尝试后仍未运行，请检查安装与配置"
            fi
        else
            log_info "MySQL服务已在运行"
        fi
    else
        log_warn "MySQL未安装，无法启动"
    fi
    
    # 启动Redis
    if check_redis_installed; then
        if ! pgrep -x "redis-server" > /dev/null; then
            log_info "启动Redis服务..."
            if [[ "$OSTYPE" == "darwin"* ]]; then
                REDIS_BREW_OUT=$(brew services start redis 2>&1 || true)
                if ! pgrep -x "redis-server" > /dev/null; then
                    log_warn "brew services 启动Redis失败或未生效: $REDIS_BREW_OUT"
                    if command -v redis-server &> /dev/null && [ -f "$REDIS_TEMP_CONFIG" ]; then
                        log_info "尝试使用临时配置文件直接启动 redis-server..."
                        nohup redis-server "$REDIS_TEMP_CONFIG" >/dev/null 2>&1 &
                        sleep 2
                    else
                        log_warn "未找到 redis-server 可执行文件或配置文件"
                    fi
                fi
            elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
                if command -v systemctl &> /dev/null; then
                    REDIS_START_OUT=$(systemctl start redis 2>&1 || systemctl start redis-server 2>&1 || true)
                    if ! pgrep -x "redis-server" > /dev/null; then
                        log_warn "systemctl 启动Redis失败或未生效: $REDIS_START_OUT"
                        if echo "$REDIS_START_OUT" | grep -qi 'System has not been booted with systemd'; then
                            log_warn "当前环境未使用systemd，改用其他方式启动Redis"
                        fi
                        if command -v service &> /dev/null; then
                            REDIS_SERVICE_OUT=$(service redis-server start 2>&1 || service redis start 2>&1 || true)
                            if ! pgrep -x "redis-server" > /dev/null; then
                                log_warn "service 启动Redis失败或未生效: $REDIS_SERVICE_OUT"
                            fi
                        fi
                    fi
                elif command -v service &> /dev/null; then
                    REDIS_SERVICE_OUT=$(service redis-server start 2>&1 || service redis start 2>&1 || true)
                    if ! pgrep -x "redis-server" > /dev/null; then
                        log_warn "service 启动Redis失败或未生效: $REDIS_SERVICE_OUT"
                    fi
                fi
                
                # 兜底：直接启动 redis-server
                if ! pgrep -x "redis-server" > /dev/null; then
                    if command -v redis-server &> /dev/null && [ -f "$REDIS_TEMP_CONFIG" ]; then
                        log_info "尝试使用临时配置文件直接启动 redis-server..."
                        nohup redis-server "$REDIS_TEMP_CONFIG" >/dev/null 2>&1 &
                        sleep 2
                    else
                        log_warn "未找到 redis-server 可执行文件或配置文件"
                    fi
                fi
            fi
            
            # 等待Redis启动完成
            local wait_count=0
            while [ $wait_count -lt 10 ] && ! pgrep -x "redis-server" > /dev/null; do
                sleep 1
                ((wait_count++))
            done
            
            if pgrep -x "redis-server" > /dev/null; then
                log_info "Redis服务已启动"
            else
                log_warn "Redis服务启动尝试后仍未运行，请检查安装与配置"
            fi
        else
            log_info "Redis服务已在运行"
        fi
    else
        log_warn "Redis未安装，无法启动"
    fi
    
    # 清理临时配置文件
    if [ -f "$MYSQL_TEMP_CONFIG" ]; then
        rm -f "$MYSQL_TEMP_CONFIG"
    fi
    if [ -f "$REDIS_TEMP_CONFIG" ]; then
        rm -f "$REDIS_TEMP_CONFIG"
    fi
}

# 停止服务
stop_services() {
    log_step "停止服务..."
    
    local mysql_stopped=false
    local redis_stopped=false
    
    # 停止MySQL
    if check_mysql_installed && pgrep -x "mysqld" > /dev/null; then
        log_info "停止MySQL服务..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            if brew services stop mysql; then
                mysql_stopped=true
                log_info "MySQL服务已通过brew services停止"
            else
                log_warn "brew services停止MySQL失败，尝试其他方式"
                # 尝试使用mysql.server
                if command -v mysql.server &> /dev/null; then
                    if mysql.server stop; then
                        mysql_stopped=true
                        log_info "MySQL服务已通过mysql.server停止"
                    fi
                fi
                
                # 如果还没停止，尝试直接杀进程
                if ! $mysql_stopped && pgrep -x "mysqld" > /dev/null; then
                    log_info "尝试直接终止MySQL进程..."
                    if pkill -TERM mysqld; then
                        sleep 3
                        if ! pgrep -x "mysqld" > /dev/null; then
                            mysql_stopped=true
                            log_info "MySQL进程已终止"
                        fi
                    fi
                fi
            fi
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            # Linux
            if command -v systemctl &> /dev/null; then
                if systemctl stop mysql 2>/dev/null || systemctl stop mysqld 2>/dev/null; then
                    mysql_stopped=true
                    log_info "MySQL服务已通过systemctl停止"
                fi
            fi
            
            if ! $mysql_stopped && command -v service &> /dev/null; then
                if service mysql stop 2>/dev/null || service mysqld stop 2>/dev/null; then
                    mysql_stopped=true
                    log_info "MySQL服务已通过service停止"
                fi
            fi
            
            # 如果还没停止，尝试直接杀进程
            if ! $mysql_stopped && pgrep -x "mysqld" > /dev/null; then
                log_info "尝试直接终止MySQL进程..."
                if pkill -TERM mysqld; then
                    sleep 3
                    if ! pgrep -x "mysqld" > /dev/null; then
                        mysql_stopped=true
                        log_info "MySQL进程已终止"
                    fi
                fi
            fi
        fi
        
        # 等待MySQL完全停止
        if $mysql_stopped; then
            local wait_count=0
            while [ $wait_count -lt 10 ] && pgrep -x "mysqld" > /dev/null; do
                sleep 1
                ((wait_count++))
            done
            
            if pgrep -x "mysqld" > /dev/null; then
                log_warn "MySQL服务可能未完全停止"
                mysql_stopped=false
            else
                log_info "MySQL服务已完全停止"
            fi
        else
            log_warn "MySQL服务停止失败"
        fi
    else
        log_info "MySQL服务未在运行或未安装"
        mysql_stopped=true
    fi
    
    # 停止Redis
    if check_redis_installed && pgrep -x "redis-server" > /dev/null; then
        log_info "停止Redis服务..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            if brew services stop redis; then
                redis_stopped=true
                log_info "Redis服务已通过brew services停止"
            else
                log_warn "brew services停止Redis失败，尝试其他方式"
                # 尝试直接杀进程
                if pgrep -x "redis-server" > /dev/null; then
                    log_info "尝试直接终止Redis进程..."
                    if pkill -TERM redis-server; then
                        sleep 2
                        if ! pgrep -x "redis-server" > /dev/null; then
                            redis_stopped=true
                            log_info "Redis进程已终止"
                        fi
                    fi
                fi
            fi
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            # Linux
            if command -v systemctl &> /dev/null; then
                if systemctl stop redis 2>/dev/null || systemctl stop redis-server 2>/dev/null; then
                    redis_stopped=true
                    log_info "Redis服务已通过systemctl停止"
                fi
            fi
            
            if ! $redis_stopped && command -v service &> /dev/null; then
                if service redis-server stop 2>/dev/null || service redis stop 2>/dev/null; then
                    # 等待一下再检查进程是否真的停止了
                    sleep 2
                    if ! pgrep -x "redis-server" > /dev/null; then
                        redis_stopped=true
                        log_info "Redis服务已通过service停止"
                    else
                        log_warn "service命令执行成功但Redis进程仍在运行"
                    fi
                fi
            fi
            
            # 如果还没停止，尝试直接杀进程
            if ! $redis_stopped && pgrep -x "redis-server" > /dev/null; then
                log_info "尝试直接终止Redis进程..."
                if pkill -TERM redis-server; then
                    sleep 2
                    if ! pgrep -x "redis-server" > /dev/null; then
                        redis_stopped=true
                        log_info "Redis进程已终止"
                    fi
                fi
            fi
        fi
        
        # 等待Redis完全停止
        if $redis_stopped; then
            local wait_count=0
            while [ $wait_count -lt 5 ] && pgrep -x "redis-server" > /dev/null; do
                sleep 1
                ((wait_count++))
            done
            
            if pgrep -x "redis-server" > /dev/null; then
                log_warn "Redis服务可能未完全停止"
                redis_stopped=false
            else
                log_info "Redis服务已完全停止"
            fi
        else
            log_warn "Redis服务停止失败"
        fi
    else
        log_info "Redis服务未在运行或未安装"
        redis_stopped=true
    fi
    
    # 总结停止结果
    if $mysql_stopped && $redis_stopped; then
        log_info "所有服务已成功停止"
        return 0
    else
        log_warn "部分服务停止失败，请检查服务状态"
        return 1
    fi
}

# 初始化数据库
init_database() {
    log_step "初始化数据库..."
    
    # 加载环境变量
    load_env
    
    # 确保MySQL在运行
    if ! pgrep -x "mysqld" > /dev/null; then
        log_error "MySQL服务未运行，请先启动MySQL服务"
        exit 1
    fi
    
    # 等待MySQL完全启动
    local wait_count=0
    while [ $wait_count -lt 30 ]; do
        if mysql -u root -e "SELECT 1" &>/dev/null; then
            break
        fi
        sleep 1
        ((wait_count++))
    done
    
    if [ $wait_count -eq 30 ]; then
        log_error "MySQL服务未能正常响应，请检查MySQL状态"
        exit 1
    fi
    
    log_info "MySQL服务响应正常，开始初始化数据库..."
    
    # 检查数据库是否已存在并包含数据
    local db_exists=false
    local has_data=false
    
    if mysql -u root -e "USE \`${MYSQL_DATABASE:-tts_db}\`;" &>/dev/null; then
        db_exists=true
        log_info "数据库 '${MYSQL_DATABASE:-tts_db}' 已存在"
        
        # 检查是否有数据表
        local table_count=$(mysql -u root "${MYSQL_DATABASE:-tts_db}" -e "SHOW TABLES;" 2>/dev/null | wc -l)
        if [ "$table_count" -gt 1 ]; then  # 大于1是因为第一行是表头
            has_data=true
            log_warn "数据库中已存在 $((table_count-1)) 个数据表"
            
            # 检查关键表是否有数据
            local tts_tasks_count=$(mysql -u root "${MYSQL_DATABASE:-tts_db}" -e "SELECT COUNT(*) FROM tts_tasks;" 2>/dev/null | tail -n1 || echo "0")
            if [ "$tts_tasks_count" -gt 0 ]; then
                log_warn "tts_tasks表中已有 $tts_tasks_count 条记录"
            fi
        fi
    fi
    
    # 如果数据库已存在且有数据，询问用户是否继续
    if [ "$has_data" = true ]; then
        log_warn "⚠️  警告：数据库已包含数据，继续初始化可能会影响现有数据！"
        echo ""
        echo "请选择操作："
        echo "1) 跳过初始化（推荐）"
        echo "2) 仅创建缺失的表结构（安全）"
        echo "3) 强制重新初始化（危险：可能丢失数据）"
        echo "4) 退出"
        echo ""
        read -p "请输入选择 (1-4): " choice
        
        case "$choice" in
            1)
                log_info "跳过数据库初始化"
                return 0
                ;;
            2)
                log_info "仅创建缺失的表结构..."
                # 继续执行，但跳过用户创建和权限设置
                ;;
            3)
                log_warn "强制重新初始化数据库..."
                log_warn "这可能会导致数据丢失！"
                read -p "确认继续？(输入 'YES' 确认): " confirm
                if [ "$confirm" != "YES" ]; then
                    log_info "取消初始化"
                    return 0
                fi
                ;;
            4|*)
                log_info "退出初始化"
                return 0
                ;;
        esac
    fi
    
    # 创建数据库
    log_info "创建数据库: ${MYSQL_DATABASE:-tts_db}"
    if mysql -u root -e "CREATE DATABASE IF NOT EXISTS \`${MYSQL_DATABASE:-tts_db}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"; then
        log_info "数据库创建成功"
    else
        log_error "数据库创建失败"
        exit 1
    fi
    
    # 只有在选择强制初始化或数据库不存在时才创建用户
    if [ "$has_data" != true ] || [ "$choice" = "3" ]; then
        # 创建用户并授权
        log_info "创建用户: ${MYSQL_USER:-tts_user}"
        if mysql -u root -e "CREATE USER IF NOT EXISTS '${MYSQL_USER:-tts_user}'@'%' IDENTIFIED BY '${MYSQL_PASSWORD:-tts_password}';"; then
            log_info "用户创建成功"
        else
            log_error "用户创建失败"
            exit 1
        fi
        
        # 授权
        log_info "为用户授权..."
        if mysql -u root -e "GRANT ALL PRIVILEGES ON \`${MYSQL_DATABASE:-tts_db}\`.* TO '${MYSQL_USER:-tts_user}'@'%';"; then
            log_info "用户授权成功"
        else
            log_error "用户授权失败"
            exit 1
        fi
        
        # 刷新权限
        if mysql -u root -e "FLUSH PRIVILEGES;"; then
            log_info "权限刷新成功"
        else
            log_error "权限刷新失败"
            exit 1
        fi
    else
        log_info "跳过用户创建和权限设置（用户已存在）"
    fi
    
    # 导入初始化SQL
    if [ -f "$SERVER_DIR/database/init.sql" ]; then
        log_info "导入初始化SQL文件..."
        
        # 如果选择了仅创建表结构，先备份现有数据
        if [ "$choice" = "2" ] && [ "$has_data" = true ]; then
            log_info "检测到现有数据，SQL文件将安全执行（使用IF NOT EXISTS）"
        fi
        
        if mysql -u root "${MYSQL_DATABASE:-tts_db}" < "$SERVER_DIR/database/init.sql"; then
            log_info "初始化SQL导入成功"
        else
            log_error "初始化SQL导入失败"
            exit 1
        fi
    else
        log_warn "未找到初始化SQL文件: $SERVER_DIR/database/init.sql"
    fi
    
    # 验证数据库初始化结果
    log_info "验证数据库初始化结果..."
    
    # 检查数据库是否存在
    if mysql -u root -e "USE \`${MYSQL_DATABASE:-tts_db}\`;" &>/dev/null; then
        log_info "数据库验证成功"
    else
        log_error "数据库验证失败"
        exit 1
    fi
    
    # 检查用户是否能连接
    if mysql -u "${MYSQL_USER:-tts_user}" -p"${MYSQL_PASSWORD:-tts_password}" -e "USE \`${MYSQL_DATABASE:-tts_db}\`;" &>/dev/null; then
        log_info "用户连接验证成功"
    else
        log_error "用户连接验证失败"
        exit 1
    fi
    
    # 检查表是否创建成功
    if [ -f "$SERVER_DIR/database/init.sql" ]; then
        local table_count=$(mysql -u "${MYSQL_USER:-tts_user}" -p"${MYSQL_PASSWORD:-tts_password}" "${MYSQL_DATABASE:-tts_db}" -e "SHOW TABLES;" 2>/dev/null | wc -l)
        if [ "$table_count" -gt 1 ]; then  # 大于1是因为第一行是表头
            log_info "数据表创建验证成功，共有 $((table_count-1)) 个表"
        else
            log_warn "未检测到数据表，可能初始化SQL文件为空或执行失败"
        fi
    fi
    
    log_info "数据库初始化完成"
}

# 重启服务
restart_services() {
    log_step "重启服务..."
    
    # 先停止服务（忽略停止失败的错误）
    stop_services || log_warn "停止服务时出现错误，继续执行启动流程"
    
    # 等待一段时间确保服务完全停止
    log_info "等待服务完全停止..."
    sleep 3
    
    # 再启动服务
    start_services
    
    log_info "服务重启完成"
}

# 检查服务状态
check_status() {
    log_step "检查服务状态..."
    
    local mysql_status="未安装"
    local redis_status="未安装"
    local mysql_connection="N/A"
    local redis_connection="N/A"
    
    # 检查MySQL
    if check_mysql_installed; then
        if pgrep -x "mysqld" > /dev/null; then
            mysql_status="运行中"
            
            # 测试MySQL连接
            if mysql -u root -e "SELECT 1" &>/dev/null; then
                mysql_connection="正常"
            else
                mysql_connection="连接失败"
            fi
            
            # 获取MySQL版本和端口信息
            local mysql_version=$(mysql --version 2>/dev/null | head -n1 | cut -d' ' -f3 | cut -d',' -f1 || echo "未知")
            local mysql_port=$(mysql -u root -e "SHOW VARIABLES LIKE 'port';" 2>/dev/null | grep port | awk '{print $2}' || echo "未知")
            
            log_info "MySQL服务正在运行"
            log_info "  版本: $mysql_version"
            log_info "  端口: $mysql_port"
            log_info "  连接状态: $mysql_connection"
            
            # 检查数据库是否存在
            load_env
            if mysql -u root -e "USE \`${MYSQL_DATABASE:-tts_db}\`;" &>/dev/null; then
                log_info "  数据库 '${MYSQL_DATABASE:-tts_db}' 存在"
                
                # 检查用户是否能连接
                if mysql -u "${MYSQL_USER:-tts_user}" -p"${MYSQL_PASSWORD:-tts_password}" -e "USE \`${MYSQL_DATABASE:-tts_db}\`;" &>/dev/null; then
                    log_info "  用户 '${MYSQL_USER:-tts_user}' 连接正常"
                else
                    log_warn "  用户 '${MYSQL_USER:-tts_user}' 连接失败"
                fi
                
                # 检查表数量
                local table_count=$(mysql -u root "${MYSQL_DATABASE:-tts_db}" -e "SHOW TABLES;" 2>/dev/null | wc -l)
                if [ "$table_count" -gt 1 ]; then
                    log_info "  数据表数量: $((table_count-1))"
                else
                    log_warn "  未检测到数据表"
                fi
            else
                log_warn "  数据库 '${MYSQL_DATABASE:-tts_db}' 不存在"
            fi
        else
            mysql_status="未运行"
            log_warn "MySQL服务未在运行"
        fi
    else
        log_warn "MySQL未安装"
    fi
    
    # 检查Redis
    if check_redis_installed; then
        if pgrep -x "redis-server" > /dev/null; then
            redis_status="运行中"
            
            # 测试Redis连接
            if command -v redis-cli &> /dev/null; then
                if redis-cli ping &>/dev/null; then
                    redis_connection="正常"
                else
                    redis_connection="连接失败"
                fi
                
                # 获取Redis版本和端口信息
                local redis_version=$(redis-cli --version 2>/dev/null | cut -d' ' -f2 || echo "未知")
                local redis_port=$(redis-cli config get port 2>/dev/null | tail -n1 || echo "未知")
                local redis_memory=$(redis-cli info memory 2>/dev/null | grep used_memory_human | cut -d':' -f2 | tr -d '\r' || echo "未知")
                
                log_info "Redis服务正在运行"
                log_info "  版本: $redis_version"
                log_info "  端口: $redis_port"
                log_info "  连接状态: $redis_connection"
                log_info "  内存使用: $redis_memory"
                
                # 检查Redis数据库数量
                local db_count=$(redis-cli config get databases 2>/dev/null | tail -n1 || echo "未知")
                log_info "  数据库数量: $db_count"
            else
                log_warn "redis-cli未安装，无法获取详细信息"
                log_info "Redis服务正在运行"
            fi
        else
            redis_status="未运行"
            log_warn "Redis服务未在运行"
        fi
    else
        log_warn "Redis未安装"
    fi
    
    # 输出状态总结
    echo ""
    log_step "服务状态总结:"
    printf "%-15s %-10s %-10s\n" "服务" "状态" "连接"
    printf "%-15s %-10s %-10s\n" "----" "----" "----"
    printf "%-15s %-10s %-10s\n" "MySQL" "$mysql_status" "$mysql_connection"
    printf "%-15s %-10s %-10s\n" "Redis" "$redis_status" "$redis_connection"
    echo ""
    
    # 返回状态码
    if [[ "$mysql_status" == "运行中" && "$redis_status" == "运行中" ]]; then
        return 0  # 所有服务正常
    elif [[ "$mysql_status" == "未安装" && "$redis_status" == "未安装" ]]; then
        return 2  # 服务未安装
    else
        return 1  # 部分服务异常
    fi
}

# 显示帮助信息
show_help() {
    echo "MySQL和Redis管理脚本"
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  install          安装MySQL和Redis"
    echo "  config           处理配置文件（替换环境变量）"
    echo "  init             初始化数据库（创建数据库、用户、导入SQL）"
    echo "  start            启动服务"
    echo "  stop             停止服务"
    echo "  restart          重启服务"
    echo "  status           检查服务状态"
    echo "  help             显示此帮助信息"
    echo ""
    echo "使用示例:"
    echo "  $0 install       # 安装MySQL和Redis"
    echo "  $0 start         # 启动所有服务"
    echo "  $0 init          # 初始化数据库"
    echo "  $0 status        # 查看服务状态"
    echo "  $0 restart       # 重启所有服务"
    echo ""
    echo "注意事项:"
    echo "  - 请确保.env文件存在并配置正确"
    echo "  - 首次使用请先运行 install 安装服务"
    echo "  - 数据库初始化需要MySQL服务正在运行"
    echo "  - 配置文件位于 data/mysql/mysql.cnf 和 data/redis/redis.conf"
}

# 主函数
main() {
    # 如果没有参数，显示帮助信息
    if [ $# -eq 0 ]; then
        show_help
        exit 0
    fi
    
    # 处理命令行参数
    case "$1" in
        install)
            install_services
            ;;
        config)
            create_configs
            ;;
        init)
            init_database
            ;;
        start)
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        status)
            check_status
            exit $?  # 传递状态检查的返回码
            ;;
        help)
            show_help
            ;;
        *)
            log_error "未知选项: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"