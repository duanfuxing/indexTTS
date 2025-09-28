<a href="README.md">中文</a> ｜ <a href="README_EN.md">English</a>

<div align="center">

# IndexTTS-vLLM
</div>

## Introduction
This project re-implements the inference of the gpt model from [index-tts](https://github.com/index-tts/index-tts) using the vllm library, which accelerates the inference process of index-tts.

The inference speed improvement on a single RTX 4090 is as follows:
- RTF (Real-Time Factor) for a single request: ≈0.3 -> ≈0.1
- gpt model decode speed for a single request: ≈90 token / s -> ≈280 token / s
- Concurrency: With gpu_memory_utilization set to 0.25 (approximately 5GB of VRAM), it has been tested to handle a concurrency of around 16 without issues (for the testing script, refer to `simple_test.py`).

## Update Log

- **[2025-08-07]** Support for fully automated one-click deployment of the API service using Docker: `docker compose up`

- **[2025-08-06]** Support for calling in the OpenAI interface format:
    1. Added `/audio/speech` api path to be compatible with the OpenAI interface.
    2. Added `/audio/voices` api path to get the voice/character list.
    - Corresponds to: [createSpeech](https://platform.openai.com/docs/api-reference/audio/createSpeech)

- **[2025-09-22]** vllm v1 is now supported, and compatibility with IndexTTS2 is in progress.
- **[2025-09-28]** Webui inference for IndexTTS2 is now supported, and the weight files have been organized for more convenient deployment 0.0; however, the current version does not seem to have an accelerating effect on the gpt of IndexTTS2, which is under investigation.

## Usage Steps

### 1. git clone this project
```bash
git clone https://github.com/Ksuriuri/index-tts-vllm.git
cd index-tts-vllm
```


### 2. Create and activate a conda environment
```bash
conda create -n index-tts-vllm python=3.12
conda activate index-tts-vllm
```


### 3. Install pytorch

Pytorch version 2.8.0 is required (corresponding to vllm 0.10.2). For specific installation instructions, please refer to the [pytorch official website](https://pytorch.org/get-started/locally/).


### 4. Install dependencies
```bash
pip install -r requirements.txt
```


### 5. Download model weights

(Recommended) Download the model weights for the corresponding version to the `checkpoints/` path:

```bash
# Index-TTS
modelscope download --model kusuriuri/Index-TTS-vLLM --local_dir ./checkpoints/Index-TTS-vLLM

# IndexTTS-1.5
modelscope download --model kusuriuri/Index-TTS-1.5-vLLM --local_dir ./checkpoints/Index-TTS-1.5-vLLM

# IndexTTS-2
modelscope download --model kusuriuri/IndexTTS-2-vLLM --local_dir ./checkpoints/IndexTTS-2-vLLM
```

(Optional, not recommended) You can also use `convert_hf_format.sh` to convert the official weight files yourself:

```bash
bash convert_hf_format.sh /path/to/your/model_dir
```

### 6. Start the webui!

Run the corresponding version:

```bash
# Index-TTS 1.0
python webui.py

# IndexTTS-1.5
python webui.py --version 1.5

# IndexTTS-2
python webui_v2.py
```
The first startup may take longer because it needs to compile the cuda kernel for bigvgan.


## API

The api interface is encapsulated using fastapi. The following is an example of how to start it. Please change `--model_dir` to the actual path of your model:

```bash
python api_server.py --model_dir /your/path/to/Index-TTS
```

### Startup parameters
- `--model_dir`: Required, the path to the model weights.
- `--host`: Service ip address, defaults to `6006`.
- `--port`: Service port, defaults to `0.0.0.0`.
- `--gpu_memory_utilization`: vllm GPU memory utilization, defaults to `0.25`.

### Request example
Refer to `api_example.py`.

### OpenAI API
- Added `/audio/speech` api path to be compatible with the OpenAI interface.
- Added `/audio/voices` api path to get the voice/character list.

For details, see: [createSpeech](https://platform.openai.com/docs/api-reference/audio/createSpeech)

## New Features
- **v1/v1.5:** Supports multi-character audio mixing: You can pass in multiple reference audios, and the TTS output character's voice will be a mixed version of the multiple reference audios (inputting multiple reference audios may cause the output character's voice to be unstable, you can "reroll" until you get a satisfactory voice and then use it as a reference audio).

## Performance
Word Error Rate (WER) Results for IndexTTS and Baseline Models on the [**seed-test**](https://github.com/BytedanceSpeech/seed-tts-eval)

| model                   | zh    | en    |
| ----------------------- | ----- | ----- |
| Human                   | 1.254 | 2.143 |
| index-tts (num_beams=3) | 1.005 | 1.943 |
| index-tts (num_beams=1) | 1.107 | 2.032 |
| index-tts-vllm      | 1.12  | 1.987 |

The performance of the original project is basically maintained.

## Concurrency Test
Refer to [`simple_test.py`](simple_test.py), the API service needs to be started first.