"""
字幕生成工具类
提供统一的SRT字幕生成功能，支持智能断句和时间分配
"""

import re
from typing import List, Tuple


class SubtitleGenerator:
    """字幕生成器类，提供SRT字幕生成功能"""
    
    def __init__(self, max_chars_per_subtitle: int = 30, min_duration: float = 1.5, max_duration: float = 6.0):
        """
        初始化字幕生成器
        
        Args:
            max_chars_per_subtitle: 每个字幕段最大字符数
            min_duration: 每个字幕段最小时长（秒）
            max_duration: 每个字幕段最大时长（秒）
        """
        self.max_chars_per_subtitle = max_chars_per_subtitle
        self.min_duration = min_duration
        self.max_duration = max_duration
    
    def generate_srt_from_text(self, text: str, audio_duration: float) -> str:
        """
        根据文本和音频时长生成SRT字幕文件，支持智能断句
        
        Args:
            text: 要生成字幕的文本
            audio_duration: 音频总时长（秒）
            
        Returns:
            SRT格式的字幕内容
        """
        if not text.strip():
            return ""
        
        # 智能分割文本
        sentences = self._split_text_intelligently(text)
        
        if not sentences:
            return ""
        
        # 生成SRT内容
        return self._generate_srt_content(sentences, audio_duration)
    
    def _split_text_intelligently(self, text: str) -> List[str]:
        """
        智能分割文本，避免连续标点符号被分开
        
        Args:
            text: 原始文本
            
        Returns:
            分割后的句子列表
        """
        # 首先按主要标点符号分割
        primary_pattern = r'([,.;!?，。；！？、])'
        parts = re.split(primary_pattern, text)
        
        # 重新组合分割的部分
        primary_sentences = []
        current_sentence = ""
        
        for part in parts:
            if part.strip():
                current_sentence += part
                # 如果这部分包含结束标点，则结束当前句子
                if re.search(primary_pattern, part):
                    primary_sentences.append(current_sentence.strip())
                    current_sentence = ""
        
        # 添加剩余的部分
        if current_sentence.strip():
            primary_sentences.append(current_sentence.strip())
        
        # 进一步处理长句
        final_sentences = []
        for sentence in primary_sentences:
            if len(sentence) <= self.max_chars_per_subtitle:
                final_sentences.append(sentence)
            else:
                # 长句按次要标点分割
                sub_sentences = self._split_long_sentence(sentence)
                final_sentences.extend(sub_sentences)
        
        return [s for s in final_sentences if s.strip()]
    
    def _split_long_sentence(self, sentence: str) -> List[str]:
        """
        分割长句子
        
        Args:
            sentence: 长句子
            
        Returns:
            分割后的句子列表
        """
        # 按次要标点符号分割
        secondary_pattern = r'([,.;!?，。；！？、])'
        parts = re.split(secondary_pattern, sentence)
        
        result = []
        current_part = ""
        
        for part in parts:
            if part.strip():
                # 如果当前部分加上新部分不超过限制，则合并
                if len(current_part + part) <= self.max_chars_per_subtitle:
                    current_part += part
                else:
                    # 否则先保存当前部分，开始新部分
                    if current_part.strip():
                        result.append(current_part.strip())
                    current_part = part
        
        # 添加最后一部分
        if current_part.strip():
            result.append(current_part.strip())
        
        return result
    
    def _generate_srt_content(self, sentences: List[str], audio_duration: float) -> str:
        """
        生成SRT格式内容
        
        Args:
            sentences: 句子列表
            audio_duration: 音频总时长
            
        Returns:
            SRT格式字符串
        """
        srt_content = []
        
        # 计算每个字幕段的时长（基于字符数比例分配）
        total_chars = sum(len(s) for s in sentences)
        current_time = 0.0
        
        for i, sentence in enumerate(sentences):
            # 根据字符数比例分配时间
            char_ratio = len(sentence) / total_chars if total_chars > 0 else 1.0 / len(sentences)
            duration = audio_duration * char_ratio
            
            # 设置合理的时长范围
            duration = max(self.min_duration, min(self.max_duration, duration))
            
            start_time = current_time
            end_time = current_time + duration
            
            # 确保不超过总时长
            if end_time > audio_duration:
                end_time = audio_duration
            
            start_srt = self._format_srt_time(start_time)
            end_srt = self._format_srt_time(end_time)
            
            srt_content.append(f"{i + 1}")
            srt_content.append(f"{start_srt} --> {end_srt}")
            srt_content.append(sentence)
            srt_content.append("")
            
            current_time = end_time
        
        return "\n".join(srt_content)
    
    def _format_srt_time(self, seconds: float) -> str:
        """
        将秒数转换为SRT时间格式
        
        Args:
            seconds: 秒数
            
        Returns:
            SRT时间格式字符串 (HH:MM:SS,mmm)
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"


# 创建默认实例
default_subtitle_generator = SubtitleGenerator()

# 提供便捷函数
def generate_srt_from_text(text: str, audio_duration: float, 
                          max_chars_per_subtitle: int = 30,
                          min_duration: float = 1.5,
                          max_duration: float = 6.0) -> str:
    """
    便捷函数：生成SRT字幕
    
    Args:
        text: 文本内容
        audio_duration: 音频时长
        max_chars_per_subtitle: 每个字幕段最大字符数
        min_duration: 最小时长
        max_duration: 最大时长
        
    Returns:
        SRT格式字幕内容
    """
    generator = SubtitleGenerator(max_chars_per_subtitle, min_duration, max_duration)
    return generator.generate_srt_from_text(text, audio_duration)