"""
字幕生成工具类
提供统一的SRT字幕生成功能，支持智能断句和时间分配
新增基于真实时间戳的字幕生成功能
"""

import re
from typing import List, Tuple, Dict, Optional


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
    
    def _generate_srt_from_exact_timestamps(self, sentence_times: List[Dict]) -> str:
        """
        使用精确时间戳生成SRT内容（新增方法）
        
        Args:
            sentence_times: 验证过的时间戳数据
            
        Returns:
            SRT格式字符串
        """
        srt_content = []
        subtitle_index = 1
        
        for sent_info in sentence_times:
            sentence = sent_info['sentence'].strip()
            if not sentence:
                continue
            
            # 如果句子太长，进行智能分割
            if len(sentence) > self.max_chars_per_subtitle:
                sub_sentences = self._split_sentence_with_timing(sentence, sent_info)
                for sub_sent_info in sub_sentences:
                    self._add_subtitle_entry(srt_content, subtitle_index, sub_sent_info)
                    subtitle_index += 1
            else:
                self._add_subtitle_entry(srt_content, subtitle_index, sent_info)
                subtitle_index += 1
        
        return "\n".join(srt_content)
    
    def _split_sentence_with_timing(self, sentence: str, timing_info: Dict) -> List[Dict]:
        """
        根据时间信息智能分割长句子（新增方法）
        
        Args:
            sentence: 长句子
            timing_info: 原始时间信息
            
        Returns:
            分割后的子句时间信息列表
        """
        # 按标点符号分割
        split_points = self._find_natural_split_points(sentence)
        
        if not split_points:
            # 如果没有合适的分割点，按字符数均匀分割
            return self._split_evenly_by_chars(sentence, timing_info)
        
        # 根据分割点分配时间
        sub_sentences = []
        total_chars = len(sentence)
        start_time = timing_info['start_time']
        total_duration = timing_info['duration']
        
        prev_pos = 0
        for i, split_pos in enumerate(split_points):
            sub_sentence = sentence[prev_pos:split_pos].strip()
            if sub_sentence:
                # 按比例分配时间
                char_ratio = len(sub_sentence) / total_chars
                sub_duration = total_duration * char_ratio
                
                sub_info = {
                    'sentence': sub_sentence,
                    'start_time': start_time,
                    'end_time': start_time + sub_duration,
                    'duration': sub_duration
                }
                sub_sentences.append(sub_info)
                
                start_time += sub_duration
            
            prev_pos = split_pos
        
        # 处理最后一部分
        if prev_pos < total_chars:
            sub_sentence = sentence[prev_pos:].strip()
            if sub_sentence:
                sub_duration = timing_info['end_time'] - start_time
                sub_info = {
                    'sentence': sub_sentence,
                    'start_time': start_time,
                    'end_time': timing_info['end_time'],
                    'duration': sub_duration
                }
                sub_sentences.append(sub_info)
        
        return sub_sentences
    
    def _find_natural_split_points(self, sentence: str) -> List[int]:
        """
        寻找句子的自然分割点（标点符号）（新增方法）
        
        Args:
            sentence: 句子
            
        Returns:
            分割位置列表
        """
        primary_pattern = r'[，,；;、。\.!?！？…]'
        matches = list(re.finditer(primary_pattern, sentence))

        split_points = []
        for match in matches:
            pos = match.end()
            # 确保分割后每段不超过最大字符数
            if pos <= len(sentence) // 2 or len(sentence) - pos <= self.max_chars_per_subtitle:
                split_points.append(pos)
        
        return split_points
    
    def _split_evenly_by_chars(self, sentence: str, timing_info: Dict) -> List[Dict]:
        """
        按字符数均匀分割句子（新增方法）
        
        Args:
            sentence: 句子
            timing_info: 时间信息
            
        Returns:
            分割后的子句时间信息列表
        """
        total_chars = len(sentence)
        total_duration = timing_info['duration']
        start_time = timing_info['start_time']
        
        # 计算分割段数
        num_parts = (total_chars + self.max_chars_per_subtitle - 1) // self.max_chars_per_subtitle
        chars_per_part = total_chars // num_parts
        
        sub_sentences = []
        for i in range(num_parts):
            start_idx = i * chars_per_part
            if i == num_parts - 1:
                # 最后一段包含剩余所有字符
                end_idx = total_chars
            else:
                end_idx = min((i + 1) * chars_per_part, total_chars)
            
            sub_sentence = sentence[start_idx:end_idx].strip()
            if sub_sentence:
                # 均匀分配时间
                part_duration = total_duration / num_parts
                sub_start = start_time + i * part_duration
                sub_end = sub_start + part_duration if i < num_parts - 1 else timing_info['end_time']
                
                sub_info = {
                    'sentence': sub_sentence,
                    'start_time': sub_start,
                    'end_time': sub_end,
                    'duration': sub_end - sub_start
                }
                sub_sentences.append(sub_info)
        
        return sub_sentences
    
    def _add_subtitle_entry(self, srt_content: List[str], index: int, timing_info: Dict):
        """
        添加一个字幕条目（新增方法）
        
        Args:
            srt_content: SRT内容列表
            index: 字幕序号
            timing_info: 时间信息
        """
        start_srt = self._format_srt_time(timing_info['start_time'])
        end_srt = self._format_srt_time(timing_info['end_time'])
        
        # 清理SentencePiece特殊符号
        clean_sentence = self._clean_sentencepiece_symbols(timing_info['sentence'])
        
        srt_content.append(f"{index}")
        srt_content.append(f"{start_srt} --> {end_srt}")
        srt_content.append(clean_sentence)
        srt_content.append("")
    
    def _generate_srt_with_fallback(self, text: str, sentence_times: List[Dict]) -> str:
        """
        回退方法：使用原始文本和估算时间生成字幕（新增方法）
        
        Args:
            text: 原始文本
            sentence_times: 部分时间信息（可能不完整）
            
        Returns:
            SRT格式字符串
        """
        if text.strip():
            # 估算总时长
            total_duration = sum(sent.get('duration', 0) for sent in sentence_times) if sentence_times else 0
            return self.generate_srt_from_text(text, total_duration)
        else:
            return ""
    
    def _validate_sentence_times(self, sentence_times: List[Dict]) -> bool:
        """
        验证时间戳数据的有效性（新增方法）
        
        Args:
            sentence_times: 时间戳数据
            
        Returns:
            是否有效
        """
        if not sentence_times:
            return False
        
        for i, sent_info in enumerate(sentence_times):
            # 检查必需字段
            required_fields = ['sentence', 'start_time', 'end_time', 'duration']
            if not all(field in sent_info for field in required_fields):
                return False
            
            # 检查时间逻辑
            if sent_info['start_time'] < 0 or sent_info['end_time'] <= sent_info['start_time']:
                return False
            
            if sent_info['duration'] <= 0:
                return False
            
            # 检查时间连续性（允许小的重叠或间隙）
            if i > 0:
                prev_end = sentence_times[i-1]['end_time']
                curr_start = sent_info['start_time']
                if abs(curr_start - prev_end) > 1.0:  # 允许1秒的间隙或重叠
                    return False
        
        return True
    
    def generate_srt_from_timestamps(self, sentence_times: List[Dict], text: str = "") -> str:
        """
        基于真实时间戳生成SRT字幕文件（新增方法）
        
        Args:
            sentence_times: 包含每句话时间信息的列表
                格式: [{'sentence': '文本', 'start_time': 0.0, 'end_time': 2.5, 'duration': 2.5}, ...]
            text: 原始文本（可选，用于验证）
            
        Returns:
            SRT格式的字幕内容
        """
        if not sentence_times:
            return ""
        
        # 如果时间戳数据有效，直接使用时间戳生成字幕
        if self._validate_sentence_times(sentence_times):
            return self._generate_srt_from_exact_timestamps(sentence_times)
        else:
            # 回退到基于字符数的智能分割
            return self._generate_srt_with_fallback(text, sentence_times)
    
    def _split_text_intelligently(self, text: str) -> List[str]:
        """
        智能分割文本，避免连续标点符号被分开
        
        Args:
            text: 原始文本
            
        Returns:
            分割后的句子列表
        """
        # 首先清理可能的SentencePiece特殊符号
        clean_text = self._clean_sentencepiece_symbols(text)
        
        # 首先按主要标点符号分割
        primary_pattern = r'([,.;!?，。；！？、])'
        parts = re.split(primary_pattern, clean_text)
        
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
            
            # 清理SentencePiece特殊符号
            clean_sentence = self._clean_sentencepiece_symbols(sentence)
            
            srt_content.append(f"{i + 1}")
            srt_content.append(f"{start_srt} --> {end_srt}")
            srt_content.append(clean_sentence)
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
    
    def _clean_sentencepiece_symbols(self, text: str) -> str:
        """
        清理SentencePiece分词器的特殊符号（新增方法）
        
        Args:
            text: 输入文本
            
        Returns:
            清理后的文本
        """
        # 清理▁符号（SentencePiece的词首标记）
        # 注意：这里简单移除所有▁符号，因为中文不需要额外的空格处理
        cleaned_text = text.replace("▁", "")
        
        # 清理其他可能的特殊符号
        # 移除多余的空格（如果存在）
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
        cleaned_text = cleaned_text.strip()
        
        return cleaned_text


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