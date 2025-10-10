-- 增强型TTS API数据库架构
-- 支持在线TTS和长文本TTS任务管理

-- TTS任务表
-- 存储所有TTS任务的详细信息和处理状态
CREATE TABLE IF NOT EXISTS tts_tasks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键ID',
    task_id VARCHAR(100) UNIQUE NOT NULL COMMENT '任务唯一标识符',
    task_type VARCHAR(20) NOT NULL COMMENT '任务类型：online/long_text',
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '任务状态：pending/processing/completed/failed/cancelled',
    task_directory VARCHAR(500) COMMENT '任务文件存储目录路径',
    text_file_path VARCHAR(500) COMMENT '文本文件存储路径（所有任务类型都存储）',
    text_preview VARCHAR(200) COMMENT '文本内容预览（前200字符）',
    voice VARCHAR(50) NOT NULL COMMENT '使用的音色标识',
    payload JSON COMMENT '任务参数配置（语速、音调、音量等）',
    audio_file_path VARCHAR(500) COMMENT '生成的音频文件本地路径',
    audio_url VARCHAR(500) COMMENT '音频文件访问URL',
    srt_file_path VARCHAR(500) COMMENT '字幕文件本地路径（所有任务类型都存储）',
    srt_url VARCHAR(500) COMMENT '字幕文件TOS访问URL',
    error_message VARCHAR(1000) COMMENT '错误信息（任务失败时）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '任务创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '任务最后更新时间',
    started_at TIMESTAMP NULL COMMENT '任务开始处理时间',
    completed_at TIMESTAMP NULL COMMENT '任务完成时间',
    callback_url VARCHAR(500) COMMENT '任务完成后的回调URL',
    INDEX idx_task_id (task_id) COMMENT '任务ID索引',
    INDEX idx_status (status) COMMENT '任务状态索引',
    INDEX idx_task_type (task_type) COMMENT '任务类型索引',
    INDEX idx_created_at (created_at) COMMENT '创建时间索引',
    INDEX idx_updated_at (updated_at) COMMENT '更新时间索引',
    INDEX idx_voice (voice) COMMENT '音色索引',
    INDEX idx_queue (status, task_type, created_at ASC) COMMENT '任务队列查询优化索引'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='TTS任务主表';

-- 音色配置表
-- 存储音色设置和元数据
CREATE TABLE IF NOT EXISTS voice_configs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键ID',
    voice_name VARCHAR(100) UNIQUE NOT NULL COMMENT '音色系统名称（英文标识）',
    display_name VARCHAR(200) COMMENT '音色显示名称（用户友好）',
    description TEXT COMMENT '音色详细描述',
    gender VARCHAR(10) COMMENT '音色性别：male/female/neutral',
    config JSON COMMENT '音色配置参数（默认语速、音调等）',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用该音色',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    INDEX idx_voice_name (voice_name) COMMENT '音色名称索引',
    INDEX idx_is_active (is_active) COMMENT '启用状态索引',
    INDEX idx_gender (gender) COMMENT '性别索引'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='音色配置表';
