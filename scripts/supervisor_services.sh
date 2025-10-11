#!/bin/bash

# Supervisor 管理脚本
# 用于管理 IndexTTS 项目的 Supervisor 服务

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目配置
PROJECT_NAME="IndexTTS"
SERVICE_GROUP="tts-services"
API_SERVICE="tts-api-server"
WORKER_SERVICE="tts-task-worker"

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查 supervisor 是否安装
check_supervisor() {
    if ! command -v supervisorctl &> /dev/null; then
        print_error "Supervisor 未安装，请先运行安装脚本: ./install_supervisor.sh"
        exit 1
    fi
}

# 检查 supervisor 服务状态
check_supervisor_service() {
    if ! systemctl is-active --quiet supervisor; then
        print_warning "Supervisor 服务未运行，正在启动..."
        systemctl start supervisor
        sleep 2
    fi
}

# 显示帮助信息
show_help() {
    echo "=========================================="
    echo "IndexTTS Supervisor 管理脚本"
    echo "=========================================="
    echo "用法: $0 [命令]"
    echo ""
    echo "可用命令:"
    echo "  install         安装 Supervisor"
    echo "  start           启动所有服务"
    echo "  stop            停止所有服务"
    echo "  restart         重启所有服务"
    echo "  status          查看服务状态"
    echo "  logs            查看服务日志"
    echo "  reload          重新加载配置"
    echo "  start-api       仅启动 API 服务"
    echo "  start-worker    仅启动 Worker 服务"
    echo "  stop-api        仅停止 API 服务"
    echo "  stop-worker     仅停止 Worker 服务"
    echo "  restart-api     仅重启 API 服务"
    echo "  restart-worker  仅重启 Worker 服务"
    echo "  tail-api        实时查看 API 服务日志"
    echo "  tail-worker     实时查看 Worker 服务日志"
    echo "  shutdown        停止所有服务并关闭 supervisord"
    echo "  help            显示此帮助信息"
    echo ""
    echo "注意事项:"
    echo "  - 首次使用请先运行: $0 install"
    echo "  - 使用项目配置文件，无需系统级配置"
    echo "  - 服务运行在 indexTTS conda 环境中"
    echo "=========================================="
}

# 启动所有服务
start_all() {
    print_info "启动所有 $PROJECT_NAME 服务..."
    
    # 使用项目配置文件启动 supervisord
    local config_file="/root/autodl-tmp/indexTTS/scripts/supervisord.conf"
    if [ ! -f "$config_file" ]; then
        print_error "配置文件不存在: $config_file"
        exit 1
    fi
    
    # 检查 supervisord 是否已经运行
    if pgrep -f "supervisord.*$config_file" > /dev/null; then
        print_info "Supervisord 已经在运行"
    else
        print_info "启动 supervisord..."
        supervisord -c "$config_file"
        sleep 2
    fi
    
    supervisorctl -c "$config_file" start $SERVICE_GROUP:*
    print_success "所有服务启动完成"
}

# 停止所有服务
stop_all() {
    print_info "停止所有 $PROJECT_NAME 服务..."
    local config_file="/root/autodl-tmp/indexTTS/scripts/supervisord.conf"
    
    if [ -f "$config_file" ]; then
        supervisorctl -c "$config_file" stop $SERVICE_GROUP:*
        print_success "所有服务停止完成"
        
        # 询问是否停止 supervisord
        read -p "是否同时停止 supervisord? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            supervisorctl -c "$config_file" shutdown
            print_success "Supervisord 已停止"
        fi
    else
        print_error "配置文件不存在: $config_file"
    fi
}

