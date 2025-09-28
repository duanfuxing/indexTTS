import os
import asyncio
import io
import traceback
import time
import uuid
import logging
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
from server.database.db_manager import DatabaseManager
from server.cache.redis_manager import RedisManager
from server.tos_uploader import TOSUploader

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    # SRT字幕文件生成是必须的，不再作为可选参数
    # return_srt: Optional[bool] = Field(False, description="是否返回字幕文件")

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
        
        start_srt = format_srt_time(start_time)
        end_srt = format_srt_time(end_time)
        
        srt_content.append(f"{i + 1}")
        srt_content.append(f"{start_srt} --> {end_srt}")
        srt_content.append(sentence)
        srt_content.append("")
    
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
    
    # 初始化TTS模型
    cfg_path = os.path.join(args.model_dir, "config.yaml")
    tts = IndexTTS(model_dir=args.model_dir, cfg_path=cfg_path, gpu_memory_utilization=args.gpu_memory_utilization)
    
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
            tts.registry_speaker(speaker, audio_paths_)
    
    # 初始化数据库
    database_url = os.getenv('DATABASE_URL', 'mysql://user:password@localhost:3306/tts_db')
    db_manager = DatabaseManager(database_url)
    await db_manager.initialize()
    
    # 初始化Redis缓存
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    redis_manager = RedisManager(redis_url)
    await redis_manager.initialize()
    
    # 初始化TOS上传器
    try:
        tos_uploader = TOSUploader.from_env()
        logger.info("TOS上传器初始化成功")
    except Exception as e:
        logger.warning(f"TOS上传器初始化失败: {e}")
        tos_uploader = None
    
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
            if db_manager and db_manager.pool:
                stats = await db_manager.get_task_statistics()
                health_status["services"]["database"] = "available"
                health_status["task_stats"] = stats
            else:
                health_status["services"]["database"] = "unavailable"
                health_status["status"] = "unhealthy"
        except Exception as e:
            health_status["services"]["database"] = f"error: {str(e)}"
            health_status["status"] = "unhealthy"
        
        # 检查Redis连接
        try:
            if redis_manager and await redis_manager.ping():
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
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(ex),
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
        speaker_path = os.path.join(cur_dir, "assets/speaker.json")
        
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
            await redis_manager.set_voice_configs(voice_data, expire=3600)
        
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
                audio_url = tos_uploader.upload(audio_file_path, f"audio/{task_id}.wav")
                logger.info(f"音频文件上传成功: {audio_url}")
                
                # 上传SRT文件
                srt_url = tos_uploader.upload(srt_file_path, f"srt/{task_id}.srt")
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
        
        # 始终返回包含音频和SRT的JSON响应
        return JSONResponse(content={
            "task_id": task_id,
            "audio_base64": wav_bytes.hex(),  # 使用hex编码而不是base64以节省空间
            "srt": srt_content,
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

@app.post("/tts/long-text/submit")
async def submit_long_text_task(request: LongTextTTSRequest):
    """提交长文本TTS任务端点"""
    try:
        global db_manager
        
        if not db_manager:
            raise HTTPException(status_code=503, detail="Database service not available")
        
        # 创建长文本任务
        task_id = await db_manager.create_long_text_task(
            text=request.text,
            voice=request.voice,
            payload={
                "metadata": request.metadata
            },
            callback_url=request.callback_url
        )
        
        # 获取任务数据以添加到Redis队列
        task_info = await db_manager.get_task(task_id)
        if not task_info:
            raise HTTPException(status_code=500, detail="Failed to retrieve created task")
        
        # 获取完整文本内容
        full_text = await db_manager.get_task_text(task_info)
        
        task_data = {
            "task_id": task_id,
            "text": full_text,
            "voice": request.voice,
            "priority": request.priority,
            "callback_url": request.callback_url,
            "metadata": request.metadata
        }
        
        # 根据优先级选择队列
        queue_name = 'high_priority' if request.priority > 0 else 'long_text'
        await redis_manager.push_task_to_queue(queue_name, task_data)
        
        logger.info(f"创建长文本TTS任务: {task_id}，已添加到队列: {queue_name}")
        
        return {
            "task_id": task_id,
            "status": "pending",
            "message": "Task submitted successfully",
            "text_length": len(request.text),
            "estimated_processing_time": len(request.text) * 0.1  # 粗略估算
        }
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as ex:
        logger.error(f"Submit long text task error: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))

@app.get("/tts/long-text/status/{task_id}", response_model=TaskStatusResponse)
async def get_long_text_task_status(task_id: str):
    """查询长文本TTS任务状态端点"""
    try:
        global db_manager, redis_manager
        
        if not db_manager:
            raise HTTPException(status_code=503, detail="Database service not available")
        
        # 优先从Redis缓存获取任务状态
        if redis_manager:
            cached_task = await redis_manager.get_task_status(task_id)
            if cached_task:
                return TaskStatusResponse(**cached_task)
        
        # 缓存未命中，从数据库获取
        task_data = await db_manager.get_task_status(task_id)
        
        if not task_data:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # 将任务状态缓存到Redis
        if redis_manager:
            await redis_manager.set_task_status(task_id, task_data)
        
        return TaskStatusResponse(**task_data)
        
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Get task status error: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))

@app.get("/tts/long-text/result/{task_id}")
async def get_long_text_task_result(task_id: str):
    """获取长文本TTS任务结果端点（音频文件）"""
    try:
        global db_manager
        
        if not db_manager:
            raise HTTPException(status_code=503, detail="Database service not available")
        
        task_data = await db_manager.get_task_status(task_id)
        
        if not task_data:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task_data['status'] != 'completed':
            raise HTTPException(status_code=400, detail=f"Task not completed, current status: {task_data['status']}")
        
        # 获取任务文件路径信息
        file_paths = await db_manager.get_task_file_paths(task_id)
        
        if not file_paths or not file_paths.get('audio_file_path'):
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        # 从文件系统读取音频文件
        try:
            audio_data = db_manager.file_manager.read_audio_file(task_id)
            
            return Response(
                content=audio_data,
                media_type="audio/wav",
                headers={
                    "X-Task-ID": task_id,
                    "X-Duration": str(task_data.get('duration', 0)),
                    "X-File-Size": str(task_data.get('file_size', 0)),
                    "Content-Disposition": f"attachment; filename={task_id}.wav"
                }
            )
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Audio file not found on disk")
        except Exception as e:
            logger.error(f"Error reading audio file for task {task_id}: {e}")
            raise HTTPException(status_code=500, detail="Error reading audio file")
        
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Get task result error: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))

