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
        prev_end_ms = None

        for sent_info in sentence_times:
            sentence = sent_info['sentence'].strip()
            if not sentence:
                continue

            if len(sentence) > self.max_chars_per_subtitle:
                sub_sentences = self._split_sentence_with_timing(sentence, sent_info)
                for sub_sent_info in sub_sentences:
                    start_ms = sub_sent_info['start_ms'] if 'start_ms' in sub_sent_info else int(round(sub_sent_info['start_time'] * 1000))
                    end_ms = sub_sent_info['end_ms'] if 'end_ms' in sub_sent_info else int(round(sub_sent_info['end_time'] * 1000))
                    if prev_end_ms is not None and start_ms < prev_end_ms:
                        start_ms = prev_end_ms
                    if end_ms < start_ms:
                        end_ms = start_ms

                    normalized = {
                        'sentence': sub_sent_info['sentence'],
                        'start_ms': start_ms,
                        'end_ms': end_ms,
                        'duration_ms': end_ms - start_ms,
                        'start_time': start_ms / 1000.0,
                        'end_time': end_ms / 1000.0,
                        'duration': (end_ms - start_ms) / 1000.0,
                    }
                    self._add_subtitle_entry(srt_content, subtitle_index, normalized)
                    subtitle_index += 1
                    prev_end_ms = end_ms
            else:
                start_ms = sent_info['start_ms'] if 'start_ms' in sent_info else int(round(sent_info['start_time'] * 1000))
                end_ms = sent_info['end_ms'] if 'end_ms' in sent_info else int(round(sent_info['end_time'] * 1000))
                if prev_end_ms is not None and start_ms < prev_end_ms:
                    start_ms = prev_end_ms
                if end_ms < start_ms:
                    end_ms = start_ms

                normalized = {
                    'sentence': sentence,
                    'start_ms': start_ms,
                    'end_ms': end_ms,
                    'duration_ms': end_ms - start_ms,
                    'start_time': start_ms / 1000.0,
                    'end_time': end_ms / 1000.0,
                    'duration': (end_ms - start_ms) / 1000.0,
                }
                self._add_subtitle_entry(srt_content, subtitle_index, normalized)
                subtitle_index += 1
                prev_end_ms = end_ms

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
        
        parts = []
        total_chars = len(sentence)
        start_ms = timing_info['start_ms'] if 'start_ms' in timing_info else int(round(timing_info['start_time'] * 1000))
        total_duration_ms = timing_info['duration_ms'] if 'duration_ms' in timing_info else int(round(timing_info['duration'] * 1000))
        end_ms_base = timing_info['end_ms'] if 'end_ms' in timing_info else start_ms + total_duration_ms

        prev_pos = 0
        for split_pos in split_points:
            sub_sentence = sentence[prev_pos:split_pos].strip()
            if sub_sentence:
                parts.append(sub_sentence)
            prev_pos = split_pos

        if prev_pos < total_chars:
            sub_sentence = sentence[prev_pos:].strip()
            if sub_sentence:
                parts.append(sub_sentence)

        if not parts:
            return []

        n = len(parts)
        if total_duration_ms < n:
            return [{
                'sentence': sentence.strip(),
                'start_ms': start_ms,
                'end_ms': end_ms_base,
                'duration_ms': end_ms_base - start_ms,
                'start_time': start_ms / 1000.0,
                'end_time': end_ms_base / 1000.0,
                'duration': (end_ms_base - start_ms) / 1000.0,
            }]

        weights = [len(p) for p in parts]
        total_w = sum(weights)
        if total_w <= 0:
            total_w = n
            weights = [1] * n

        raw = [total_duration_ms * w / total_w for w in weights]
        floors = [int(x) for x in raw]
        remainder = total_duration_ms - sum(floors)
        fracs = [x - f for x, f in zip(raw, floors)]
        order = sorted(range(n), key=lambda i: fracs[i], reverse=True)
        durations = floors[:]
        for i in range(remainder):
            durations[order[i]] += 1

        zeros = [i for i, d in enumerate(durations) if d <= 0]
        if zeros:
            need = len(zeros)
            if total_duration_ms < need:
                return [{
                    'sentence': sentence.strip(),
                    'start_ms': start_ms,
                    'end_ms': end_ms_base,
                    'duration_ms': end_ms_base - start_ms,
                    'start_time': start_ms / 1000.0,
                    'end_time': end_ms_base / 1000.0,
                    'duration': (end_ms_base - start_ms) / 1000.0,
                }]
            for z in zeros:
                durations[z] = 1
            surplus = total_duration_ms - sum(durations)
            idx = 0
            while surplus > 0:
                durations[idx % n] += 1
                idx += 1

        sub_sentences = []
        cur_ms = start_ms
        for i, (p, d_ms) in enumerate(zip(parts, durations)):
            end_ms = cur_ms + d_ms if i < n - 1 else end_ms_base
            sub_sentences.append({
                'sentence': p,
                'start_ms': cur_ms,
                'end_ms': end_ms,
                'duration_ms': end_ms - cur_ms,
                'start_time': cur_ms / 1000.0,
                'end_time': end_ms / 1000.0,
                'duration': (end_ms - cur_ms) / 1000.0,
            })
            cur_ms = end_ms

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
        total_duration_ms = timing_info['duration_ms'] if 'duration_ms' in timing_info else int(round(timing_info['duration'] * 1000))
        start_ms = timing_info['start_ms'] if 'start_ms' in timing_info else int(round(timing_info['start_time'] * 1000))
        end_ms_base = timing_info['end_ms'] if 'end_ms' in timing_info else start_ms + total_duration_ms
        
        # 计算分割段数
        num_parts = (total_chars + self.max_chars_per_subtitle - 1) // self.max_chars_per_subtitle
        chars_per_part = total_chars // num_parts
        
        sub_sentences = []
        base = total_duration_ms // num_parts
        rem = total_duration_ms - base * num_parts
        offset_ms = 0
        for i in range(num_parts):
            start_idx = i * chars_per_part
            if i == num_parts - 1:
                end_idx = total_chars
            else:
                end_idx = min((i + 1) * chars_per_part, total_chars)
            sub_sentence = sentence[start_idx:end_idx].strip()
            if sub_sentence:
                part_duration_ms = base + (1 if i < rem else 0)
                sub_start_ms = start_ms + offset_ms
                sub_end_ms = sub_start_ms + part_duration_ms if i < num_parts - 1 else end_ms_base
                sub_info = {
                    'sentence': sub_sentence,
                    'start_ms': sub_start_ms,
                    'end_ms': sub_end_ms,
                    'duration_ms': sub_end_ms - sub_start_ms,
                    'start_time': sub_start_ms / 1000.0,
                    'end_time': sub_end_ms / 1000.0,
                    'duration': (sub_end_ms - sub_start_ms) / 1000.0,
                }
                sub_sentences.append(sub_info)
                offset_ms += part_duration_ms
        
        return sub_sentences
    
    def _add_subtitle_entry(self, srt_content: List[str], index: int, timing_info: Dict):
        """
        添加一个字幕条目（新增方法）
        
        Args:
            srt_content: SRT内容列表
            index: 字幕序号
            timing_info: 时间信息
        """
        start_seconds = timing_info['start_ms'] / 1000.0 if 'start_ms' in timing_info else timing_info['start_time']
        end_seconds = timing_info['end_ms'] / 1000.0 if 'end_ms' in timing_info else timing_info['end_time']
        start_srt = self._format_srt_time(start_seconds)
        end_srt = self._format_srt_time(end_seconds)
        
        # 清理SentencePiece特殊符号
        clean_sentence = self._clean_sentencepiece_symbols(timing_info['sentence'])
        
        srt_content.append(f"{index}")
        srt_content.append(f"{start_srt} --> {end_srt}")
        srt_content.append(clean_sentence)
        srt_content.append("")
    
    
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
            if 'sentence' not in sent_info:
                return False
            has_ms = all(k in sent_info for k in ['start_ms', 'end_ms', 'duration_ms'])
            has_s = all(k in sent_info for k in ['start_time', 'end_time', 'duration'])
            if not (has_ms or has_s):
                return False
            start_s = (sent_info['start_ms'] / 1000.0) if has_ms else sent_info['start_time']
            end_s = (sent_info['end_ms'] / 1000.0) if has_ms else sent_info['end_time']
            dur_s = (sent_info['duration_ms'] / 1000.0) if has_ms else sent_info['duration']
            if start_s < 0 or end_s <= start_s:
                return False
            if dur_s <= 0:
                return False
            if i > 0:
                prev = sentence_times[i-1]
                prev_end_s = (prev['end_ms'] / 1000.0) if 'end_ms' in prev else prev['end_time']
                if abs(start_s - prev_end_s) > 1.0:
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
        
        if self._validate_sentence_times(sentence_times):
            return self._generate_srt_from_exact_timestamps(sentence_times)
        else:
            return ""
    
    
    def _format_srt_time(self, seconds: float) -> str:
        """
        将秒数转换为SRT时间格式
        
        Args:
            seconds: 秒数
            
        Returns:
            SRT时间格式字符串 (HH:MM:SS,mmm)
        """
        total_ms = int(round(seconds * 1000))
        hours = total_ms // (3600 * 1000)
        minutes = (total_ms % (3600 * 1000)) // (60 * 1000)
        secs = (total_ms % (60 * 1000)) // 1000
        millisecs = total_ms % 1000
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