# 重启所有服务
restart_all() {
    print_info "重启所有 $PROJECT_NAME 服务..."
    local config_file="/root/autodl-tmp/indexTTS/scripts/supervisord.conf"
    
    if [ ! -f "$config_file" ]; then
        print_error "配置文件不存在: $config_file"
        exit 1
    fi
    
    # 检查 supervisord 是否已经运行
    if pgrep -f "supervisord.*$config_file" > /dev/null; then
        supervisorctl -c "$config_file" restart $SERVICE_GROUP:*
    else
        print_info "启动 supervisord..."
        supervisord -c "$config_file"
        sleep 2
        supervisorctl -c "$config_file" start $SERVICE_GROUP:*
    fi
    
    print_success "所有服务重启完成"
}

# 查看服务状态
show_status() {
    print_info "查看 $PROJECT_NAME 服务状态..."
    local config_file="/root/autodl-tmp/indexTTS/scripts/supervisord.conf"
    
    echo "=========================================="
    if [ -f "$config_file" ] && pgrep -f "supervisord.*$config_file" > /dev/null; then
        supervisorctl -c "$config_file" status $SERVICE_GROUP:*
    else
        print_warning "Supervisord 未运行，请先启动服务"
    fi
    echo "=========================================="
}

# 查看服务日志
show_logs() {
    print_info "查看 $PROJECT_NAME 服务日志..."
    echo "=========================================="
    echo "API 服务日志 (最后 20 行):"
    echo "----------------------------------------"
    tail -n 20 /root/autodl-tmp/indexTTS/logs/api_server.log 2>/dev/null || echo "日志文件不存在"
    echo ""
    echo "Worker 服务日志 (最后 20 行):"
    echo "----------------------------------------"
    tail -n 20 /root/autodl-tmp/indexTTS/logs/task_worker.log 2>/dev/null || echo "日志文件不存在"
    echo "=========================================="
}

# 重新加载配置
reload_config() {
    print_info "重新加载 Supervisor 配置..."
    local config_file="/root/autodl-tmp/indexTTS/scripts/supervisord.conf"
    
    if [ -f "$config_file" ] && pgrep -f "supervisord.*$config_file" > /dev/null; then
        supervisorctl -c "$config_file" reread
        supervisorctl -c "$config_file" update
        print_success "配置重新加载完成"
    else
        print_warning "Supervisord 未运行，请先启动服务"
    fi
}

# 启动单个服务
start_service() {
    local service=$1
    print_info "启动 $service 服务..."
    local config_file="/root/autodl-tmp/indexTTS/scripts/supervisord.conf"
    
    if [ ! -f "$config_file" ]; then
        print_error "配置文件不存在: $config_file"
        exit 1
    fi
    
    # 检查 supervisord 是否已经运行
    if pgrep -f "supervisord.*$config_file" > /dev/null; then
        print_info "Supervisord 已经在运行"
    else
        print_info "启动 supervisord..."
        supervisord -c "$config_file"
        sleep 2
    fi
    
    supervisorctl -c "$config_file" start $SERVICE_GROUP:$service
    print_success "$service 服务启动完成"
}

# 停止单个服务
stop_service() {
    local service=$1
    print_info "停止 $service 服务..."
    local config_file="/root/autodl-tmp/indexTTS/scripts/supervisord.conf"
    
    if [ -f "$config_file" ] && pgrep -f "supervisord.*$config_file" > /dev/null; then
        supervisorctl -c "$config_file" stop $SERVICE_GROUP:$service
        print_success "$service 服务停止完成"
    else
        print_warning "Supervisord 未运行"
    fi
}

# 重启单个服务
restart_service() {
    local service=$1
    print_info "重启 $service 服务..."
    local config_file="/root/autodl-tmp/indexTTS/scripts/supervisord.conf"
    
    if [ ! -f "$config_file" ]; then
        print_error "配置文件不存在: $config_file"
        exit 1
    fi
    
    # 检查 supervisord 是否已经运行
    if pgrep -f "supervisord.*$config_file" > /dev/null; then
        supervisorctl -c "$config_file" restart $SERVICE_GROUP:$service
    else
        print_info "启动 supervisord..."
        supervisord -c "$config_file"
        sleep 2
        supervisorctl -c "$config_file" start $SERVICE_GROUP:$service
    fi
    
    print_success "$service 服务重启完成"
}

