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