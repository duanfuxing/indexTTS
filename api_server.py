import os
import sys

# 添加vllm路径到sys.path
vllm_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vllm')
if vllm_path not in sys.path:
    sys.path.insert(0, vllm_path)

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 导入patch_vllm模块
import patch_vllm
import asyncio
import io
import traceback
import time
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
import numpy as np
import soundfile as sf
from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import argparse
import json
from pydantic import BaseModel, Field
from indextts.infer_vllm import IndexTTS
from utils.db_manager import DatabaseManager
from utils.redis_manager import RedisManager
from utils.tos_uploader import TOSUploader
from utils.logger import IndexTTSLogger

# 配置日志
logger = IndexTTSLogger.get_logger("api_server")

# 全局变量
tts = None
db_manager = None
redis_manager = None
tos_uploader = None

# 请求和响应的Pydantic模型
class OnlineTTSRequest(BaseModel):
    text: str = Field(..., max_length=300, description="要合成的文本（最多300字符）")
    voice: str = Field(..., description="音色名称")
    seed: Optional[int] = Field(8, description="随机种子")

class LongTextTTSRequest(BaseModel):
    text: str = Field(..., max_length=50000, description="要合成的文本（最多50000字符）")
    voice: str = Field(..., description="音色名称")
    callback_url: Optional[str] = Field(None, description="完成后的回调URL")
    metadata: Optional[Dict[str, Any]] = Field(None, description="额外的元数据")
    priority: Optional[int] = Field(0, description="任务优先级，数值越大优先级越高")

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    audio_url: Optional[str] = None
    srt_url: Optional[str] = None
    processing_time: Optional[float] = None
    text_length: Optional[int] = None
    duration: Optional[float] = None
    file_size: Optional[int] = None

def generate_srt_from_text(text: str, audio_duration: float) -> str:
    """根据文本和音频时长生成SRT字幕文件，支持智能断句"""
    # 首先按主要标点符号分割
    primary_sentences = text.replace('。', '。\n').replace('！', '！\n').replace('？', '？\n').split('\n')
    primary_sentences = [s.strip() for s in primary_sentences if s.strip()]
    
    if not primary_sentences:
        return ""
    
    # 进一步处理长句，按逗号、分号等次要标点分割
    final_sentences = []
    max_chars_per_subtitle = 25  # 每个字幕段最大字符数
    
    for sentence in primary_sentences:
        if len(sentence) <= max_chars_per_subtitle:
            final_sentences.append(sentence)
        else:
            # 长句按逗号、分号分割
            sub_parts = sentence.replace('，', '，\n').replace('；', '；\n').replace('、', '、\n').split('\n')
            sub_parts = [s.strip() for s in sub_parts if s.strip()]
            
            current_part = ""
            for part in sub_parts:
                # 如果当前部分加上新部分不超过限制，则合并
                if len(current_part + part) <= max_chars_per_subtitle:
                    current_part += part
                else:
                    # 否则先保存当前部分，开始新部分
                    if current_part:
                        final_sentences.append(current_part)
                    current_part = part
            
            # 添加最后一部分
            if current_part:
                final_sentences.append(current_part)
    
    if not final_sentences:
        return ""
    
    srt_content = []
    
    # 计算每个字幕段的时长（基于字符数比例分配）
    total_chars = sum(len(s) for s in final_sentences)
    current_time = 0.0
    
    for i, sentence in enumerate(final_sentences):
        # 根据字符数比例分配时间，但设置最小和最大时长
        char_ratio = len(sentence) / total_chars if total_chars > 0 else 1.0 / len(final_sentences)
        duration = audio_duration * char_ratio
        
        # 设置合理的时长范围：最短1.5秒，最长6秒
        duration = max(1.5, min(6.0, duration))
        
        start_time = current_time
        end_time = current_time + duration
        
        # 确保不超过总时长
        if end_time > audio_duration:
            end_time = audio_duration
        
        start_srt = format_srt_time(start_time)
        end_srt = format_srt_time(end_time)
        
        srt_content.append(f"{i + 1}")
        srt_content.append(f"{start_srt} --> {end_srt}")
        srt_content.append(sentence)
        srt_content.append("")
        
        current_time = end_time
    
    return "\n".join(srt_content)

