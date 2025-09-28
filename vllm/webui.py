import os
import sys
import threading
import time

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
sys.path.append(os.path.join(current_dir, "indextts"))

import gradio as gr

from indextts.infer_vllm import IndexTTS

import argparse
parser = argparse.ArgumentParser(description="IndexTTS WebUI")
parser.add_argument("--port", type=int, default=6006, help="Port to run the web UI on")
parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to run the web UI on")
parser.add_argument("--version", type=str, default="1.0", help="Host to run the web UI on")
parser.add_argument("--model_dir", type=str, default="", help="Model checkpoints directory")
parser.add_argument("--gpu_memory_utilization", type=float, default=0.25, help="Port to run the web UI on")
cmd_args = parser.parse_args()

CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
model_dir = None
if cmd_args.model_dir:
    model_dir = cmd_args.model_dir
else:
    if cmd_args.version == "1.0":
        model_dir = os.path.join(CURRENT_DIR, "checkpoints/Index-TTS-vLLM")
    elif cmd_args.version == "1.5":
        model_dir = os.path.join(CURRENT_DIR, "checkpoints/Index-TTS-1.5-vLLM")


async def gen_single(prompts, text, progress=gr.Progress()):
    output_path = None
    tts.gr_progress = progress
    
    if isinstance(prompts, list):
        prompt_paths = [prompt.name for prompt in prompts if prompt is not None]
    else:
        prompt_paths = [prompts.name] if prompts is not None else []
    
    output = await tts.infer(prompt_paths, text, output_path, verbose=True)
    return gr.update(value=output, visible=True)

def update_prompt_audio():
    return gr.update(interactive=True)


if __name__ == "__main__":
    tts = IndexTTS(model_dir=model_dir, gpu_memory_utilization=cmd_args.gpu_memory_utilization)

    with gr.Blocks() as demo:
        mutex = threading.Lock()
        gr.HTML('''
        <h2><center>IndexTTS: An Industrial-Level Controllable and Efficient Zero-Shot Text-To-Speech System</h2>
        <h2><center>(一款工业级可控且高效的零样本文本转语音系统)</h2>

    <p align="center">
    <a href='https://arxiv.org/abs/2502.05512'><img src='https://img.shields.io/badge/ArXiv-2502.05512-red'></a>
        ''')
        with gr.Tab("音频生成"):
            with gr.Row():
                # 使用 gr.File 替代 gr.Audio 来支持多文件上传
                prompt_audio = gr.File(
                    label="请上传参考音频（可上传多个）",
                    file_count="multiple",
                    file_types=["audio"]
                )
                with gr.Column():
                    input_text_single = gr.TextArea(label="请输入目标文本", key="input_text_single")
                    gen_button = gr.Button("生成语音", key="gen_button", interactive=True)
                output_audio = gr.Audio(label="生成结果", visible=True, key="output_audio")

        prompt_audio.upload(
            update_prompt_audio,
            inputs=[],
            outputs=[gen_button]
        )

        gen_button.click(
            gen_single,
            inputs=[prompt_audio, input_text_single],
            outputs=[output_audio]
        )

    demo.queue(20)
    demo.launch(server_name=cmd_args.host, server_port=cmd_args.port)