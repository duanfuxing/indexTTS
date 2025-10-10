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
