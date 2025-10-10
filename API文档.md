# TTS API 接口文档

## 概述

本文档描述了TTS（Text-to-Speech）API服务器提供的所有接口，包括在线TTS合成、长文本任务处理、任务状态查询等功能。

**服务地址：** `http://localhost:6006`

**API版本：** v1.0.0

---

## 1. 健康检查接口

### 接口信息
- **路径：** `GET /health`
- **描述：** 检查TTS服务、数据库和Redis连接的健康状态
- **认证：** 无需认证

### 请求参数
无

### 响应参数
```json
{
  "status": "healthy",
  "timestamp": "2025-10-10T14:00:00",
  "services": {
    "tts": "available",
    "database": "connected", 
    "redis": "connected"
  }
}
```

### 响应字段说明
| 字段 | 类型 | 描述 |
|------|------|------|
| status | string | 整体健康状态：healthy/unhealthy |
| timestamp | string | 检查时间戳 |
| services.tts | string | TTS服务状态：available/unavailable |
| services.database | string | 数据库连接状态：connected/disconnected |
| services.redis | string | Redis连接状态：connected/disconnected |

---

## 2. 获取可用音色接口

### 接口信息
- **路径：** `GET /voices`
- **描述：** 获取系统中可用的音色配置列表
- **认证：** 无需认证

### 请求参数
无

### 响应参数
```json
{
  "voices": [
    {
      "name": "xiaomeng",
      "description": "小萌音色",
      "language": "zh-CN"
    },
    {
      "name": "yunxi", 
      "description": "云希音色",
      "language": "zh-CN"
    }
  ],
  "total": 2
}
```

### 响应字段说明
| 字段 | 类型 | 描述 |
|------|------|------|
| voices | array | 音色列表 |
| voices[].name | string | 音色名称标识符 |
| voices[].description | string | 音色描述 |
| voices[].language | string | 支持的语言 |
| total | integer | 可用音色总数 |

---

## 3. 在线TTS合成接口

### 接口信息
- **路径：** `POST /tts/online`
- **描述：** 在线TTS合成，限制300字符，直接返回音频文件URL和字幕文件URL
- **认证：** 无需认证

### 请求参数
```json
{
  "text": "要合成的文本内容",
  "voice": "xiaomeng",
  "seed": 8
}
```

### 请求字段说明
| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| text | string | 是 | 要合成的文本，最多300字符 |
| voice | string | 是 | 音色名称（如：xiaomeng, yunxi） |
| seed | integer | 否 | 随机种子，默认为8 |

### 响应参数
```json
{
  "task_id": "7a5186872526488e95de0bc6f8fe69fe",
  "sample_rate": 24000,
  "duration": 3.3635,
  "processing_time": 1.357893943786621,
  "audio_url": "https://aigc-omni.tos-cn-guangzhou.volces.com/7a5186872526488e95de0bc6f8fe69fe/7a5186872526488e95de0bc6f8fe69fe.wav",
  "srt_url": "https://aigc-omni.tos-cn-guangzhou.volces.com/7a5186872526488e95de0bc6f8fe69fe/7a5186872526488e95de0bc6f8fe69fe.srt"
}
```

### 响应字段说明
| 字段 | 类型 | 描述 |
|------|------|------|
| task_id | string | 任务唯一标识符 |
| sample_rate | integer | 音频采样率 |
| duration | float | 音频时长（秒） |
| processing_time | float | 处理耗时（秒） |
| audio_url | string | 音频文件下载URL |
| srt_url | string | 字幕文件下载URL |

---

## 4. 长文本任务提交接口

### 接口信息
- **路径：** `POST /tts/task/submit`
- **描述：** 提交长文本TTS合成任务到队列处理
- **认证：** 无需认证

### 请求参数
```json
{
  "text": "要合成的长文本内容",
  "voice": "xiaomeng",
  "callback_url": "https://your-callback-url.com/webhook",
  "metadata": {
    "user_id": "123",
    "custom_field": "value"
  },
  "priority": 1
}
```

### 请求字段说明
| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| text | string | 是 | 要合成的文本，最多50000字符 |
| voice | string | 是 | 音色名称 |
| callback_url | string | 否 | 任务完成后的回调URL |
| metadata | object | 否 | 额外的元数据 |
| priority | integer | 否 | 任务优先级，数值越大优先级越高，默认为0 |

### 响应参数
```json
{
  "task_id": "29889eb0ed1341d68675290d3167cd1e",
  "status": "pending",
  "message": "长文本合成任务已提交，请使用task_id查询处理状态",
  "text_length": 1500,
  "voice": "xiaomeng",
  "priority": 1
}
```

### 响应字段说明
| 字段 | 类型 | 描述 |
|------|------|------|
| task_id | string | 任务唯一标识符 |
| status | string | 任务状态：pending |
| message | string | 提示信息 |
| text_length | integer | 文本长度 |
| voice | string | 使用的音色 |
| priority | integer | 任务优先级 |

---

## 5. 任务状态查询接口

### 接口信息
- **路径：** `GET /tts/task/{task_id}`
- **描述：** 查询指定任务的处理状态和结果
- **认证：** 无需认证

### 请求参数
| 参数 | 类型 | 位置 | 必填 | 描述 |
|------|------|------|------|------|
| task_id | string | 路径 | 是 | 任务ID |