def format_srt_time(seconds: float) -> str:
    """将秒数转换为SRT时间格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用程序生命周期管理器"""
    global tts, db_manager, redis_manager, tos_uploader
    
    # 初始化数据库
    db_manager = DatabaseManager()
    await db_manager.initialize()
    
    # 初始化Redis缓存
    redis_manager = RedisManager()
    await redis_manager.initialize()
    
    # 初始化TOS上传器
    try:
        tos_uploader = TOSUploader.from_env()
        logger.info("TOS上传器初始化成功")
    except Exception as e:
        logger.warning(f"TOS上传器初始化失败: {e}")
        tos_uploader = None

    # 初始化TTS模型
    tts = IndexTTS(model_dir=args.model_dir, gpu_memory_utilization=args.gpu_memory_utilization)
    
    # 加载音色配置
    current_file_path = os.path.abspath(__file__)
    cur_dir = os.path.dirname(current_file_path)
    # 修改speaker.json路径，指向vllm目录下的assets
    vllm_dir = os.path.join(cur_dir, 'vllm')
    speaker_path = os.path.join(vllm_dir, "assets/speaker.json")

    print("speaker_path:", speaker_path)

    if os.path.exists(speaker_path):
        speaker_dict = json.load(open(speaker_path, 'r'))
        for speaker, audio_paths in speaker_dict.items():
            audio_paths_ = []
            for audio_path in audio_paths:
                audio_paths_.append(os.path.join(vllm_dir, audio_path))
            tts.registry_speaker(speaker, audio_paths_)
    
    
    logger.info("应用程序启动完成")
    
    yield
    
    # 清理资源
    if db_manager:
        await db_manager.close()
    if redis_manager:
        await redis_manager.close()
    logger.info("应用程序关闭完成")

app = FastAPI(
    title="增强型TTS API服务器",
    description="TTS API服务器，支持在线合成和长文本队列处理",
    version="1.0.0",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """健康检查端点"""
    try:
        global tts, db_manager, redis_manager
        
        health_status = {
            "status": "healthy",
            "timestamp": time.time(),
            "services": {}
        }
        
        # 检查TTS服务
        if tts is None:
            health_status["services"]["tts"] = "unavailable"
            health_status["status"] = "unhealthy"
        else:
            health_status["services"]["tts"] = "available"
        
        # 检查数据库连接
        try:
            if db_manager:
                db_connected = await db_manager.check_connection()
                if db_connected:
                    health_status["services"]["database"] = "available"
                else:
                    health_status["services"]["database"] = "unavailable"
                    health_status["status"] = "unhealthy"
            else:
                health_status["services"]["database"] = "unavailable"
                health_status["status"] = "unhealthy"
        except Exception as e:
            health_status["services"]["database"] = f"error: {str(e)}"
            health_status["status"] = "unhealthy"
        
        # 检查Redis连接
        try:
            if redis_manager and await redis_manager.check_connection():
                health_status["services"]["redis"] = "available"
            else:
                health_status["services"]["redis"] = "unavailable"
                health_status["status"] = "unhealthy"
        except Exception as e:
            health_status["services"]["redis"] = f"error: {str(e)}"
            health_status["status"] = "unhealthy"
        
        status_code = 200 if health_status["status"] == "healthy" else 503
        return JSONResponse(status_code=status_code, content=health_status)
        
    except Exception as ex:
        import traceback
        error_details = {
            "message": str(ex),
            "traceback": traceback.format_exc()
        }
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(ex),
                "error_details": error_details,
                "timestamp": time.time()
            }
        )