@app.get("/tts/long-text/srt/{task_id}")
async def get_long_text_task_srt(task_id: str):
    """获取长文本TTS任务字幕文件端点"""
    try:
        global db_manager
        
        if not db_manager:
            raise HTTPException(status_code=503, detail="Database service not available")
        
        task_data = await db_manager.get_task_status(task_id)
        
        if not task_data:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task_data['status'] != 'completed':
            raise HTTPException(status_code=400, detail=f"Task not completed, current status: {task_data['status']}")
        
        # 获取任务文件路径信息
        file_paths = await db_manager.get_task_file_paths(task_id)
        
        if not file_paths or not file_paths.get('srt_file_path'):
            raise HTTPException(status_code=404, detail="SRT file not found")
        
        # 从文件系统读取字幕文件
        try:
            srt_data = db_manager.file_manager.read_srt_file(task_id)
            
            return Response(
                content=srt_data,
                media_type="text/plain",
                headers={
                    "X-Task-ID": task_id,
                    "Content-Disposition": f"attachment; filename={task_id}.srt"
                }
            )
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="SRT file not found on disk")
        except Exception as e:
            logger.error(f"Error reading SRT file for task {task_id}: {e}")
            raise HTTPException(status_code=500, detail="Error reading SRT file")
        
    except HTTPException:
        raise
    except Exception as ex:
        logger.error(f"Get task SRT error: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))

# 保持原有的兼容性API
@app.post("/tts", responses={
    200: {"content": {"application/octet-stream": {}}},
    500: {"content": {"application/json": {}}}
})
async def tts_api_legacy(request: Request):
    """保持与原有API的兼容性"""
    try:
        data = await request.json()
        text = data["text"]
        character = data["character"]
        
        # 使用新的在线TTS API
        online_request = OnlineTTSRequest(text=text, voice=character)
        return await online_tts(online_request)
        
    except Exception as ex:
        tb_str = ''.join(traceback.format_exception(type(ex), ex, ex.__traceback__))
        logger.error(f"Legacy TTS API error: {tb_str}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": str(tb_str)
            }
        )

@app.get("/audio/voices")
async def tts_voices_legacy():
    """保持与原有API的兼容性"""
    return await get_voices()

@app.post("/audio/speech", responses={
    200: {"content": {"application/octet-stream": {}}},
    500: {"content": {"application/json": {}}}
})
async def tts_api_openai_legacy(request: Request):
    """OpenAI兼容API"""
    try:
        data = await request.json()
        text = data["input"]
        character = data["voice"]
        
        # 使用新的在线TTS API
        online_request = OnlineTTSRequest(text=text, voice=character)
        return await online_tts(online_request)
        
    except Exception as ex:
        tb_str = ''.join(traceback.format_exception(type(ex), ex, ex.__traceback__))
        logger.error(f"OpenAI compatible API error: {tb_str}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": str(tb_str)
            }
        )

if __name__ == "__main__":
    # 从环境变量读取配置参数
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "6006"))
    model_dir = os.getenv("MODEL_DIR", "/path/to/IndexTeam/Index-TTS")
    gpu_memory_utilization = float(os.getenv("GPU_MEMORY_UTILIZATION", "0.40"))
    
    # 创建args对象以保持兼容性
    class Args:
        def __init__(self):
            self.host = host
            self.port = port
            self.model_dir = model_dir
            self.gpu_memory_utilization = gpu_memory_utilization
    
    args = Args()
    
    uvicorn.run(app=app, host=args.host, port=args.port)