# 实时查看服务日志
tail_service_log() {
    local service=$1
    local log_file=""
    
    case $service in
        $API_SERVICE)
            log_file="/root/autodl-tmp/indexTTS/logs/api_server.log"
            ;;
        $WORKER_SERVICE)
            log_file="/root/autodl-tmp/indexTTS/logs/task_worker.log"
            ;;
        *)
            print_error "未知服务: $service"
            exit 1
            ;;
    esac
    
    if [ -f "$log_file" ]; then
        print_info "实时查看 $service 日志 (按 Ctrl+C 退出)..."
        tail -f "$log_file"
    else
        print_error "日志文件不存在: $log_file"
        exit 1
    fi
}

# 完全关闭 supervisord
shutdown_supervisor() {
    print_info "停止所有服务并关闭 supervisord..."
    local config_file="/root/autodl-tmp/indexTTS/scripts/supervisord.conf"
    
    if [ -f "$config_file" ] && pgrep -f "supervisord.*$config_file" > /dev/null; then
        supervisorctl -c "$config_file" shutdown
        print_success "Supervisord 已完全关闭"
    else
        print_warning "Supervisord 未运行"
    fi
}

# 安装 Supervisor
install_supervisor() {
    print_info "开始安装 Supervisor..."
    
    # 检查是否为 root 用户
    if [ "$EUID" -ne 0 ]; then
        print_error "请使用 root 用户运行此脚本"
        exit 1
    fi

    # 检查 Python 是否已安装
    if ! command -v python3 &> /dev/null; then
        print_error "未找到 Python3，请先安装 Python3"
        exit 1
    fi

    # 检查 pip 是否已安装
    if ! command -v pip3 &> /dev/null; then
        print_info "正在安装 pip3..."
        apt-get update
        apt-get install -y python3-pip
    fi

    # 安装 supervisor
    print_info "正在安装 supervisor..."
    pip3 install supervisor

    # 检查项目配置文件是否存在
    local project_config="/root/autodl-tmp/indexTTS/scripts/supervisord.conf"
    if [ ! -f "$project_config" ]; then
        print_error "项目配置文件不存在: $project_config"
        exit 1
    fi

    print_success "Supervisor 安装完成!"
    echo "=========================================="
    echo "使用方法:"
    echo "  启动服务: ./supervisor_services.sh start"
    echo "  停止服务: ./supervisor_services.sh stop"
    echo "  查看状态: ./supervisor_services.sh status"
    echo "  查看帮助: ./supervisor_services.sh help"
    echo "=========================================="
}

# 主函数
main() {
    # 检查参数
    if [ $# -eq 0 ]; then
        show_help
        exit 0
    fi
    
    # 检查 supervisor 是否安装 (除了 install 和 help 命令)
    if [[ "$1" != "install" && "$1" != "help" ]]; then
        check_supervisor
    fi
    
    # 根据参数执行相应操作
    case $1 in
        install)
            install_supervisor
            ;;
        start)
            start_all
            ;;
        stop)
            stop_all
            ;;
        restart)
            restart_all
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
        reload)
            reload_config
            ;;
        start-api)
            start_service $API_SERVICE
            ;;
        start-worker)
            start_service $WORKER_SERVICE
            ;;
        stop-api)
            stop_service $API_SERVICE
            ;;
        stop-worker)
            stop_service $WORKER_SERVICE
            ;;
        restart-api)
            restart_service $API_SERVICE
            ;;
        restart-worker)
            restart_service $WORKER_SERVICE
            ;;
        tail-api)
            tail_service_log $API_SERVICE
            ;;
        tail-worker)
            tail_service_log $WORKER_SERVICE
            ;;
        shutdown)
            shutdown_supervisor
            ;;
        help)
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"