@app.get("/voices")
async def get_voices():
    """获取可用音色列表端点"""
    try:
        # 优先从Redis缓存获取音色配置
        if redis_manager:
            cached_voices = await redis_manager.get_voice_configs()
            if cached_voices:
                return cached_voices
        
        current_file_path = os.path.abspath(__file__)
        cur_dir = os.path.dirname(current_file_path)
        # 修改speaker.json路径，指向vllm目录下的assets
        vllm_dir = os.path.join(os.path.dirname(cur_dir), 'vllm')
        speaker_path = os.path.join(vllm_dir, "assets/speaker.json")
        
        voice_data = None
        if os.path.exists(speaker_path):
            speaker_dict = json.load(open(speaker_path, 'r'))
            voice_data = {
                "voices": list(speaker_dict.keys()),
                "total": len(speaker_dict),
                "details": speaker_dict
            }
        else:
            voice_data = {
                "voices": [],
                "total": 0,
                "details": {}
            }
        
        # 将音色配置缓存到Redis（缓存1小时）
        if redis_manager and voice_data:
            await redis_manager.set_voice_configs(voice_data, expire=3600*24)
        
        return voice_data
        
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

@app.post("/tts/online", responses={
    200: {"content": {"application/octet-stream": {}}},
    500: {"content": {"application/json": {}}}
})
async def online_tts(request: OnlineTTSRequest):
    """在线TTS合成端点 - 限制300字，直接返回音频"""
    try:
        global tts, db_manager
        
        if not tts:
            raise HTTPException(status_code=503, detail="TTS service not available")
        
        # 创建数据库任务记录
        task_id = await db_manager.create_online_task(
            text=request.text,
            voice=request.voice,
            payload={"seed": request.seed}
        )
        
        start_time = time.time()
        
        # 执行TTS合成
        sr, wav_data = await tts.infer_with_ref_audio_embed(request.voice, request.text)
        
        processing_time = time.time() - start_time
        audio_duration = len(wav_data) / sr
        
        # 生成音频字节
        with io.BytesIO() as wav_buffer:
            sf.write(wav_buffer, wav_data, sr, format='WAV')
            wav_bytes = wav_buffer.getvalue()
        
        # 保存音频文件
        audio_file_path = db_manager.file_manager.save_audio_file(task_id, wav_bytes)
        
        # 生成SRT字幕（必须生成）
        srt_content = generate_srt_from_text(request.text, audio_duration)
        srt_file_path = db_manager.file_manager.save_srt_file(task_id, srt_content)
        
        # 上传文件到TOS并获取URL
        audio_url = None
        srt_url = None
        if tos_uploader:
            try:
                # 上传音频文件
                audio_url = tos_uploader.upload(audio_file_path, task_id)
                logger.info(f"音频文件上传成功: {audio_url}")
                
                # 上传SRT文件
                srt_url = tos_uploader.upload(srt_file_path, task_id)
                logger.info(f"SRT文件上传成功: {srt_url}")
            except Exception as e:
                logger.error(f"文件上传失败: {e}")
        
        # 更新任务文件路径
        await db_manager.update_task_files(
            task_id=task_id,
            audio_file_path=audio_file_path,
            srt_file_path=srt_file_path,
            audio_url=audio_url,
            srt_url=srt_url
        )
        
        # 更新任务状态
        await db_manager.update_task_status(
            task_id=task_id,
            status='completed',
            result={
                "sample_rate": sr,
                "duration": audio_duration,
                "task_id": task_id,
                "audio_url": audio_url,
                "srt_url": srt_url
            },
            srt=srt_content,
            processing_time=processing_time,
            actual_duration=int(audio_duration),
            file_size=len(wav_bytes),
            audio_url=audio_url,
            srt_url=srt_url
        )
        
        # 返回JSON响应，不包含音频和字幕内容
        return JSONResponse(content={
            "task_id": task_id,
            "sample_rate": sr,
            "duration": audio_duration,
            "processing_time": processing_time,
            "audio_url": audio_url,
            "srt_url": srt_url
        })
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as ex:
        tb_str = ''.join(traceback.format_exception(type(ex), ex, ex.__traceback__))
        logger.error(f"Online TTS error: {tb_str}")
        
        # 尝试更新任务状态为失败
        try:
            if 'task_id' in locals():
                await db_manager.update_task_status(
                    task_id=task_id,
                    status='failed',
                    error_message=str(ex)
                )
        except:
            pass
        
        raise HTTPException(status_code=500, detail=str(ex))

