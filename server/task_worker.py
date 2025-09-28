#!/usr/bin/env python3
"""
长文本TTS任务处理器

此处理器从数据库队列中处理长文本TTS任务。
它处理文本分块、音频生成和结果存储。
"""

import os
import asyncio
import io
import time
import uuid
import logging
import signal
import sys
from typing import Optional
import traceback
import json
from pathlib import Path

import soundfile as sf
import requests
from indextts.infer_vllm import IndexTTS

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent.parent))

from .database.db_manager import DatabaseManager
from .cache.redis_manager import RedisManager
from .config import config
from .tos_uploader import TOSUploader

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TTSTaskWorker:
    """长文本TTS任务处理器"""
    
    def __init__(self, worker_id: str, model_dir: str, database_url: str, 
                 gpu_memory_utilization: float = 0.25, audio_output_dir: str = "./audio_output"):
        self.worker_id = worker_id
        self.model_dir = model_dir
        self.database_url = database_url
        self.gpu_memory_utilization = gpu_memory_utilization
        self.audio_output_dir = audio_output_dir
        
        self.tts = None
        self.db_manager = None
        self.redis_manager = None
        self.running = False
        self.current_task = None
        
        # 确保音频输出目录存在
        os.makedirs(self.audio_output_dir, exist_ok=True)
        
        # 设置SRT文件存储目录
        self.srt_output_dir = config.SRT_OUTPUT_DIR
        os.makedirs(self.srt_output_dir, exist_ok=True)
    
    async def initialize(self):
        """初始化TTS模型和数据库连接"""
        try:
            # 初始化TTS模型
            cfg_path = os.path.join(self.model_dir, "config.yaml")
            self.tts = IndexTTS(
                model_dir=self.model_dir, 
                cfg_path=cfg_path, 
                gpu_memory_utilization=self.gpu_memory_utilization
            )
            
            # 加载音色配置
            current_file_path = os.path.abspath(__file__)
            cur_dir = os.path.dirname(current_file_path)
            speaker_path = os.path.join(cur_dir, "assets/speaker.json")
            if os.path.exists(speaker_path):
                speaker_dict = json.load(open(speaker_path, 'r'))
                for speaker, audio_paths in speaker_dict.items():
                    audio_paths_ = []
                    for audio_path in audio_paths:
                        audio_paths_.append(os.path.join(cur_dir, audio_path))
                    self.tts.registry_speaker(speaker, audio_paths_)
                logger.info(f"已加载 {len(speaker_dict)} 个音色")
            
            # 初始化数据库连接
            self.db_manager = DatabaseManager()
            await self.db_manager.initialize()
            
            # 初始化Redis连接
            self.redis_manager = RedisManager()
            await self.redis_manager.initialize()
            
            # 初始化TOS上传器
            try:
                self.tos_uploader = TOSUploader.from_env()
                logger.info("TOS上传器初始化成功")
            except Exception as e:
                logger.warning(f"TOS上传器初始化失败: {e}，将跳过文件上传")
                self.tos_uploader = None
            
            logger.info(f"处理器 {self.worker_id} 初始化成功")
            
        except Exception as e:
            logger.error(f"处理器 {self.worker_id} 初始化失败: {e}")
            raise
    
    async def cleanup(self):
        """清理资源"""
        if self.db_manager:
            await self.db_manager.close()
        if self.redis_manager:
            await self.redis_manager.close()
        logger.info(f"处理器 {self.worker_id} 资源清理完成")
    
    def generate_srt_from_text(self, text: str, audio_duration: float) -> str:
        """根据文本和音频时长生成简单的SRT字幕文件"""
        # 简单的字幕生成逻辑，将文本按句子分割
        sentences = text.replace('。', '。\n').replace('！', '！\n').replace('？', '？\n').split('\n')
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return ""
        
        srt_content = []
        time_per_sentence = audio_duration / len(sentences)
        
        for i, sentence in enumerate(sentences):
            start_time = i * time_per_sentence
            end_time = (i + 1) * time_per_sentence
            
            start_srt = self.format_srt_time(start_time)
            end_srt = self.format_srt_time(end_time)
            
            srt_content.append(f"{i + 1}")
            srt_content.append(f"{start_srt} --> {end_srt}")
            srt_content.append(sentence)
            srt_content.append("")
        
        return "\n".join(srt_content)
    
    def format_srt_time(self, seconds: float) -> str:
        """将秒数转换为SRT时间格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    async def send_callback(self, callback_url: str, task_data: dict):
        """发送任务完成回调"""
        try:
            response = requests.post(
                callback_url,
                json=task_data,
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            logger.info(f"回调发送成功到 {callback_url}")
        except Exception as e:
            logger.error(f"发送回调失败到 {callback_url}: {e}")
    
    async def process_task(self, task_data: dict) -> bool:
        """处理单个TTS任务"""
        task_id = task_data['task_id']
        voice = task_data['voice']
        payload = task_data.get('payload', {})
        
        # 从数据库获取完整文本内容
        text = await self.db_manager.get_task_text(task_data)
        
        logger.info(f"正在处理任务 {task_id}，音色: {voice}，文本长度: {len(text)}")
        
        try:
            start_time = time.time()
            
            # 执行TTS合成
            sr, wav_data = await self.tts.infer_with_ref_audio_embed(voice, text)
            
            processing_time = time.time() - start_time
            audio_duration = len(wav_data) / sr
            
            # 生成音频字节数据
            with io.BytesIO() as wav_buffer:
                sf.write(wav_buffer, wav_data, sr, format='WAV')
                wav_bytes = wav_buffer.getvalue()
            
            # 使用文件管理器保存音频文件
            audio_file_path = self.db_manager.file_manager.save_audio_file(task_id, wav_bytes)
            
            # 生成SRT字幕文件
            srt_content = self.generate_srt_from_text(text, audio_duration)
            
            # 使用文件管理器保存SRT文件
            srt_file_path = self.db_manager.file_manager.save_srt_file(task_id, srt_content)
            
            # 上传文件到TOS并获取URL
            audio_url = None
            srt_url = None
            
            if self.tos_uploader:
                try:
                    # 上传音频文件
                    audio_object_key = await asyncio.get_event_loop().run_in_executor(
                        None, self.tos_uploader.upload, audio_file_path
                    )
                    audio_url = f"https://{self.tos_uploader.bucket}.{self.tos_uploader.client.endpoint.replace('https://', '')}/{audio_object_key}"
                    logger.info(f"音频文件上传成功: {audio_url}")
                    
                    # 上传字幕文件
                    srt_object_key = await asyncio.get_event_loop().run_in_executor(
                        None, self.tos_uploader.upload, srt_file_path
                    )
                    srt_url = f"https://{self.tos_uploader.bucket}.{self.tos_uploader.client.endpoint.replace('https://', '')}/{srt_object_key}"
                    logger.info(f"字幕文件上传成功: {srt_url}")
                    
                except Exception as e:
                    logger.error(f"文件上传失败: {e}")
            
            # 更新任务文件路径和URL
            await self.db_manager.update_task_files(
                task_id=task_id,
                audio_file_path=audio_file_path,
                audio_url=audio_url,
                srt_file_path=srt_file_path,
                srt_url=srt_url
            )
            
            # 更新任务状态为完成
            await self.db_manager.update_task_status(
                task_id=task_id,
                status='completed',
                result={
                    "sample_rate": sr,
                    "duration": audio_duration,
                    "task_id": task_id,
                    "audio_url": audio_url,
                    "srt_url": srt_url
                },
                processing_time=processing_time,
                actual_duration=int(audio_duration),
                file_size=len(wav_bytes),
                audio_url=audio_url,
                srt_url=srt_url
            )
            
            logger.info(f"任务 {task_id} 处理成功，耗时 {processing_time:.2f}秒")
            
            # 发送回调（如果有）
            callback_url = task_data.get('callback_url')
            if callback_url:
                callback_data = {
                    "task_id": task_id,
                    "status": "completed",
                    "audio_url": audio_url,
                    "srt_url": srt_url,
                    "processing_time": processing_time,
                    "duration": audio_duration,
                    "file_size": len(wav_bytes)
                }
                await self.send_callback(callback_url, callback_data)
            
            return True
            
        except Exception as e:
            error_msg = str(e)
            tb_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            logger.error(f"任务 {task_id} 处理失败: {tb_str}")
            
            # 更新任务状态为失败
            await self.db_manager.update_task_status(
                task_id=task_id,
                status='failed',
                error_message=error_msg
            )
            
            # 发送失败回调（如果有）
            callback_url = task_data.get('callback_url')
            if callback_url:
                callback_data = {
                    "task_id": task_id,
                    "status": "failed",
                    "error": error_msg
                }
                await self.send_callback(callback_url, callback_data)
            
            return False
    
    async def run(self, task_type: Optional[str] = None, poll_interval: float = 1.0):
        """运行任务处理循环"""
        self.running = True
        logger.info(f"处理器 {self.worker_id} 已启动，处理 {task_type or '所有'} 类型任务")
        
        consecutive_empty_polls = 0
        max_empty_polls = 10  # 连续10次没有任务时增加轮询间隔
        
        while self.running:
            try:
                # 优先从Redis队列获取任务
                task_data = await self.redis_manager.pop_task_from_queue('online')
                
                if not task_data:
                    # Redis队列为空时从数据库获取任务
                    task_data = await self.db_manager.get_next_task(task_type)
                
                if task_data:
                    consecutive_empty_polls = 0
                    self.current_task = task_data
                    
                    # 处理任务
                    success = await self.process_task(task_data)
                    
                    self.current_task = None
                    
                    if success:
                        logger.info(f"处理器 {self.worker_id} 完成任务 {task_data['task_id']}")
                    else:
                        logger.error(f"处理器 {self.worker_id} 处理任务失败 {task_data['task_id']}")
                else:
                    consecutive_empty_polls += 1
                    # 没有任务时，逐渐增加轮询间隔以减少数据库负载
                    if consecutive_empty_polls > max_empty_polls:
                        await asyncio.sleep(poll_interval * 2)
                    else:
                        await asyncio.sleep(poll_interval)
                
            except Exception as e:
                logger.error(f"处理器 {self.worker_id} 主循环错误: {e}")
                await asyncio.sleep(poll_interval * 2)  # 出错时等待更长时间
        
        logger.info(f"处理器 {self.worker_id} 已停止")
    
    def stop(self):
        """停止任务处理"""
        self.running = False
        logger.info(f"处理器 {self.worker_id} 收到停止请求")

async def main():
    import uuid
    
    # 从环境变量读取配置参数
    worker_id = os.getenv("WORKER_ID") or f"worker-{uuid.uuid4().hex[:8]}"
    model_dir = os.getenv("MODEL_DIR", "/path/to/IndexTeam/Index-TTS")
    database_url = os.getenv("DATABASE_URL", "mysql://user:password@localhost:3306/tts_db")
    gpu_memory_utilization = float(os.getenv("GPU_MEMORY_UTILIZATION", "0.40"))
    audio_output_dir = os.getenv("AUDIO_OUTPUT_DIR", "./audio_output")
    task_type = os.getenv("TASK_TYPE")  # 可选参数
    poll_interval = float(os.getenv("POLL_INTERVAL", "1.0"))
    
    # 创建worker
    worker = TTSTaskWorker(
        worker_id=worker_id,
        model_dir=model_dir,
        database_url=database_url,
        gpu_memory_utilization=gpu_memory_utilization,
        audio_output_dir=audio_output_dir
    )
    
    # 设置信号处理
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，正在停止处理器...")
        worker.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 初始化worker
        await worker.initialize()
        
        # 运行worker
        await worker.run(task_type=task_type, poll_interval=poll_interval)
        
    except KeyboardInterrupt:
        logger.info("收到键盘中断信号")
    except Exception as e:
        logger.error(f"处理器错误: {e}")
    finally:
        await worker.cleanup()

if __name__ == "__main__":
    asyncio.run(main())