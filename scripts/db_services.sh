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
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env}"
SERVER_DIR="$PROJECT_ROOT/server"
DATA_DIR="$PROJECT_ROOT/data"
MYSQL_DATA_DIR="$DATA_DIR/mysql"
REDIS_DATA_DIR="$DATA_DIR/redis"
MYSQL_CONFIG_TEMPLATE="$DATA_DIR/mysql/mysql.cnf.template"
MYSQL_CONFIG_FILE="$DATA_DIR/mysql/mysql.cnf"
REDIS_CONFIG_TEMPLATE="$DATA_DIR/redis/redis.conf.template"
REDIS_CONFIG_FILE="$DATA_DIR/redis/redis.conf"

# 打印彩色输出的函数
log_info() { echo -e "${GREEN}[信息]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
log_error() { echo -e "${RED}[错误]${NC} $1"; }
log_step() { echo -e "${BLUE}[步骤]${NC} $1"; }

# 加载环境变量并验证必需配置
load_env() {
    if [ -f "$ENV_FILE" ]; then
        # 使用source方式加载环境变量，保留空值
        set -a  # 自动导出所有变量
        source "$ENV_FILE"
        set +a  # 关闭自动导出
    else
        log_error ".env文件不存在，请先创建.env文件"
        exit 1
    fi
    
    # 验证MySQL必需配置
    local mysql_missing=()
    [ -z "$MYSQL_HOST" ] && mysql_missing+=("MYSQL_HOST")
    [ -z "$MYSQL_PORT" ] && mysql_missing+=("MYSQL_PORT")
    [ -z "$MYSQL_USER" ] && mysql_missing+=("MYSQL_USER")
    [ -z "$MYSQL_PASSWORD" ] && mysql_missing+=("MYSQL_PASSWORD")
    [ -z "$MYSQL_DATABASE" ] && mysql_missing+=("MYSQL_DATABASE")
    
    # 验证Redis必需配置
    local redis_missing=()
    [ -z "$REDIS_HOST" ] && redis_missing+=("REDIS_HOST")
    [ -z "$REDIS_PORT" ] && redis_missing+=("REDIS_PORT")
    [ -z "$REDIS_USER" ] && redis_missing+=("REDIS_USER")
    [ -z "$REDIS_PASSWORD" ] && redis_missing+=("REDIS_PASSWORD")
    [ -z "$REDIS_DB" ] && redis_missing+=("REDIS_DB")
    
    # 报告缺失的配置
    local has_error=false
    if [ ${#mysql_missing[@]} -gt 0 ]; then
        log_error "MySQL配置缺失以下必需变量:"
        for var in "${mysql_missing[@]}"; do
            log_error "  - $var"
        done
        has_error=true
    fi
    
    if [ ${#redis_missing[@]} -gt 0 ]; then
        log_error "Redis配置缺失以下必需变量:"
        for var in "${redis_missing[@]}"; do
            log_error "  - $var"
        done
        has_error=true
    fi
    
    if [ "$has_error" = true ]; then
        log_error "请在.env文件中补充所有必需的配置变量"
        exit 1
    fi
    
    log_info "环境变量验证通过"
}

# 检查服务是否已安装
check_mysql_installed() { command -v mysql &> /dev/null; }
check_redis_installed() { command -v redis-server &> /dev/null; }

# 卸载服务
uninstall_services() {
    log_step "卸载MySQL和Redis服务..."
    
    local mysql_uninstalled=false
    local redis_uninstalled=false
    
    # 停止服务
    if pgrep -x "mysqld" > /dev/null || pgrep -x "redis-server" > /dev/null; then
        log_info "正在停止运行中的服务..."
        stop_services
    fi
    
    # 卸载MySQL
    if check_mysql_installed; then
        log_info "卸载MySQL..."
        if apt-get remove --purge -y mysql-server mysql-client mysql-common mysql-server-core-* mysql-client-core-*; then
            log_info "MySQL卸载成功"
            mysql_uninstalled=true
        else
            log_warn "MySQL卸载可能不完整"
        fi
        
        # 清理MySQL数据目录
        if [ -d "/var/lib/mysql" ]; then
            log_info "清理MySQL数据目录..."
            rm -rf /var/lib/mysql
        fi
        
        # 清理MySQL配置文件
        if [ -d "/etc/mysql" ]; then
            log_info "清理MySQL配置目录..."
            rm -rf /etc/mysql
        fi
    else
        log_info "MySQL未安装，跳过卸载"
        mysql_uninstalled=true
    fi
    
    # 卸载Redis
    if check_redis_installed; then
        log_info "卸载Redis..."
        if apt-get remove --purge -y redis-server redis-tools; then
            log_info "Redis卸载成功"
            redis_uninstalled=true
        else
            log_warn "Redis卸载可能不完整"
        fi
        
        # 清理Redis数据目录
        if [ -d "/var/lib/redis" ]; then
            log_info "清理Redis数据目录..."
            rm -rf /var/lib/redis
        fi
        
        # 清理Redis配置文件
        if [ -f "/etc/redis/redis.conf" ]; then
            log_info "清理Redis配置文件..."
            rm -f /etc/redis/redis.conf
        fi
    else
        log_info "Redis未安装，跳过卸载"
        redis_uninstalled=true
    fi
    
    # 清理包缓存
    apt-get autoremove -y
    apt-get autoclean
    
    if $mysql_uninstalled && $redis_uninstalled; then
        log_info "MySQL和Redis卸载完成"
        return 0
    else
        log_warn "部分服务卸载失败"
        return 1
    fi
}

# 根据.env配置修改MySQL配置文件
configure_mysql_from_env() {
    log_step "配置MySQL..."
    
    # 确保.env文件已加载
    load_env
    
    local mysql_config_file="/etc/mysql/mysql.conf.d/mysqld.cnf"
    
    if [ ! -f "$mysql_config_file" ]; then
        log_error "MySQL配置文件不存在: $mysql_config_file"
        return 1
    fi
    
    # 备份原配置文件
    cp "$mysql_config_file" "$mysql_config_file.backup.$(date +%Y%m%d_%H%M%S)"
    log_info "已备份原配置文件"
    
    # 修改配置
    log_info "修改MySQL配置..."
    
    # 设置端口
    if [ -n "$MYSQL_PORT" ]; then
        if grep -q "^port" "$mysql_config_file"; then
            sed -i "s/^port.*/port = $MYSQL_PORT/" "$mysql_config_file"
        else
            echo "port = $MYSQL_PORT" >> "$mysql_config_file"
        fi
        log_info "设置端口: $MYSQL_PORT"
    fi
    
    # 设置绑定地址
    if [ -n "$MYSQL_HOST" ] && [ "$MYSQL_HOST" != "localhost" ]; then
        if grep -q "^bind-address" "$mysql_config_file"; then
            sed -i "s/^bind-address.*/bind-address = $MYSQL_HOST/" "$mysql_config_file"
        else
            echo "bind-address = $MYSQL_HOST" >> "$mysql_config_file"
        fi
        log_info "设置绑定地址: $MYSQL_HOST"
    else
        # 默认绑定到localhost
        if grep -q "^bind-address" "$mysql_config_file"; then
            sed -i "s/^bind-address.*/bind-address = 127.0.0.1/" "$mysql_config_file"
        else
            echo "bind-address = 127.0.0.1" >> "$mysql_config_file"
        fi
        log_info "设置绑定地址: 127.0.0.1"
    fi
    
    # 添加一些基本的性能配置
    if ! grep -q "max_connections" "$mysql_config_file"; then
        echo "max_connections = 200" >> "$mysql_config_file"
    fi
    
    if ! grep -q "innodb_buffer_pool_size" "$mysql_config_file"; then
        echo "innodb_buffer_pool_size = 128M" >> "$mysql_config_file"
    fi
    
    log_info "MySQL配置完成"
}

# 根据.env配置修改Redis配置文件
configure_redis_from_env() {
    log_step "配置Redis..."
    
    # 确保.env文件已加载
    load_env
    
    local redis_config_file="/etc/redis/redis.conf"
    
    if [ ! -f "$redis_config_file" ]; then
        log_error "Redis配置文件不存在: $redis_config_file"
        return 1
    fi
    
    # 备份原配置文件
    cp "$redis_config_file" "$redis_config_file.backup.$(date +%Y%m%d_%H%M%S)"
    log_info "已备份原配置文件"
    
    # 修改配置
    log_info "修改Redis配置..."
    
    # 设置端口
    if [ -n "$REDIS_PORT" ]; then
        if grep -q "^port" "$redis_config_file"; then
            sed -i "s/^port.*/port $REDIS_PORT/" "$redis_config_file"
        else
            echo "port $REDIS_PORT" >> "$redis_config_file"
        fi
        log_info "设置端口: $REDIS_PORT"
    fi
    
    # 设置绑定地址
    if [ -n "$REDIS_HOST" ] && [ "$REDIS_HOST" != "localhost" ]; then
        if grep -q "^bind" "$redis_config_file"; then
            sed -i "s/^bind.*/bind $REDIS_HOST/" "$redis_config_file"
        else
            echo "bind $REDIS_HOST" >> "$redis_config_file"
        fi
        log_info "设置绑定地址: $REDIS_HOST"
    else
        # 默认绑定到localhost
        if grep -q "^bind" "$redis_config_file"; then
            sed -i "s/^bind.*/bind 127.0.0.1/" "$redis_config_file"
        else
            echo "bind 127.0.0.1" >> "$redis_config_file"
        fi
        log_info "设置绑定地址: 127.0.0.1"
    fi
    
    # 设置密码
    if [ -n "$REDIS_PASSWORD" ]; then
        if grep -q "^requirepass" "$redis_config_file"; then
            sed -i "s/^requirepass.*/requirepass $REDIS_PASSWORD/" "$redis_config_file"
        else
            echo "requirepass $REDIS_PASSWORD" >> "$redis_config_file"
        fi
        log_info "设置密码认证"
    fi
    
    # 设置用户配置
    if [ -n "$REDIS_PASSWORD" ]; then
        local user_config="user $REDIS_USER on >$REDIS_PASSWORD ~* +@all"
        if grep -q "^user $REDIS_USER" "$redis_config_file"; then
            sed -i "/^user $REDIS_USER/c\\$user_config" "$redis_config_file"
        else
            echo "$user_config" >> "$redis_config_file"
        fi
        log_info "设置用户配置: $REDIS_USER"
    fi
    
    # 设置数据库数量
    if [ -n "$REDIS_DB" ] && [ "$REDIS_DB" -gt 0 ]; then
        local databases=$((REDIS_DB + 1))
        if grep -q "^databases" "$redis_config_file"; then
            sed -i "s/^databases.*/databases $databases/" "$redis_config_file"
        else
            echo "databases $databases" >> "$redis_config_file"
        fi
        log_info "设置数据库数量: $databases"
    fi
    
    # 启用持久化
    if ! grep -q "^save" "$redis_config_file"; then
        echo "save 900 1" >> "$redis_config_file"
        echo "save 300 10" >> "$redis_config_file"
        echo "save 60 10000" >> "$redis_config_file"
    fi
    
    log_info "Redis配置完成"
}

# 安装服务
install_services() {
    log_step "安装MySQL和Redis..."
    
    # 检查是否已安装服务，如果已安装则询问是否卸载
    local need_uninstall=false
    if check_mysql_installed || check_redis_installed; then
        echo ""
        log_warn "检测到系统中已安装MySQL或Redis服务"
        if check_mysql_installed; then
            log_info "已安装的服务: MySQL"
        fi
        if check_redis_installed; then
            log_info "已安装的服务: Redis"
        fi
        echo ""
        log_warn "为了确保配置正确，建议先卸载现有服务再重新安装"
        echo -n "是否要卸载现有的MySQL和Redis服务？(y/N): "
        read -r response
        case "$response" in
            [yY][eE][sS]|[yY])
                need_uninstall=true
                ;;
            *)
                log_info "跳过卸载，继续安装过程..."
                ;;
        esac
    fi
    
    # 如果用户选择卸载，则先卸载现有服务
    if $need_uninstall; then
        uninstall_services
        if [ $? -ne 0 ]; then
            log_error "卸载失败，安装过程中止"
            exit 1
        fi
    fi
    
    # Ubuntu环境安装
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
    
    # 验证安装结果
    if check_mysql_installed && check_redis_installed; then
        log_info "MySQL和Redis安装完成"
        
        # 根据.env配置修改MySQL配置文件
        configure_mysql_from_env
        
        # 根据.env配置修改Redis配置文件
        configure_redis_from_env
        
        # 显示配置文件位置提示
        echo ""
        log_step "配置文件位置提示："
        log_info "MySQL配置文件位置："
        log_info "  - 主配置文件: /etc/mysql/mysql.conf.d/mysqld.cnf"
        log_info ""
        log_info "Redis配置文件位置："
        log_info "  - 主配置文件: /etc/redis/redis.conf"
        echo ""
    else
        log_error "安装验证失败，请检查安装过程"
        exit 1
    fi
}

# 启动服务
start_services() {
    log_step "启动服务..."
    
    # 启动MySQL
    if check_mysql_installed; then
        if ! pgrep -x "mysqld" > /dev/null; then
            log_info "启动MySQL服务..."
            if command -v mysqld &> /dev/null; then
                log_info "直接启动 mysqld..."
                nohup mysqld --defaults-file=/etc/mysql/my.cnf >/dev/null 2>&1 &
                sleep 3
            else
                log_error "未找到 mysqld 可执行文件"
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
            if command -v redis-server &> /dev/null; then
                log_info "直接启动 redis-server..."
                nohup redis-server /etc/redis/redis.conf >/dev/null 2>&1 &
                sleep 2
            else
                log_error "未找到 redis-server 可执行文件"
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
    
    # 测试服务连接
    log_step "测试服务连接..."
    local mysql_test_passed=false
    local redis_test_passed=false
    
    # 测试MySQL连接
    if check_mysql_installed && pgrep -x "mysqld" > /dev/null; then
        if test_mysql_connection; then
            mysql_test_passed=true
        else
            log_warn "MySQL服务已启动但连接测试失败"
        fi
    elif check_mysql_installed; then
        log_warn "MySQL已安装但服务未运行，跳过连接测试"
    else
        log_info "MySQL未安装，跳过连接测试"
        mysql_test_passed=true  # 未安装时视为通过
    fi
    
    # 测试Redis连接
    if check_redis_installed && pgrep -x "redis-server" > /dev/null; then
        if test_redis_connection; then
            redis_test_passed=true
        else
            log_warn "Redis服务已启动但连接测试失败"
        fi
    elif check_redis_installed; then
        log_warn "Redis已安装但服务未运行，跳过连接测试"
    else
        log_info "Redis未安装，跳过连接测试"
        redis_test_passed=true  # 未安装时视为通过
    fi
    
    # 总结测试结果
    if $mysql_test_passed && $redis_test_passed; then
        log_info "所有服务启动并连接测试通过"
        return 0
    else
        log_warn "部分服务连接测试失败，请检查配置"
        return 1
    fi
}

# 测试MySQL连接
test_mysql_connection() {
    log_info "测试MySQL连接..."
    
    # 确保环境变量已加载
    load_env
    
    # 使用mysql命令测试连接
    if command -v mysql &> /dev/null; then
        local test_result
        if test_result=$(mysql -h"$MYSQL_HOST" -P"$MYSQL_PORT" -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" -e "SELECT 1;" 2>&1); then
            log_info "MySQL连接测试成功"
            return 0
        else
            log_error "MySQL连接测试失败: $test_result"
            return 1
        fi
    else
        log_error "mysql客户端未安装，无法测试连接"
        return 1
    fi
}

# 测试Redis连接
test_redis_connection() {
    log_info "测试Redis连接..."
    
    # 确保环境变量已加载
    load_env

    if ! command -v redis-cli &> /dev/null; then
        log_error "redis-cli客户端未安装，无法测试连接"
        return 1
    fi

    local redis_cmd="redis-cli -u redis://$REDIS_USER:$REDIS_PASSWORD@$REDIS_HOST:$REDIS_PORT"
    
    local test_result
    test_result=$($redis_cmd ping 2>&1)
    local exit_code=$?

    if [ $exit_code -ne 0 ]; then
        log_error "Redis连接测试失败: $test_result"
        return 1
    fi

    # 只要输出中包含 PONG 就算成功
    if echo "$test_result" | grep -q "PONG"; then
        log_info "Redis连接测试成功"
        return 0
    else
        log_error "Redis连接测试失败，响应: $test_result"
        return 1
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
        log_info "尝试直接终止MySQL进程..."
        if pkill -TERM mysqld; then
            sleep 3
            if ! pgrep -x "mysqld" > /dev/null; then
                mysql_stopped=true
                log_info "MySQL进程已终止"
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
        log_info "尝试直接终止Redis进程..."
        if pkill -TERM redis-server; then
            sleep 2
            if ! pgrep -x "redis-server" > /dev/null; then
                redis_stopped=true
                log_info "Redis进程已终止"
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

# 检查服务状态
check_services() {
    log_step "检查服务状态..."
    
    # 加载并验证环境变量
    load_env
    
    # 检查MySQL状态
    if check_mysql_installed; then
        if pgrep -x "mysqld" > /dev/null; then
            log_info "MySQL服务: 运行中"
        else
            log_warn "MySQL服务: 未运行"
        fi
    else
        log_warn "MySQL: 未安装"
    fi
    
    # 检查Redis状态
    if check_redis_installed; then
        if pgrep -x "redis-server" > /dev/null; then
            log_info "Redis服务: 运行中"
        else
            log_warn "Redis服务: 未运行"
        fi
    else
        log_warn "Redis: 未安装"
    fi
}

# 主函数
main() {
    case "${1:-}" in
        "install")
            install_services
            ;;
        "uninstall")
            uninstall_services
            ;;
        "start")
            start_services
            ;;
        "stop")
            stop_services
            ;;
        "restart")
            stop_services
            sleep 2
            start_services
            ;;
        "status")
            check_services
            ;;
        *)
            echo "用法: $0 {install|uninstall|start|stop|restart|status}"
            echo ""
            echo "命令说明:"
            echo "  install   - 安装MySQL和Redis服务"
            echo "  uninstall - 卸载MySQL和Redis服务"
            echo "  start     - 启动服务"
            echo "  stop      - 停止服务"
            echo "  restart   - 重启服务"
            echo "  status    - 检查服务状态"
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"