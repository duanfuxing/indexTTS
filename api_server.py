import os
import sys

# 添加vllm路径到sys.path
vllm_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vllm')
if vllm_path not in sys.path:
    sys.path.insert(0, vllm_path)

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 导入配置
from utils.config import config

# 导入patch_vllm模块
import patch_vllm
import asyncio
import io
import traceback
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import numpy as np
import soundfile as sf
from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks, Depends, Header
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
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
from utils.subtitle_generator import SubtitleGenerator

# 初始化日志系统
IndexTTSLogger.setup_logging()

# 配置日志
logger = IndexTTSLogger.get_logger("api_server")

# API密钥验证
security = HTTPBearer(auto_error=False)

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证API密钥"""
    if not config.API_KEY:
        # 如果没有配置API_KEY，则不进行验证
        return True
    
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail={
                "status": "error",
                "msg": "缺少API密钥",
                "data": None
            }
        )
    
    if credentials.credentials != config.API_KEY:
        raise HTTPException(
            status_code=401,
            detail={
                "status": "error", 
                "msg": "无效的API密钥",
                "data": None
            }
        )
    
    return True

# 速率限制功能
async def check_rate_limit(request: Request):
    """检查速率限制"""
    if not redis_manager:
        # 如果Redis不可用，跳过速率限制
        return True
    
    # 获取客户端IP
    client_ip = request.client.host
    if "x-forwarded-for" in request.headers:
        client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
    elif "x-real-ip" in request.headers:
        client_ip = request.headers["x-real-ip"]
    
    # 速率限制键
    rate_limit_key = f"rate_limit:{client_ip}"
    
    try:
        # 获取当前计数
        current_count = await redis_manager.get_cache(rate_limit_key)
        
        if current_count is None:
            # 第一次请求，设置计数为1，过期时间为1分钟
            await redis_manager.set_cache(rate_limit_key, "1", expire=60)
            return True
        
        current_count = int(current_count)
        
        if current_count >= config.RATE_LIMIT_PER_MINUTE:
            raise HTTPException(
                status_code=429,
                detail={
                    "status": "error",
                    "msg": f"请求过于频繁，每分钟最多{config.RATE_LIMIT_PER_MINUTE}次请求",
                    "data": {
                        "rate_limit": config.RATE_LIMIT_PER_MINUTE,
                        "current_count": current_count,
                        "reset_time": 60
                    }
                }
            )
        
        # 增加计数
        await redis_manager.increment_counter(rate_limit_key)
        return True
        
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"速率限制检查失败: {e}")
        # 如果速率限制检查失败，允许请求通过
        return True

# 全局变量
tts = None
db_manager = None
redis_manager = None
tos_uploader = None
subtitle_generator = None

# 请求和响应的Pydantic模型
class OnlineTTSRequest(BaseModel):
    text: str = Field(..., max_length=config.MAX_ONLINE_TEXT_LENGTH, description=f"要合成的文本（最多{config.MAX_ONLINE_TEXT_LENGTH}字符）")
    voice: str = Field(..., description="音色名称")
    seed: Optional[int] = Field(8, description="随机种子")

class LongTextTTSRequest(BaseModel):
    text: str = Field(..., max_length=config.MAX_LONG_TEXT_LENGTH, description=f"要合成的文本（最多{config.MAX_LONG_TEXT_LENGTH}字符）")
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用程序生命周期管理器"""
    global tts, db_manager, redis_manager, tos_uploader, subtitle_generator
    
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

    # 初始化字幕生成器
    subtitle_generator = SubtitleGenerator()
    
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
    allow_origins=config.ALLOWED_ORIGINS,
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
            "healthy": True,
            "timestamp": time.time(),
            "services": {}
        }
        
        # 检查TTS服务
        if tts is None:
            health_status["services"]["tts"] = "unavailable"
            health_status["healthy"] = False
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
                    health_status["healthy"] = False
            else:
                health_status["services"]["database"] = "unavailable"
                health_status["healthy"] = False
        except Exception as e:
            health_status["services"]["database"] = f"error: {str(e)}"
            health_status["healthy"] = False
        
        # 检查Redis连接
        try:
            if redis_manager and await redis_manager.check_connection():
                health_status["services"]["redis"] = "available"
            else:
                health_status["services"]["redis"] = "unavailable"
                health_status["healthy"] = False
        except Exception as e:
            health_status["services"]["redis"] = f"error: {str(e)}"
            health_status["healthy"] = False
        
        # 构建统一响应格式
        response_data = {
            "status": "success" if health_status["healthy"] else "error",
            "msg": "服务运行正常" if health_status["healthy"] else "部分服务不可用",
            "data": health_status
        }
        
        status_code = 200 if health_status["healthy"] else 503
        return JSONResponse(status_code=status_code, content=response_data)
        
    except Exception as ex:
        import traceback
        error_details = {
            "message": str(ex),
            "traceback": traceback.format_exc()
        }
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "msg": f"健康检查失败: {str(ex)}",
                "data": {
                    "error_details": error_details,
                    "timestamp": time.time()
                }
            }
        )