@app.post("/tts/task/submit")
async def submit_long_text_task(request: LongTextTTSRequest):
    """提交长文本TTS合成任务"""
    try:
        # 创建长文本任务
        task_id = await db_manager.create_long_text_task(
            text=request.text,
            voice=request.voice,
            payload={
                "priority": request.priority,
                "metadata": request.metadata
            },
            callback_url=request.callback_url
        )
        
        # 将任务推送到Redis队列
        task_data = {
            "task_id": task_id,
            "task_type": "long_text",
            "voice": request.voice,
            "priority": request.priority or 0
        }
        
        success = await redis_manager.push_task_to_queue("long_text", task_data, request.priority or 0)
        
        if not success:
            raise HTTPException(status_code=500, detail="任务提交失败")
        
        logger.info(f"长文本任务 {task_id} 已提交到队列")
        
        return {
            "task_id": task_id,
            "status": "pending",
            "message": "长文本合成任务已提交，请使用task_id查询处理状态",
            "text_length": len(request.text),
            "voice": request.voice,
            "priority": request.priority or 0
        }
        
    except Exception as e:
        logger.error(f"提交长文本任务失败: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"提交任务失败: {str(e)}")

@app.get("/tts/task/{task_id}")
async def get_task_status(task_id: str):
    """查询任务状态"""
    try:
        # 从数据库获取任务信息
        task_data = await db_manager.get_task(task_id)
        
        if not task_data:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        # 构建响应数据
        response_data = {
            "task_id": task_data["task_id"],
            "task_type": task_data["task_type"],
            "status": task_data["status"],
            "voice": task_data["voice"],
            "created_at": task_data["created_at"],
            "started_at": task_data.get("started_at"),
            "completed_at": task_data.get("completed_at"),
            "text_preview": task_data.get("text_preview"),
            "error_message": task_data.get("error_message")
        }
        
        # 如果任务已完成，添加结果信息
        if task_data["status"] == "completed":
            response_data.update({
                "audio_url": task_data.get("audio_url"),
                "srt_url": task_data.get("srt_url")
            })
        
        # 如果是长文本任务，添加队列信息
        if task_data["task_type"] == "long_text" and task_data["status"] == "pending":
            queue_length = await redis_manager.get_queue_length("long_text")
            response_data["queue_position"] = queue_length
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"查询任务状态失败: {str(e)}")

if __name__ == "__main__":
    # 配置参数
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "6006"))
    model_dir = os.getenv("MODEL_DIR", "checkpoints/Index-TTS-1.5-vLLM")
    gpu_memory_utilization = float(os.getenv("GPU_MEMORY_UTILIZATION", "0.40"))

    class Args:
        def __init__(self):
            self.host = host
            self.port = port
            self.model_dir = model_dir
            self.gpu_memory_utilization = gpu_memory_utilization
    
    args = Args()
    
    uvicorn.run(app=app, host=args.host, port=args.port)
else:
    # 当作为模块导入时的默认配置
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "6006"))
    model_dir = os.getenv("MODEL_DIR", "checkpoints/Index-TTS-1.5-vLLM")
    gpu_memory_utilization = float(os.getenv("GPU_MEMORY_UTILIZATION", "0.40"))
    
    class Args:
        def __init__(self):
            self.host = host
            self.port = port
            self.model_dir = model_dir
            self.gpu_memory_utilization = gpu_memory_utilization
    
    args = Args()