## 快速开始
### 项目部署
#### 1. 克隆项目
```bash
git clone https://github.com/duanfuxing/indexTTS.git
cd indexTTS
```

#### 2. 优化缓存配置，可选（autodl服务器系统盘比较小）
```bash
# 设置 pip 缓存到数据盘
mkdir -p /root/autodl-tmp/pip_cache
pip config set global.cache-dir /root/autodl-tmp/pip_cache

# 设置 conda 缓存到数据盘
conda config --add pkgs_dirs /root/autodl-tmp/conda_cache
```

#### 3. 创建并激活 conda 环境
```bash
# 指定目录创建虚拟环境
conda create --prefix conda_envs/index-tts-vllm python=3.12
conda init bash && source /root/.bashrc 
conda activate conda_envs/indexTTS
```

#### 4. 安装依赖
```bash
# 使用清华源加速安装
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

#### 5. 下载模型
```bash
# Index-TTS
modelscope download --model kusuriuri/Index-TTS-vLLM --local_dir ./checkpoints/Index-TTS-vLLM

# IndexTTS-1.5
modelscope download --model kusuriuri/Index-TTS-1.5-vLLM --local_dir ./checkpoints/Index-TTS-1.5-vLLM

# IndexTTS-2
modelscope download --model kusuriuri/IndexTTS-2-vLLM --local_dir ./checkpoints/IndexTTS-2-vLLM
```

#### 6. 配置环境变量
```bash
# 复制示例环境变量文件
cp .env.example .env

# 编辑 .env 文件，配置数据库连接和其他参数
vim .env
```
#### 7. 安装Redis和MySQL
```bash
# 安装
bash scripts/db_server.sh install

# 脚本命令
bash scripts/db_server.sh install   - 安装MySQL和Redis服务
bash scripts/db_server.sh uninstall - 卸载MySQL和Redis服务
bash scripts/db_server.sh start     - 启动服务
bash scripts/db_server.sh stop      - 停止服务
bash scripts/db_server.sh restart   - 重启服务
bash scripts/db_server.sh status    - 检查服务状态

# 修改MySQL用户密码及登录权限
mysql -u root -p
ALTER USER 'root'@'%' IDENTIFIED BY '新密码';
FLUSH PRIVILEGES;
exit

# 注意事项
- 确保在root用户下执行脚本
- 脚本会自动配置MySQL和Redis服务，无需手动操作
- 配置文件均使用默认路径
    - MySQL配置文件：/etc/mysql/mysql.conf.d/mysqld.cnf
    - Redis配置文件：/etc/redis/redis.conf
- 安装时会使用.env中的数据库连接参数配置MySQL和Redis服务
```

### 服务启动

#### 8. 启动服务
完成上述配置后，按以下顺序启动服务：

```bash
# 1. 激活 conda 环境
cd /root/autodl-tmp
conda activate conda_envs/indexTTS
cd indexTTS

# 2. 启动数据库服务（如果未启动）
bash scripts/db_services.sh start

# 3. 启动 API 服务器
python api_server.py

# 4. 启动任务处理器（新开终端）
# 在新的终端中执行：
cd /root/autodl-tmp
conda activate conda_envs/indexTTS
cd indexTTS
GPU_MEMORY_UTILIZATION=0.40 python task_worker.py
```

#### 服务管理命令
```bash
# 检查服务状态
bash scripts/db_services.sh status

# 重启数据库服务
bash scripts/db_services.sh restart

# 停止数据库服务
bash scripts/db_services.sh stop

# 查看 API 服务器日志
tail -f logs/api_server.log

# 查看任务处理器日志
tail -f logs/task_worker.log
```

#### 服务验证
```bash
# 检查 API 服务器健康状态
curl http://localhost:6006/health

# 获取可用语音列表
curl http://localhost:6006/voices

# 测试在线 TTS 合成
curl -X POST http://localhost:6006/tts/online \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好，这是一个测试",
    "voice": "xiaomeng",
    "speed": 1.0,
    "pitch": 0.0
  }'
```

#### 注意事项
- API 服务器默认运行在 `http://localhost:6006`
- 确保 GPU 内存足够，可根据显卡调整 `GPU_MEMORY_UTILIZATION` 参数
- 长文本任务需要任务处理器运行才能处理
- 首次启动模型加载需要一些时间，请耐心等待