@app.get("/voices")
async def get_voices(request: Request, auth: bool = Depends(verify_api_key), rate_limit: bool = Depends(check_rate_limit)):
    """获取可用音色列表端点"""
    try:
        # 优先从Redis缓存获取音色配置
        if redis_manager:
            cached_voices = await redis_manager.get_voice_configs()
            if cached_voices:
                # 如果缓存数据已经是新格式，直接返回
                if isinstance(cached_voices, dict) and "status" in cached_voices:
                    return cached_voices
                # 如果是旧格式，包装成新格式
                return {
                    "status": "success",
                    "msg": "获取音色列表成功",
                    "data": cached_voices
                }
        
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
        
        # 构建统一响应格式
        response_data = {
            "status": "success",
            "msg": "获取音色列表成功",
            "data": voice_data
        }
        
        return response_data
        
    except Exception as ex:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "msg": f"获取音色列表失败: {str(ex)}",
                "data": None
            }
        )

@app.post("/tts/online", responses={
    200: {"content": {"application/octet-stream": {}}},
    500: {"content": {"application/json": {}}}
})
async def online_tts(request_data: OnlineTTSRequest, request: Request, auth: bool = Depends(verify_api_key), rate_limit: bool = Depends(check_rate_limit)):
    """在线TTS合成端点 - 限制300字，直接返回音频"""
    try:
        global tts, db_manager
        
        if not tts:
            raise HTTPException(status_code=503, detail="TTS service not available")
        
        # 创建数据库任务记录
        task_id = await db_manager.create_online_task(
            text=request_data.text,
            voice=request_data.voice,
            payload={"seed": request_data.seed}
        )
        
        start_time = time.time()
        
        # 执行TTS推理
        sr, wav_data = await tts.infer_with_ref_audio_embed(request_data.voice, request_data.text)
        
        processing_time = time.time() - start_time
        audio_duration = len(wav_data) / sr
        
        # 生成音频字节
        with io.BytesIO() as wav_buffer:
            sf.write(wav_buffer, wav_data, sr, format='WAV')
            wav_bytes = wav_buffer.getvalue()
        
        # 保存音频文件
        audio_file_path = db_manager.file_manager.save_audio_file(task_id, wav_bytes)
        
        # 生成字幕
        srt_content = subtitle_generator.generate_srt_from_text(request_data.text, audio_duration)
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
            "status": "success",
            "msg": "TTS合成成功",
            "data": {
                "task_id": task_id,
                "sample_rate": sr,
                "duration": audio_duration,
                "processing_time": processing_time,
                "audio_url": audio_url,
                "srt_url": srt_url
            }
        })
        
    except ValueError as ve:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "msg": f"请求参数错误: {str(ve)}",
                "data": None
            }
        )
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
        
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "msg": f"TTS合成失败: {str(ex)}",
                "data": None
            }
        )

@app.post("/tts/task/submit")
async def submit_long_text_task(request_data: LongTextTTSRequest, request: Request, auth: bool = Depends(verify_api_key), rate_limit: bool = Depends(check_rate_limit)):
    """提交长文本TTS合成任务"""
    try:
        # 创建长文本任务
        task_id = await db_manager.create_long_text_task(
            text=request_data.text,
            voice=request_data.voice,
            payload={
                "priority": request_data.priority,
                "metadata": request_data.metadata
            },
            callback_url=request_data.callback_url
        )
        
        # 将任务推送到Redis队列
        task_data = {
            "task_id": task_id,
            "task_type": "long_text",
            "voice": request_data.voice,
            "priority": request_data.priority or 0
        }
        
        success = await redis_manager.push_task_to_queue("long_text", task_data, request_data.priority or 0)
        
        if not success:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "msg": "任务提交失败",
                    "data": None
                }
            )
        
        logger.info(f"长文本任务 {task_id} 已提交到队列")
        
        return JSONResponse(content={
            "status": "success",
            "msg": "长文本合成任务已提交成功",
            "data": {
                "task_id": task_id,
                "task_status": "pending",
                "message": "长文本合成任务已提交，请使用task_id查询处理状态",
                "text_length": len(request_data.text),
                "voice": request_data.voice,
                "priority": request_data.priority or 0
            }
        })
        
    except Exception as e:
        logger.error(f"提交长文本任务失败: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "msg": f"提交任务失败: {str(e)}",
                "data": None
            }
        )

@app.get("/tts/task/{task_id}")
async def get_task_status(task_id: str, request: Request, auth: bool = Depends(verify_api_key), rate_limit: bool = Depends(check_rate_limit)):
    """查询任务状态"""
    try:
        # 从数据库获取任务信息
        task_data = await db_manager.get_task(task_id)
        
        if not task_data:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "msg": "任务不存在",
                    "data": None
                }
            )
        
        # 构建响应数据
        task_info = {
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
            task_info.update({
                "audio_url": task_data.get("audio_url"),
                "srt_url": task_data.get("srt_url")
            })
        
        # 如果是长文本任务，添加队列信息
        if task_data["task_type"] == "long_text" and task_data["status"] == "pending":
            queue_length = await redis_manager.get_queue_length("long_text")
            task_info["queue_position"] = queue_length
        
        return JSONResponse(content={
            "status": "success",
            "msg": "查询任务状态成功",
            "data": task_info
        })
        
    except HTTPException as he:
        # 如果是已经处理过的HTTPException，直接返回对应的JSONResponse
        if he.status_code == 404:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "error",
                    "msg": "任务不存在",
                    "data": None
                }
            )
        else:
            return JSONResponse(
                status_code=he.status_code,
                content={
                    "status": "error",
                    "msg": he.detail,
                    "data": None
                }
            )
    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "msg": f"查询任务状态失败: {str(e)}",
                "data": None
            }
        )

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