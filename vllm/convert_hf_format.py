import os
from omegaconf import OmegaConf
import torch
# from indextts.gpt.model import UnifiedVoice
from indextts.gpt.model_v2 import UnifiedVoice
from indextts.utils.checkpoint import load_checkpoint
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--model_dir", type=str, default="")
args = parser.parse_args()

model_dir = args.model_dir
cfg_path = os.path.join(model_dir, "config.yaml")
gpt_save_dir = os.path.join(model_dir, "gpt")

cfg = OmegaConf.load(cfg_path)
gpt = UnifiedVoice(**cfg.gpt)
gpt_path = os.path.join(model_dir, cfg.gpt_checkpoint)
load_checkpoint(gpt, gpt_path)
gpt = gpt.to(device="cuda", dtype=torch.float16)
gpt.eval()  # .half()
gpt.post_init_gpt2_config()
print(">> GPT weights restored from:", gpt_path)

gpt.inference_model.save_pretrained(gpt_save_dir, safe_serialization=False)
print(f"GPT transformer saved to {gpt_save_dir}")


# from safetensors.torch import load_file

# # 加载模型参数
# model_path = os.path.join(gpt_save_dir, "pytorch_model.bin")
# state_dict = load_file(model_path)

# # 打印所有参数名
# for key in state_dict.keys():
#     print(key)
