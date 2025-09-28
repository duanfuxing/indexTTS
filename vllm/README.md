<a href="README.md">中文</a> ｜ <a href="README_EN.md">English</a>

<div align="center">

# IndexTTS-vLLM
</div>

## 项目简介
该项目在 [index-tts](https://github.com/index-tts/index-tts) 的基础上使用 vllm 库重新实现了 gpt 模型的推理，加速了 index-tts 的推理过程。

推理速度在单卡 RTX 4090 上的提升为：
- 单个请求的 RTF (Real-Time Factor)：≈0.3 -> ≈0.1
- 单个请求的 gpt 模型 decode 速度：≈90 token / s -> ≈280 token / s
- 并发量：gpu_memory_utilization设置为0.25（约5GB显存）的情况下，实测 16 左右的并发无压力（测速脚本参考 `simple_test.py`）

## 更新日志

- **[2025-08-07]** 支持 Docker 全自动化一键部署 API 服务：`docker compose up`

- **[2025-08-06]** 支持 openai 接口格式调用：
    1. 添加 /audio/speech api 路径，兼容 OpenAI 接口
    2. 添加 /audio/voices api 路径， 获得 voice/character 列表
    - 对应：[createSpeech](https://platform.openai.com/docs/api-reference/audio/createSpeech)

- **[2025-09-22]** 支持了 vllm v1 版本，IndexTTS2 正在兼容中
- **[2025-09-28]** 支持了 IndexTTS2 的 webui 推理，并整理了权重文件，现在部署更加方便了！ \0.0/ ；但当前版本对于 IndexTTS2 的 gpt 似乎并没有加速效果，待研究（国庆再抽空研究了）

## 使用步骤

### 1. git 本项目
```bash
git clone https://github.com/Ksuriuri/index-tts-vllm.git
cd index-tts-vllm
```


### 2. 创建并激活 conda 环境
```bash
conda create -n index-tts-vllm python=3.12
conda activate index-tts-vllm
```


### 3. 安装 pytorch

需要 pytorch 版本 2.8.0（对应 vllm 0.10.2），具体安装指令请参考：[pytorch 官网](https://pytorch.org/get-started/locally/)


### 4. 安装依赖
```bash
pip install -r requirements.txt
```


### 5. 下载模型权重

（推荐）选择对应版本的模型权重下载到 `checkpoints/` 路径下：

```bash
# Index-TTS
modelscope download --model kusuriuri/Index-TTS-vLLM --local_dir ./checkpoints/Index-TTS-vLLM

# IndexTTS-1.5
modelscope download --model kusuriuri/Index-TTS-1.5-vLLM --local_dir ./checkpoints/Index-TTS-1.5-vLLM

# IndexTTS-2
modelscope download --model kusuriuri/IndexTTS-2-vLLM --local_dir ./checkpoints/IndexTTS-2-vLLM
```

（可选，不推荐）也可以使用 `convert_hf_format.sh` 自行转换官方权重文件：

```bash
bash convert_hf_format.sh /path/to/your/model_dir
```

### 6. webui 启动！

运行对应版本：

```bash
# Index-TTS 1.0
python webui.py

# IndexTTS-1.5
python webui.py --version 1.5

# IndexTTS-2
python webui_v2.py
```
第一次启动可能会久一些，因为要对 bigvgan 进行 cuda 核编译


## API

使用 fastapi 封装了 api 接口，启动示例如下，请将 `--model_dir` 改为你的模型的实际路径：

```bash
python api_server.py --model_dir /your/path/to/Index-TTS
```

### 启动参数
- `--model_dir`: 必填，模型权重路径
- `--host`: 服务ip地址，默认为 `6006`
- `--port`: 服务端口，默认为 `0.0.0.0`
- `--gpu_memory_utilization`: vllm 显存占用率，默认设置为 `0.25`

### 请求示例
参考 `api_example.py`

### OpenAI API
- 添加 /audio/speech api 路径，兼容 OpenAI 接口
- 添加 /audio/voices api 路径， 获得 voice/character 列表

详见：[createSpeech](https://platform.openai.com/docs/api-reference/audio/createSpeech)

## 新特性
- **v1/v1.5:** 支持多角色音频混合：可以传入多个参考音频，TTS 输出的角色声线为多个参考音频的混合版本（输入多个参考音频会导致输出的角色声线不稳定，可以抽卡抽到满意的声线再作为参考音频）

## 性能
Word Error Rate (WER) Results for IndexTTS and Baseline Models on the [**seed-test**](https://github.com/BytedanceSpeech/seed-tts-eval)

| model                   | zh    | en    |
| ----------------------- | ----- | ----- |
| Human                   | 1.254 | 2.143 |
| index-tts (num_beams=3) | 1.005 | 1.943 |
| index-tts (num_beams=1) | 1.107 | 2.032 |
| index-tts-vllm      | 1.12  | 1.987 |

基本保持了原项目的性能

## 并发测试
参考 [`simple_test.py`](simple_test.py)，需先启动 API 服务