### 响应参数

#### 任务进行中时
```json
{
  "task_id": "29889eb0ed1341d68675290d3167cd1e",
  "task_type": "long_text",
  "status": "pending",
  "voice": "xiaomeng",
  "created_at": "2025-10-10T14:01:53",
  "started_at": null,
  "completed_at": null,
  "text_preview": "要合成的文本内容...",
  "error_message": null,
  "queue_position": 3
}
```

#### 任务完成时
```json
{
  "task_id": "29889eb0ed1341d68675290d3167cd1e",
  "task_type": "long_text", 
  "status": "completed",
  "voice": "yunxi",
  "created_at": "2025-10-10T14:01:53",
  "started_at": "2025-10-10T14:01:54",
  "completed_at": "2025-10-10T14:01:56",
  "text_preview": "这是一个长文本测试，用于验证任务提交和状态查询功能...",
  "error_message": null,
  "audio_url": "https://aigc-omni.tos-cn-guangzhou.volces.com/29889eb0ed1341d68675290d3167cd1e/29889eb0ed1341d68675290d3167cd1e.wav",
  "srt_url": "https://aigc-omni.tos-cn-guangzhou.volces.com/29889eb0ed1341d68675290d3167cd1e/29889eb0ed1341d68675290d3167cd1e.srt"
}
```

#### 任务失败时
```json
{
  "task_id": "29889eb0ed1341d68675290d3167cd1e",
  "task_type": "long_text",
  "status": "failed", 
  "voice": "xiaomeng",
  "created_at": "2025-10-10T14:01:53",
  "started_at": "2025-10-10T14:01:54",
  "completed_at": "2025-10-10T14:01:56",
  "text_preview": "要合成的文本内容...",
  "error_message": "具体的错误信息"
}
```

### 响应字段说明
| 字段 | 类型 | 描述 |
|------|------|------|
| task_id | string | 任务唯一标识符 |
| task_type | string | 任务类型：online/long_text |
| status | string | 任务状态：pending/processing/completed/failed |
| voice | string | 使用的音色 |
| created_at | string | 任务创建时间 |
| started_at | string | 任务开始处理时间 |
| completed_at | string | 任务完成时间 |
| text_preview | string | 文本预览 |
| error_message | string | 错误信息（仅失败时） |
| audio_url | string | 音频文件URL（仅完成时） |
| srt_url | string | 字幕文件URL（仅完成时） |
| queue_position | integer | 队列位置（仅pending状态的长文本任务） |

---

## 状态码说明

| 状态码 | 描述 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在（如任务ID不存在） |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

---

## 任务状态说明

| 状态 | 描述 |
|------|------|
| pending | 任务已提交，等待处理 |
| processing | 任务正在处理中 |
| completed | 任务已完成 |
| failed | 任务处理失败 |

---

## 使用示例

### 1. 短文本合成示例

```bash
# 请求
curl -X POST "http://localhost:6006/tts/online" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好，这是一个测试。",
    "voice": "xiaomeng",
    "seed": 8
  }'

# 响应
{
  "task_id": "7a5186872526488e95de0bc6f8fe69fe",
  "sample_rate": 24000,
  "duration": 2.1,
  "processing_time": 0.8,
  "audio_url": "https://example.com/audio.wav",
  "srt_url": "https://example.com/subtitle.srt"
}
```

### 2. 长文本合成示例

```bash
# 提交任务
curl -X POST "http://localhost:6006/tts/task/submit" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "这是一个很长的文本...",
    "voice": "yunxi",
    "priority": 1
  }'

# 响应
{
  "task_id": "29889eb0ed1341d68675290d3167cd1e",
  "status": "pending",
  "message": "长文本合成任务已提交，请使用task_id查询处理状态"
}

# 查询状态
curl "http://localhost:6006/tts/task/29889eb0ed1341d68675290d3167cd1e"
```

### 3. 获取音色列表示例

```bash
# 请求
curl "http://localhost:6006/voices"

# 响应
{
  "voices": [
    {
      "name": "xiaomeng",
      "description": "小萌音色",
      "language": "zh-CN"
    },
    {
      "name": "yunxi",
      "description": "云希音色", 
      "language": "zh-CN"
    }
  ],
  "total": 2
}
```

---

## 注意事项

1. **文本长度限制**：
   - 在线TTS接口：最多300字符
   - 长文本任务接口：最多50000字符

2. **音色支持**：
   - 当前支持：xiaomeng（小萌）、yunxi（云希）
   - 使用前建议通过 `/voices` 接口获取最新的音色列表

3. **文件存储**：
   - 生成的音频和字幕文件会自动上传到TOS存储
   - 文件URL在任务完成后通过响应返回

4. **任务处理**：
   - 长文本任务采用队列处理机制
   - 可通过priority参数设置任务优先级
   - 建议定期轮询任务状态直到完成

5. **错误处理**：
   - 所有接口都会返回标准的HTTP状态码
   - 错误信息会在响应体中详细说明

---

## 更新日志

### v1.0.0 (2025-10-10)
- 修改在线TTS合成接口：删除响应中的 `audio_base64` 和 `srt` 参数
- 修改任务状态查询接口：任务完成时删除 `result` 参数
- 优化响应结构，减少数据传输量
- 统一使用文件URL方式提供音频和字幕访问