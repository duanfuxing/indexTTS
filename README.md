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