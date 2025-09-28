#!/bin/bash

# 增强型TTS API服务器启动脚本
# 此脚本帮助您启动TTS API服务器和任务处理器
# 支持本地部署模式

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
SERVER_DIR="$PROJECT_ROOT/server"

# 打印彩色输出的函数
log_info() {
    echo -e "${GREEN}[信息]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[警告]${NC} $1"
}

log_error() {
    echo -e "${RED}[错误]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[步骤]${NC} $1"
}

# 初始化环境
init_environment() {
    log_step "初始化环境..."
    
    local need_install_deps=false
    local need_install_supervisor=false
    local need_install_mysql=false
    local need_install_redis=false
    local need_init_db=false
    
    # 1. 检查.env配置是否缺失
    log_info "1. 检查环境配置文件..."
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        if [ -f "$PROJECT_ROOT/.env.example" ]; then
            log_info "复制.env.example到.env"
            cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
            log_warn "请根据实际情况修改.env文件中的配置"
        else
            log_error ".env文件不存在，且未找到.env.example文件"
            log_error "请手动创建.env配置文件或提供.env.example模板文件"
            exit 1
        fi
    else
        log_info "✓ .env配置文件存在"
    fi
    
    # 加载环境变量
    if [ -f "$PROJECT_ROOT/.env" ]; then
        export $(cat "$PROJECT_ROOT/.env" | grep -v '^#' | grep -v '^$' | xargs)
    fi
    
    # 检查关键环境变量
    local missing_vars=""
    [ -z "$MODEL_DIR" ] && missing_vars="$missing_vars MODEL_DIR"
    [ -z "$HOST" ] && missing_vars="$missing_vars HOST"
    [ -z "$PORT" ] && missing_vars="$missing_vars PORT"
    [ -z "$MYSQL_HOST" ] && missing_vars="$missing_vars MYSQL_HOST"
    [ -z "$MYSQL_USER" ] && missing_vars="$missing_vars MYSQL_USER"
    [ -z "$MYSQL_DATABASE" ] && missing_vars="$missing_vars MYSQL_DATABASE"
    
    if [ ! -z "$missing_vars" ]; then
        log_error "环境变量配置缺失:$missing_vars"
        log_error "请在.env文件中配置这些参数"
        exit 1
    fi
    
    # 检查模型目录
    if [ ! -d "$MODEL_DIR" ]; then
        log_error "TTS模型目录不存在: $MODEL_DIR"
        log_error "请确保MODEL_DIR指向正确的模型目录"
        exit 1
    fi
    
    log_info "✓ 环境配置检查通过"
    
    # 2. 依赖检查
    log_info "2. 检查Python依赖..."
    if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
        log_error "requirements.txt文件不存在"
        exit 1
    fi
    
    # 检查关键Python包是否已安装
    local missing_packages=""
    if ! python3 -c "import fastapi" &> /dev/null; then
        missing_packages="$missing_packages fastapi"
    fi
    if ! python3 -c "import uvicorn" &> /dev/null; then
        missing_packages="$missing_packages uvicorn"
    fi
    if ! python3 -c "import sqlalchemy" &> /dev/null; then
        missing_packages="$missing_packages sqlalchemy"
    fi
    
    if [ ! -z "$missing_packages" ]; then
        log_warn "检测到缺失的Python包:$missing_packages"
        need_install_deps=true
    else
        log_info "✓ 关键Python依赖已安装"
    fi
    
    # 3. Supervisor检查
    log_info "3. 检查Supervisor..."
    if ! command -v supervisord &> /dev/null || ! command -v supervisorctl &> /dev/null; then
        log_warn "Supervisor未安装或不完整"
        need_install_supervisor=true
    else
        log_info "✓ Supervisor已安装"
    fi
    
    # 4. MySQL检查
    log_info "4. 检查MySQL..."
    if ! command -v mysql &> /dev/null; then
        log_warn "MySQL客户端未安装"
        need_install_mysql=true
    else
        log_info "✓ MySQL客户端已安装: $(mysql --version | head -n1)"
        
        # 检查MySQL服务是否运行
        if ! pgrep -x "mysqld" > /dev/null; then
            log_warn "MySQL服务未运行"
            need_install_mysql=true
        else
            log_info "✓ MySQL服务正在运行"
            
            # 测试数据库连接
            set +e
            if [ -n "$MYSQL_PASSWORD" ]; then
                mysql --protocol=TCP --connect-timeout=5 -h "$MYSQL_HOST" -P "${MYSQL_PORT:-3306}" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" -e "SELECT 1;" &>/dev/null
            else
                mysql --protocol=TCP --connect-timeout=5 -h "$MYSQL_HOST" -P "${MYSQL_PORT:-3306}" -u "$MYSQL_USER" -e "SELECT 1;" &>/dev/null
            fi
            local db_test_result=$?
            set -e
            
            if [ $db_test_result -eq 0 ]; then
                log_info "✓ MySQL数据库连接正常"
                
                # 检查数据库表是否存在
                local table_exists=0
                if [ -n "$MYSQL_PASSWORD" ]; then
                    table_exists=$(mysql -h "$MYSQL_HOST" -P "${MYSQL_PORT:-3306}" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'tts_tasks';" -s -N 2>/dev/null || echo "0")
                else
                    table_exists=$(mysql -h "$MYSQL_HOST" -P "${MYSQL_PORT:-3306}" -u "$MYSQL_USER" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'tts_tasks';" -s -N 2>/dev/null || echo "0")
                fi
                
                if [ "$table_exists" = "1" ]; then
                    log_info "✓ 数据库表结构已存在"
                else
                    log_warn "数据库表结构不存在"
                    need_init_db=true
                fi
            else
                log_warn "MySQL数据库连接失败"
                need_init_db=true
            fi
        fi
    fi
    
    # 5. Redis检查
    log_info "5. 检查Redis..."
    if ! command -v redis-server &> /dev/null; then
        log_warn "Redis服务器未安装"
        need_install_redis=true
    else
        log_info "✓ Redis已安装: $(redis-server --version | head -n1)"
        
        # 检查Redis服务是否运行
        if ! pgrep -x "redis-server" > /dev/null; then
            log_warn "Redis服务未运行"
            need_install_redis=true
        else
            log_info "✓ Redis服务正在运行"
            
            # 测试Redis连接
            if command -v redis-cli &> /dev/null && redis-cli ping &>/dev/null; then
                log_info "✓ Redis连接正常"
            else
                log_warn "Redis连接失败"
                need_install_redis=true
            fi
        fi
    fi
    
    # 执行必要的安装和初始化
    log_info "===== 环境初始化总结 ====="
    log_info "Python依赖需要安装: $([ "$need_install_deps" = true ] && echo "是" || echo "否")"
    log_info "Supervisor需要安装: $([ "$need_install_supervisor" = true ] && echo "是" || echo "否")"
    log_info "MySQL需要安装/启动: $([ "$need_install_mysql" = true ] && echo "是" || echo "否")"
    log_info "Redis需要安装/启动: $([ "$need_install_redis" = true ] && echo "是" || echo "否")"
    log_info "数据库需要初始化: $([ "$need_init_db" = true ] && echo "是" || echo "否")"
    log_info "================================"
    
    # 安装Python依赖
    if [ "$need_install_deps" = true ]; then
        log_step "安装Python依赖..."
        
        # 检查磁盘空间
        local available_space=$(df /root | tail -1 | awk '{print $4}')
        local required_space=2097152  # 2GB in KB
        
        if [ "$available_space" -lt "$required_space" ]; then
            log_warn "磁盘空间不足 (可用: $(($available_space/1024))MB, 需要: $(($required_space/1024))MB)"
            log_warn "跳过Python依赖安装，但会继续其他初始化步骤"
        else
            cd "$PROJECT_ROOT"
            pip3 install -r requirements.txt
            log_info "✓ Python依赖安装完成"
        fi
    fi
    
    # 安装Supervisor
    if [ "$need_install_supervisor" = true ]; then
        log_step "安装Supervisor..."
        pip3 install supervisor
        log_info "✓ Supervisor安装完成"
    fi
    
    # 安装/启动MySQL和Redis
    if [ "$need_install_mysql" = true ] || [ "$need_install_redis" = true ]; then
        log_step "安装/启动数据库服务..."
        
        # 如果服务未安装，先安装
        if ! command -v mysql &> /dev/null || ! command -v redis-server &> /dev/null; then
            bash "$SCRIPT_DIR/db_services.sh" install
        fi
        
        # 启动数据库服务
        bash "$SCRIPT_DIR/db_services.sh" start
        log_info "✓ 数据库服务启动完成"
        
        # 等待服务就绪
        sleep 3
    fi
    
    # 初始化数据库
    if [ "$need_init_db" = true ]; then
        log_step "初始化数据库..."
        bash "$SCRIPT_DIR/db_services.sh" init
        log_info "✓ 数据库初始化完成"
    fi
    
    log_info "环境初始化完成！"
}

# 检查依赖
check_dependencies() {
    log_step "检查系统依赖..."
    
    # 检查Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python3未安装，请先安装Python3"
        exit 1
    fi

    # 检查并安装数据库相关客户端工具
    if ! command -v mysql &> /dev/null; then
        log_warn "未找到mysql客户端(mysql)，尝试自动安装..."
        bash "$SCRIPT_DIR/db_services.sh" install
    else
        log_info "✓ MySQL客户端已安装: $(mysql --version | head -n1)"
    fi

    if ! command -v redis-server &> /dev/null; then
        log_warn "未找到redis服务器(redis-server)，尝试自动安装..."
        bash "$SCRIPT_DIR/db_services.sh" install
    else
        log_info "✓ Redis已安装: $(redis-server --version | head -n1)"
    fi
    
    log_info "系统依赖检查完成"
}

# 检查数据库服务状态
check_db_services() {
    log_step "检查数据库服务状态..."
    
    # 调用db_services.sh脚本检查服务状态
    bash "$SCRIPT_DIR/db_services.sh" status
}

# 启动数据库服务
start_db_services() {
    log_step "启动数据库服务..."
    
    # 调用db_services.sh脚本启动服务
    bash "$SCRIPT_DIR/db_services.sh" start
}

# 设置环境变量
setup_environment() {
    log_step "设置环境变量..."
    
    # 检查.env文件
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        if [ -f "$PROJECT_ROOT/.env.example" ]; then
            log_info "复制.env.example到.env"
            cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
            log_warn "请根据实际情况修改.env文件中的配置"
        else
            log_error ".env文件不存在，且未找到.env.example文件"
            log_error "请手动创建.env配置文件或提供.env.example模板文件"
            exit 1
        fi
    fi
    
    # 加载环境变量
    if [ -f "$PROJECT_ROOT/.env" ]; then
        export $(cat "$PROJECT_ROOT/.env" | grep -v '^#' | grep -v '^$' | xargs)
    fi

    # 补充常见的MySQL客户端安装路径到PATH（macOS Homebrew）
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if [ -d "/opt/homebrew/opt/mysql-client/bin" ]; then
            export PATH="/opt/homebrew/opt/mysql-client/bin:$PATH"
        fi
        if [ -d "/usr/local/opt/mysql-client/bin" ]; then
            export PATH="/usr/local/opt/mysql-client/bin:$PATH"
        fi
        if [ -d "/opt/homebrew/opt/mysql/bin" ]; then
            export PATH="/opt/homebrew/opt/mysql/bin:$PATH"
        fi
        if [ -d "/usr/local/opt/mysql/bin" ]; then
            export PATH="/usr/local/opt/mysql/bin:$PATH"
        fi
    fi

    # 显示mysql客户端情况
    if command -v mysql &> /dev/null; then
        log_info "✓ MySQL客户端路径: $(command -v mysql)"
        log_info "✓ MySQL客户端版本: $(mysql --version | head -n1)"
    else
        log_warn "未在PATH中找到mysql客户端，后续步骤将尝试安装并补充PATH"
    fi
    
    # 检查数据库配置文件是否存在，如果不存在则创建
    if [ ! -f "$SERVER_DIR/database/mysql.cnf" ] || [ ! -f "$SERVER_DIR/cache/redis.conf" ]; then
        log_info "创建数据库配置文件..."
        bash "$SCRIPT_DIR/db_services.sh" config
    fi
    
    # 检查必要的环境变量
    log_info "检查环境变量配置..."
    
    # 检查TTS模型配置
    if [ -z "$MODEL_DIR" ]; then
        log_error "MODEL_DIR未配置，请在.env文件中设置TTS模型目录路径"
        exit 1
    elif [ ! -d "$MODEL_DIR" ]; then
        log_error "TTS模型目录不存在: $MODEL_DIR"
        log_error "请确保MODEL_DIR指向正确的模型目录"
        exit 1
    fi
    
    # 检查服务器配置
    missing_server_vars=""
    [ -z "$HOST" ] && missing_server_vars="$missing_server_vars HOST"
    [ -z "$PORT" ] && missing_server_vars="$missing_server_vars PORT"
    
    if [ ! -z "$missing_server_vars" ]; then
        log_error "服务器配置缺失以下参数:$missing_server_vars"
        log_error "请在.env文件中配置这些参数"
        exit 1
    fi
    
    log_info "✓ 模型目录: $MODEL_DIR"
    log_info "✓ 服务器配置: $HOST:$PORT"
    
    log_info "环境变量设置完成"
}

# 创建必要的目录
create_directories() {
    log_step "创建必要的目录..."
    
    cd "$PROJECT_ROOT"
    mkdir -p storage/audio
    mkdir -p storage/tasks
    mkdir -p storage/srt
    mkdir -p logs
    mkdir -p database/backups
    
    log_info "目录创建完成"
}

# 安装Python依赖
install_python_dependencies() {
    log_step "安装Python依赖..."
    
    cd "$PROJECT_ROOT"
    if [ -f requirements.txt ]; then
        log_info "开始安装Python依赖包..."
        PIP_ERROR=$(pip3 install -r requirements.txt 2>&1)
        PIP_EXIT_CODE=$?
        
        if [ $PIP_EXIT_CODE -eq 0 ]; then
            log_info "Python依赖安装完成"
        else
            log_error "Python依赖安装失败"
            log_error "错误详情: $PIP_ERROR"
            exit 1
        fi
    else
        log_error "requirements.txt文件不存在"
        exit 1
    fi
}

# 检查数据库连接
check_database() {
    log_step "检查数据库连接..."
    
    # 检查MySQL连接信息
    if [ -z "$MYSQL_HOST" ] || [ -z "$MYSQL_USER" ] || [ -z "$MYSQL_DATABASE" ]; then
        log_error "MySQL连接信息不完整"
        log_error "缺少环境变量: MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE"
        exit 1
    fi
    
    # 端口默认值
    [ -z "$MYSQL_PORT" ] && MYSQL_PORT=3306

    # 检查mysql客户端
    if ! command -v mysql >/dev/null 2>&1; then
        log_error "未找到mysql客户端(mysql)，请先安装客户端工具(例如: apt-get install -y mysql-client 或 yum install -y mysql)"
        exit 1
    fi
    
    log_info "数据库配置信息:"
    log_info "  主机: $MYSQL_HOST"
    log_info "  端口: $MYSQL_PORT"
    log_info "  用户: $MYSQL_USER"
    log_info "  数据库: $MYSQL_DATABASE"
    
    # 测试数据库连接（强制TCP，5秒超时）
    log_info "正在测试数据库连接..."

    set +e
    TMP_ERR_FILE="$(mktemp)"
    if [ -n "$MYSQL_PASSWORD" ]; then
        mysql --protocol=TCP --connect-timeout=5 -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" -e "SELECT 1 as test;" >/dev/null 2>"$TMP_ERR_FILE"
    else
        mysql --protocol=TCP --connect-timeout=5 -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -e "SELECT 1 as test;" >/dev/null 2>"$TMP_ERR_FILE"
    fi
    DB_TEST_EXIT_CODE=$?
    DB_TEST_RESULT="$(cat "$TMP_ERR_FILE")"
    rm -f "$TMP_ERR_FILE"
    set -e
    
    if [ $DB_TEST_EXIT_CODE -eq 0 ]; then
        log_info "✓ 数据库连接测试成功"
    else
        log_error "✗ 数据库连接测试失败 (退出码: $DB_TEST_EXIT_CODE)"
        [ -n "$DB_TEST_RESULT" ] && log_error "错误详情: $DB_TEST_RESULT"
        exit 1
    fi
}

# 检查数据库表是否存在
check_database_tables() {
    log_step "检查数据库表结构..."
    
    # 检查MySQL连接信息
    if [ -z "$MYSQL_HOST" ] || [ -z "$MYSQL_USER" ] || [ -z "$MYSQL_DATABASE" ]; then
        log_error "MySQL连接信息不完整，无法检查表结构"
        log_error "缺少环境变量: MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE"
        exit 1
    fi
    
    # 检查tts_tasks表是否存在
    log_info "检查tts_tasks表..."
    TTS_TASKS_EXISTS="0"
    if [ -n "$MYSQL_PASSWORD" ]; then
        TTS_TASKS_RESULT=$(mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'tts_tasks';" -s -N 2>&1)
        TTS_TASKS_EXIT_CODE=$?
        if [ $TTS_TASKS_EXIT_CODE -eq 0 ]; then
            TTS_TASKS_EXISTS="$TTS_TASKS_RESULT"
            log_info "  ✓ tts_tasks表检查完成，存在状态: $TTS_TASKS_EXISTS"
        else
            log_warn "  ✗ 检查tts_tasks表时出错: $TTS_TASKS_RESULT"
            TTS_TASKS_EXISTS="0"
        fi
    else
        TTS_TASKS_RESULT=$(mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'tts_tasks';" -s -N 2>&1)
        TTS_TASKS_EXIT_CODE=$?
        if [ $TTS_TASKS_EXIT_CODE -eq 0 ]; then
            TTS_TASKS_EXISTS="$TTS_TASKS_RESULT"
            log_info "  ✓ tts_tasks表检查完成，存在状态: $TTS_TASKS_EXISTS"
        else
            log_warn "  ✗ 检查tts_tasks表时出错: $TTS_TASKS_RESULT"
            TTS_TASKS_EXISTS="0"
        fi
    fi
    
    # 检查voice_configs表是否存在
    log_info "检查voice_configs表..."
    VOICE_CONFIGS_EXISTS="0"
    if [ -n "$MYSQL_PASSWORD" ]; then
        VOICE_CONFIGS_RESULT=$(mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'voice_configs';" -s -N 2>&1)
        VOICE_CONFIGS_EXIT_CODE=$?
        if [ $VOICE_CONFIGS_EXIT_CODE -eq 0 ]; then
            VOICE_CONFIGS_EXISTS="$VOICE_CONFIGS_RESULT"
            log_info "  ✓ voice_configs表检查完成，存在状态: $VOICE_CONFIGS_EXISTS"
        else
            log_warn "  ✗ 检查voice_configs表时出错: $VOICE_CONFIGS_RESULT"
            VOICE_CONFIGS_EXISTS="0"
        fi
    else
        VOICE_CONFIGS_RESULT=$(mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" "$MYSQL_DATABASE" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'voice_configs';" -s -N 2>&1)
        VOICE_CONFIGS_EXIT_CODE=$?
        if [ $VOICE_CONFIGS_EXIT_CODE -eq 0 ]; then
            VOICE_CONFIGS_EXISTS="$VOICE_CONFIGS_RESULT"
            log_info "  ✓ voice_configs表检查完成，存在状态: $VOICE_CONFIGS_EXISTS"
        else
            log_warn "  ✗ 检查voice_configs表时出错: $VOICE_CONFIGS_RESULT"
            VOICE_CONFIGS_EXISTS="0"
        fi
    fi
    
    log_info "===== 数据库表检查结果 ====="
    log_info "tts_tasks表存在: $([ "$TTS_TASKS_EXISTS" = "1" ] && echo "是" || echo "否")"
    log_info "voice_configs表存在: $([ "$VOICE_CONFIGS_EXISTS" = "1" ] && echo "是" || echo "否")"
    log_info "================================"
    
    # 如果表不存在，则创建
    if [ "$TTS_TASKS_EXISTS" = "0" ] || [ "$VOICE_CONFIGS_EXISTS" = "0" ]; then
        log_info "发现缺失的表，开始创建..."
        create_database_tables
    else
        log_info "✓ 所有必需的表都已存在"
        # 检查DDL是否有变化
        check_database_schema_changes
    fi
}

# 创建数据库表
create_database_tables() {
    log_step "创建数据库表..."
    
    # 检查初始化脚本是否存在
    if [ ! -f "$PROJECT_ROOT/server/database/init.sql" ]; then
        log_error "数据库初始化脚本不存在: $PROJECT_ROOT/server/database/init.sql"
        exit 1
    fi
    
    log_info "找到数据库初始化脚本: $PROJECT_ROOT/server/database/init.sql"
    log_info "脚本大小: $(wc -l < "$PROJECT_ROOT/server/database/init.sql") 行"
    
    # 执行数据库初始化脚本
    log_info "开始执行数据库初始化..."
    if [ -n "$MYSQL_PASSWORD" ]; then
        MYSQL_INIT_ERROR=$(mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" < "$PROJECT_ROOT/server/database/init.sql" 2>&1) || true
        MYSQL_INIT_EXIT_CODE=$?
    else
        MYSQL_INIT_ERROR=$(mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" "$MYSQL_DATABASE" < "$PROJECT_ROOT/server/database/init.sql" 2>&1) || true
        MYSQL_INIT_EXIT_CODE=$?
    fi
    
    if [ $MYSQL_INIT_EXIT_CODE -eq 0 ]; then
        log_info "✓ 数据库表创建/更新完成"
        log_info "正在验证表创建结果..."
        
        # 验证表是否创建成功
        if [ -n "$MYSQL_PASSWORD" ]; then
            VERIFY_RESULT=$(mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "SHOW TABLES LIKE 'tts_%';" -s -N 2>&1)
        else
            VERIFY_RESULT=$(mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" "$MYSQL_DATABASE" -e "SHOW TABLES LIKE 'tts_%';" -s -N 2>&1)
        fi
        
        if [ $? -eq 0 ] && [ -n "$VERIFY_RESULT" ]; then
            log_info "验证成功，已创建的表:"
            echo "$VERIFY_RESULT" | while read table; do
                log_info "  - $table"
            done
        else
            log_warn "表创建验证失败或未找到相关表"
        fi
    else
        log_error "✗ 数据库表创建失败"
        log_error "错误详情: $MYSQL_INIT_ERROR"
        exit 1
    fi
}

# 检查数据库架构变化
check_database_schema_changes() {
    log_step "检查数据库架构变化..."
    
    # 生成当前表结构的校验和
    if [ -n "$MYSQL_PASSWORD" ]; then
        CURRENT_SCHEMA_RESULT=$(mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "
            SELECT CONCAT(table_name, ':', column_name, ':', data_type, ':', is_nullable, ':', column_default) 
            FROM information_schema.columns 
            WHERE table_schema = DATABASE() AND table_name IN ('tts_tasks', 'voice_configs') 
            ORDER BY table_name, ordinal_position;
        " -s -N 2>&1)
        if [ $? -eq 0 ]; then
            CURRENT_SCHEMA="$CURRENT_SCHEMA_RESULT"
        else
            log_error "获取当前数据库架构失败: $CURRENT_SCHEMA_RESULT"
            exit 1
        fi
    else
        CURRENT_SCHEMA_RESULT=$(mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" "$MYSQL_DATABASE" -e "
            SELECT CONCAT(table_name, ':', column_name, ':', data_type, ':', is_nullable, ':', column_default) 
            FROM information_schema.columns 
            WHERE table_schema = DATABASE() AND table_name IN ('tts_tasks', 'voice_configs') 
            ORDER BY table_name, ordinal_position;
        " -s -N 2>&1)
        if [ $? -eq 0 ]; then
            CURRENT_SCHEMA="$CURRENT_SCHEMA_RESULT"
        else
            log_error "获取当前数据库架构失败: $CURRENT_SCHEMA_RESULT"
            exit 1
        fi
    fi
    
    # 计算当前架构的MD5
    CURRENT_SCHEMA_MD5=$(echo "$CURRENT_SCHEMA" | md5sum | cut -d' ' -f1)
    
    # 计算期望架构的MD5（基于init.sql）
    if [ -f "$PROJECT_ROOT/server/database/init.sql" ]; then
        EXPECTED_SCHEMA_MD5=$(grep -E "CREATE TABLE|ADD COLUMN|MODIFY COLUMN" "$PROJECT_ROOT/server/database/init.sql" | md5sum | cut -d' ' -f1)
    else
        log_error "数据库初始化脚本不存在: $PROJECT_ROOT/server/database/init.sql"
        exit 1
    fi
    
    log_info "当前架构MD5: $CURRENT_SCHEMA_MD5"
    log_info "期望架构MD5: $EXPECTED_SCHEMA_MD5"
    
    if [ "$CURRENT_SCHEMA_MD5" != "$EXPECTED_SCHEMA_MD5" ]; then
        log_warn "检测到数据库架构变化，需要更新表结构"
        update_database_schema
    else
        log_info "数据库架构无变化，跳过更新"
    fi
}

# 更新数据库架构
update_database_schema() {
    log_step "更新数据库架构..."
    
    # 备份当前数据库结构
    BACKUP_FILE="$PROJECT_ROOT/database/backups/schema_backup_$(date +%Y%m%d_%H%M%S).sql"
    mkdir -p "$PROJECT_ROOT/database/backups"
    
    log_info "备份当前数据库结构到: $BACKUP_FILE"
    if [ -n "$MYSQL_PASSWORD" ]; then
        BACKUP_RESULT=$(mysqldump -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" --no-data "$MYSQL_DATABASE" 2>&1)
        BACKUP_EXIT_CODE=$?
        if [ $BACKUP_EXIT_CODE -eq 0 ]; then
            echo "$BACKUP_RESULT" > "$BACKUP_FILE"
            log_info "数据库结构备份完成"
        else
            log_warn "数据库结构备份失败，但继续执行更新"
            log_warn "备份错误详情: $BACKUP_RESULT"
        fi
    else
        BACKUP_RESULT=$(mysqldump -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" --no-data "$MYSQL_DATABASE" 2>&1)
        BACKUP_EXIT_CODE=$?
        if [ $BACKUP_EXIT_CODE -eq 0 ]; then
            echo "$BACKUP_RESULT" > "$BACKUP_FILE"
            log_info "数据库结构备份完成"
        else
            log_warn "数据库结构备份失败，但继续执行更新"
            log_warn "备份错误详情: $BACKUP_RESULT"
        fi
    fi
    
    # 执行架构更新（重新运行init.sql）
    log_info "执行数据库架构更新..."
    create_database_tables
}

# 初始化数据库
initialize_database() {
    log_step "初始化MySQL数据库..."
    
    # 检查MySQL连接信息
    if [ -z "$MYSQL_HOST" ] || [ -z "$MYSQL_USER" ] || [ -z "$MYSQL_DATABASE" ]; then
        log_error "MySQL连接信息不完整，跳过数据库初始化"
        log_error "缺少环境变量: MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE"
        exit 1
    fi
    
    # 检查并创建/更新数据库表
    check_database_tables
}

# 检查supervisor安装
check_supervisor() {
    log_step "检查supervisor安装..."
    
    if ! command -v supervisord &> /dev/null; then
        log_warn "supervisor未安装，将在安装依赖时自动安装"
        return 0
    fi
    
    if ! command -v supervisorctl &> /dev/null; then
        log_warn "supervisorctl未找到，将在安装依赖时重新安装supervisor"
        return 0
    fi
    
    log_info "supervisor检查通过"
}

# 启动supervisor守护进程
start_supervisord() {
    log_step "启动supervisor守护进程..."
    
    # 检查supervisor是否已经在运行
    if [ -f "$PROJECT_ROOT/logs/supervisord.pid" ]; then
        local pid=$(cat "$PROJECT_ROOT/logs/supervisord.pid" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            log_info "supervisor守护进程已在运行 (PID: $pid)，跳过启动"
            return 0
        else
            log_info "清理过期的PID文件"
            rm -f "$PROJECT_ROOT/logs/supervisord.pid"
        fi
    fi
    
    # 设置环境变量供supervisor使用
    export MODEL_DIR="$MODEL_DIR"
    export HOST="$HOST"
    export PORT="$PORT"
    export GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.9}"
    export DATABASE_URL="mysql://${MYSQL_USER}:${MYSQL_PASSWORD}@${MYSQL_HOST}:${MYSQL_PORT:-3306}/${MYSQL_DATABASE}"
    export AUDIO_OUTPUT_DIR="${AUDIO_OUTPUT_DIR:-$PROJECT_ROOT/storage/audio}"
    
    # 设置supervisor进程管理配置
    export SUPERVISOR_AUTOSTART="${SUPERVISOR_AUTOSTART:-true}"
    export SUPERVISOR_AUTORESTART="${SUPERVISOR_AUTORESTART:-true}"
    export SUPERVISOR_STARTSECS="${SUPERVISOR_STARTSECS:-10}"
    export SUPERVISOR_STARTRETRIES="${SUPERVISOR_STARTRETRIES:-3}"
    export SUPERVISOR_LOG_MAXBYTES="${SUPERVISOR_LOG_MAXBYTES:-50MB}"
    export SUPERVISOR_LOG_BACKUPS="${SUPERVISOR_LOG_BACKUPS:-10}"
    export SUPERVISOR_API_PRIORITY="${SUPERVISOR_API_PRIORITY:-100}"
    export SUPERVISOR_WORKER_PRIORITY="${SUPERVISOR_WORKER_PRIORITY:-200}"
    export SUPERVISOR_USER="${SUPERVISOR_USER:-root}"
    export SUPERVISOR_PROJECT_DIR="${SUPERVISOR_PROJECT_DIR:-$PROJECT_ROOT}"
    
    # 确保日志目录存在
    mkdir -p "$PROJECT_ROOT/logs"
    
    # 启动supervisord，使用绝对路径配置文件
    log_info "启动supervisor守护进程..."
    cd "$PROJECT_ROOT"
    SUPERVISORD_ERROR=$(supervisord -c "$PROJECT_ROOT/server/supervisor/supervisord.conf" 2>&1)
    SUPERVISORD_EXIT_CODE=$?
    
    if [ $SUPERVISORD_EXIT_CODE -eq 0 ]; then
        log_info "supervisor守护进程启动成功"
        sleep 2  # 等待supervisor完全启动
        
        # 验证supervisor是否正常运行
        if supervisorctl -c "$PROJECT_ROOT/server/supervisor/supervisord.conf" status >/dev/null 2>&1; then
            log_info "supervisor守护进程验证成功"
        else
            log_warn "supervisor守护进程可能未完全启动，继续执行..."
        fi
    else
        log_error "supervisor守护进程启动失败"
        log_error "错误详情: $SUPERVISORD_ERROR"
        exit 1
    fi
}

# 启动所有服务
start_services() {
    log_step "通过supervisor启动TTS服务组件..."
    
    # 获取当前服务状态
    log_info "检查当前服务状态..."
    SERVICES_STATUS=$(supervisorctl -c "$PROJECT_ROOT/server/supervisor/supervisord.conf" status tts-services:* 2>&1)
    SERVICES_STATUS_EXIT_CODE=$?
    
    if [ $SERVICES_STATUS_EXIT_CODE -ne 0 ]; then
        log_error "无法获取服务状态，supervisor可能未运行"
        log_error "错误详情: $SERVICES_STATUS"
        exit 1
    fi
    
    # 详细分析每个服务的状态
    log_info "当前服务状态详情:"
    echo "$SERVICES_STATUS" | while read line; do
        if [ -n "$line" ]; then
            service_name=$(echo "$line" | awk '{print $1}')
            service_status=$(echo "$line" | awk '{print $2}')
            
            case "$service_status" in
                "RUNNING")
                    log_info "  ✓ $service_name: 正在运行"
                    ;;
                "STOPPED")
                    log_warn "  ✗ $service_name: 已停止"
                    ;;
                "FATAL"|"EXITED"|"BACKOFF")
                    log_error "  ✗ $service_name: 状态异常 ($service_status)"
                    ;;
                *)
                    log_warn "  ? $service_name: 未知状态 ($service_status)"
                    ;;
            esac
        fi
    done
    
    # 检查是否有服务需要启动
    STOPPED_SERVICES=$(echo "$SERVICES_STATUS" | grep -E "STOPPED|FATAL|EXITED" | awk '{print $1}')
    RUNNING_SERVICES=$(echo "$SERVICES_STATUS" | grep "RUNNING" | awk '{print $1}')
    
    if [ -n "$RUNNING_SERVICES" ]; then
        log_info "已运行的服务:"
        echo "$RUNNING_SERVICES" | while read service; do
            log_info "  - $service"
        done
    fi
    
    if [ -n "$STOPPED_SERVICES" ]; then
        log_info "需要启动的服务:"
        echo "$STOPPED_SERVICES" | while read service; do
            log_info "  - $service"
        done
        
        # 启动停止的服务
        log_info "启动停止的服务..."
        echo "$STOPPED_SERVICES" | while read service; do
            if [ -n "$service" ]; then
                log_info "启动服务: $service"
                START_RESULT=$(supervisorctl -c "$PROJECT_ROOT/server/supervisor/supervisord.conf" start "$service" 2>&1)
                START_EXIT_CODE=$?
                if [ $START_EXIT_CODE -eq 0 ]; then
                    log_info "  ✓ $service 启动成功"
                else
                    log_error "  ✗ $service 启动失败"
                    log_error "  错误详情: $START_RESULT"
                fi
            fi
        done
        SUPERVISOR_START_EXIT_CODE=0
    else
        log_info "所有服务都已在运行，无需启动"
        SUPERVISOR_START_EXIT_CODE=0
    fi
    
    if [ $SUPERVISOR_START_EXIT_CODE -eq 0 ]; then
        log_info "所有TTS服务组件启动完成"
    else
        log_error "TTS服务组件启动失败"
        log_error "错误详情: $SUPERVISOR_START_ERROR"
        # 显示详细状态
        supervisorctl -c "$PROJECT_ROOT/server/supervisor/supervisord.conf" status tts-services:* || true
    fi
}

# 检查服务状态
check_services() {
    log_step "检查服务状态..."
    
    # 检查supervisor守护进程
    SUPERVISOR_STATUS=$(supervisorctl -c "$PROJECT_ROOT/server/supervisor/supervisord.conf" status 2>&1)
    if [ $? -ne 0 ]; then
        log_warn "✗ supervisor守护进程未运行"
        log_warn "错误详情: $SUPERVISOR_STATUS"
        # 尝试启动supervisor
        log_info "尝试启动supervisor守护进程..."
        start_supervisord || true
        return 1
    else
        log_info "✓ supervisor守护进程运行正常"
    fi
    
    # 获取详细的服务状态
    log_info "获取详细服务状态..."
    SERVICES_STATUS=$(supervisorctl -c "$PROJECT_ROOT/server/supervisor/supervisord.conf" status tts-services:* 2>&1)
    SERVICES_STATUS_EXIT_CODE=$?
    
    if [ $SERVICES_STATUS_EXIT_CODE -ne 0 ]; then
        log_error "无法获取服务状态"
        log_error "错误详情: $SERVICES_STATUS"
        return 1
    fi
    
    # 分析每个服务的详细状态
    log_info "===== 详细服务状态 ====="
    
    RUNNING_COUNT=0
    STOPPED_COUNT=0
    ERROR_COUNT=0
    TOTAL_COUNT=0
    
    echo "$SERVICES_STATUS" | while read line; do
        if [ -n "$line" ]; then
            TOTAL_COUNT=$((TOTAL_COUNT + 1))
            service_name=$(echo "$line" | awk '{print $1}')
            service_status=$(echo "$line" | awk '{print $2}')
            service_info=$(echo "$line" | awk '{for(i=3;i<=NF;i++) printf "%s ", $i; print ""}' | sed 's/[[:space:]]*$//')
            
            case "$service_status" in
                "RUNNING")
                    RUNNING_COUNT=$((RUNNING_COUNT + 1))
                    log_info "  ✓ $service_name: 正在运行"
                    if [ -n "$service_info" ]; then
                        log_info "    详情: $service_info"
                    fi
                    ;;
                "STOPPED")
                    STOPPED_COUNT=$((STOPPED_COUNT + 1))
                    log_warn "  ✗ $service_name: 已停止"
                    if [ -n "$service_info" ]; then
                        log_warn "    详情: $service_info"
                    fi
                    ;;
                "FATAL")
                    ERROR_COUNT=$((ERROR_COUNT + 1))
                    log_error "  ✗ $service_name: 致命错误"
                    if [ -n "$service_info" ]; then
                        log_error "    详情: $service_info"
                    fi
                    ;;
                "EXITED")
                    ERROR_COUNT=$((ERROR_COUNT + 1))
                    log_error "  ✗ $service_name: 已退出"
                    if [ -n "$service_info" ]; then
                        log_error "    详情: $service_info"
                    fi
                    ;;
                "BACKOFF")
                    ERROR_COUNT=$((ERROR_COUNT + 1))
                    log_error "  ✗ $service_name: 启动失败，正在重试"
                    if [ -n "$service_info" ]; then
                        log_error "    详情: $service_info"
                    fi
                    ;;
                "STARTING")
                    log_info "  ⏳ $service_name: 正在启动"
                    if [ -n "$service_info" ]; then
                        log_info "    详情: $service_info"
                    fi
                    ;;
                *)
                    log_warn "  ? $service_name: 未知状态 ($service_status)"
                    if [ -n "$service_info" ]; then
                        log_warn "    详情: $service_info"
                    fi
                    ;;
            esac
        fi
    done
    
    # 显示服务状态统计
    TOTAL_SERVICES=$(echo "$SERVICES_STATUS" | wc -l | tr -d ' ')
    RUNNING_SERVICES=$(echo "$SERVICES_STATUS" | grep "RUNNING" | wc -l | tr -d ' ')
    STOPPED_SERVICES=$(echo "$SERVICES_STATUS" | grep -E "STOPPED|FATAL|EXITED|BACKOFF" | wc -l | tr -d ' ')
    
    log_info "===== 服务状态统计 ====="
    log_info "总服务数: $TOTAL_SERVICES"
    log_info "运行中: $RUNNING_SERVICES"
    log_info "停止/异常: $STOPPED_SERVICES"
    
    if [ "$RUNNING_SERVICES" -eq "$TOTAL_SERVICES" ]; then
        log_info "✓ 所有服务运行正常"
    elif [ "$RUNNING_SERVICES" -gt 0 ]; then
        log_warn "⚠ 部分服务异常 ($RUNNING_SERVICES/$TOTAL_SERVICES 正常运行)"
    else
        log_error "✗ 所有服务都未运行"
    fi
    
    # 检查API服务器健康状态
    log_info "检查API服务器健康状态..."
    # 等待API服务器启动
    for i in {1..30}; do
        API_HEALTH=$(curl -f http://localhost:$PORT/health 2>&1)
        if [ $? -eq 0 ]; then
            log_info "✓ API服务器健康检查通过"
            break
        elif [ $i -eq 30 ]; then
            log_warn "✗ API服务器健康检查失败 (超时)"
            log_warn "错误详情: $API_HEALTH"
        else
            sleep 2
        fi
    done
    
    # 检查数据库连接
    log_info "检查数据库连接..."
    if [ -n "$MYSQL_PASSWORD" ]; then
        DB_ERROR=$(mysql -h "$MYSQL_HOST" -P "${MYSQL_PORT:-3306}" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" -e "SELECT 1;" 2>&1)
        if [ $? -eq 0 ]; then
            log_info "✓ 数据库连接正常"
        else
            log_warn "✗ 数据库连接异常"
            log_warn "错误详情: $DB_ERROR"
        fi
    else
        DB_ERROR=$(mysql -h "$MYSQL_HOST" -P "${MYSQL_PORT:-3306}" -u "$MYSQL_USER" -e "SELECT 1;" 2>&1)
        if [ $? -eq 0 ]; then
            log_info "✓ 数据库连接正常"
        else
            log_warn "✗ 数据库连接异常"
            log_warn "错误详情: $DB_ERROR"
        fi
    fi
    
    # 输出服务清单
    log_info "===== 服务清单 ====="
    log_info "1. 数据库服务: MySQL (端口: ${MYSQL_PORT:-3306})"
    log_info "2. 缓存服务: Redis (端口: ${REDIS_PORT:-6379})"
    log_info "3. API服务器 (端口: $PORT)"
    log_info "4. 任务处理器"
    log_info "===================="
}

# 停止服务
stop_services() {
    log_step "停止所有服务..."
    
    # 检查supervisor是否运行
    SUPERVISOR_STATUS=$(supervisorctl -c "$PROJECT_ROOT/server/supervisor/supervisord.conf" status 2>&1)
    if [ $? -ne 0 ]; then
        log_warn "supervisor守护进程未运行，无需停止服务"
        log_warn "错误详情: $SUPERVISOR_STATUS"
        return 0
    fi
    
    # 停止TTS服务组
    log_info "正在停止TTS服务组件..."
    supervisorctl -c "$PROJECT_ROOT/server/supervisor/supervisord.conf" stop tts-services:*
    
    if [ $? -eq 0 ]; then
        log_info "TTS服务组件已停止"
    else
        log_warn "停止TTS服务组件时出现问题"
    fi
    
    # 停止supervisor守护进程
    log_info "正在停止supervisor守护进程..."
    supervisorctl -c "$PROJECT_ROOT/server/supervisor/supervisord.conf" shutdown
    
    if [ $? -eq 0 ]; then
        log_info "supervisor守护进程已停止"
    else
        log_warn "停止supervisor守护进程时出现问题"
    fi
    
    # 清理PID和socket文件
    rm -f "$PROJECT_ROOT/logs/supervisord.pid" "$PROJECT_ROOT/logs/supervisor.sock" 2>/dev/null || true
    
    log_info "所有服务已停止"
}

# supervisor管理命令
supervisor_cmd() {
    SUPERVISOR_STATUS=$(supervisorctl -c "$PROJECT_ROOT/server/supervisor/supervisord.conf" status 2>&1)
    if [ $? -ne 0 ]; then
        log_error "supervisor守护进程未运行，请先启动服务"
        log_error "错误详情: $SUPERVISOR_STATUS"
        exit 1
    fi
    
    case "$1" in
        "")
            log_info "supervisor服务状态:"
            supervisorctl -c "$PROJECT_ROOT/server/supervisor/supervisord.conf" status
            ;;
        *)
            log_info "执行supervisor命令: $*"
            supervisorctl -c "$PROJECT_ROOT/server/supervisor/supervisord.conf" "$@"
            ;;
    esac
}

# 显示帮助信息
show_help() {
    echo "Enhanced TTS API Server 启动脚本 (基于Supervisor)"
    echo ""
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  init                  初始化环境 (检查并安装依赖、数据库等)"
    echo "  start                 启动所有服务 (需要先运行init)"
    echo "  quickstart            快速启动 (自动初始化+启动服务)"
    echo "  stop                  停止所有服务"
    echo "  restart               重启所有服务"
    echo "  status                检查服务状态"
    echo "  logs                  查看日志"
    echo "  supervisor [cmd]      执行supervisor命令"
    echo "  help                  显示此帮助信息"
    echo ""
    echo "服务组件:"
    echo "  - TTS API服务器       提供语音合成API接口"
    echo "  - TTS任务处理器       处理长文本语音合成任务"

    echo ""
    echo "推荐使用流程:"
    echo "  首次使用:"
    echo "    $0 init               # 初始化环境（首次运行必须）"
    echo "    $0 start              # 启动所有服务"
    echo ""
    echo "  或者使用快速启动:"
    echo "    $0 quickstart         # 一键初始化并启动"
    echo ""
    echo "  日常使用:"
    echo "    $0 start              # 启动服务"
    echo "    $0 stop               # 停止服务"
    echo "    $0 restart            # 重启服务"
    echo "    $0 status             # 检查状态"
    echo ""
    echo "  高级操作:"
    echo "    $0 supervisor         # 查看supervisor状态"
    echo "    $0 supervisor restart tts-api-server  # 重启API服务器"
}

# 查看日志
show_logs() {
    log_step "显示服务日志..."
    
    echo "=== API服务器日志 ==="
    if [ -f "$PROJECT_ROOT/logs/api_server.log" ]; then
        tail -n 50 "$PROJECT_ROOT/logs/api_server.log"
    else
        echo "API服务器日志文件不存在"
    fi
    
    echo ""
    echo "=== 任务处理器日志 ==="
    if [ -f "$PROJECT_ROOT/logs/worker_long.log" ]; then
        tail -n 50 "$PROJECT_ROOT/logs/worker_long.log"
    else
        echo "任务处理器日志文件不存在"
    fi
    
    echo ""
    echo "=== 服务日志 ==="
    if [ -f "$PROJECT_ROOT/logs/tts_api.log" ]; then
        tail -n 50 "$PROJECT_ROOT/logs/tts_api.log"
    else
        echo "服务日志文件不存在"
    fi
}

# 主函数
main() {
    case "$1" in
        init)
            init_environment # 初始化环境
            ;;
        start)
            # 快速检查关键环境变量是否存在
            if [ ! -f "$PROJECT_ROOT/.env" ]; then
                log_error ".env文件不存在，请先运行: $0 init"
                exit 1
            fi
            
            # 加载环境变量
            setup_environment
            
            # 检查关键服务是否可用
            if ! command -v mysql &> /dev/null || ! command -v redis-server &> /dev/null; then
                log_error "数据库服务未安装，请先运行: $0 init"
                exit 1
            fi
            
            if ! command -v supervisord &> /dev/null || ! command -v supervisorctl &> /dev/null; then
                log_error "Supervisor未安装，请先运行: $0 init"
                exit 1
            fi
            
            log_info "开始启动TTS服务..."
            
            # 确保必要目录存在
            create_directories
            
            # 启动数据库服务
            log_step "启动数据库服务..."
            start_db_services
            sleep 3 # 等待数据库服务就绪
            
            # 启动supervisor守护进程
            start_supervisord
            
            # 启动应用服务
            start_services
            
            sleep 5 # 等待服务启动
            
            # 检查服务状态
            check_services
            
            log_info "所有服务启动完成！"
            log_info "API服务器地址: http://localhost:$PORT"
            log_info "健康检查: http://localhost:$PORT/health"
            log_info "API文档: http://localhost:$PORT/docs"
            
            # 输出服务清单
            log_info "===== 服务清单 ====="
            log_info "1. 数据库服务: MySQL (端口: ${MYSQL_PORT:-3306})"
            log_info "2. 缓存服务: Redis (端口: ${REDIS_PORT:-6379})"
            log_info "3. API服务器 (端口: $PORT)"
            log_info "4. 任务处理器"
            log_info "===================="
            
            log_info "提示: 如果遇到问题，请先运行 '$0 init' 初始化环境"
            ;;
        quickstart)
            log_info "快速启动模式: 自动初始化环境并启动服务"
            init_environment
            echo ""
            log_info "环境初始化完成，开始启动服务..."
            main start
            ;;
        stop)
            stop_services # 停止服务
            ;;
        restart)
            stop_services # 停止服务
            sleep 3
            main start
            ;;
        status)
            check_services # 检查服务状态
            ;;
        logs)
            show_logs # 显示日志
            ;;
        supervisor)
            shift
            supervisor_cmd "$@"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"