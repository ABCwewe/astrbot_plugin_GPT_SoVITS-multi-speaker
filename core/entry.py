# entry.py
from __future__ import annotations

from typing import Any

from astrbot.api import logger

from .config import EmotionConfig, PluginConfig, SpeakerConfig


class SpeakerManager:
    """
    说话人管理器
    管理所有说话人配置，支持按名称查找说话人和情绪
    """

    def __init__(self, config: PluginConfig):
        self.cfg = config
        self.speakers: dict[str, SpeakerConfig] = {}
        self._load_speakers()
        logger.debug(f"已加载说话人：{self.get_all_speaker_names()}")

    def _load_speakers(self) -> None:
        """加载所有说话人配置"""
        # 从 PluginConfig 获取说话人数据
        speakers_data = self.cfg._data.get("speakers", [])
        for speaker_data in speakers_data:
            if isinstance(speaker_data, dict):
                speaker_cfg = SpeakerConfig(speaker_data)
                self.speakers[speaker_cfg.speaker_name] = speaker_cfg

    def get_speaker(self, name: str) -> SpeakerConfig | None:
        """
        根据名称获取说话人配置

        Args:
            name: 说话人名称

        Returns:
            SpeakerConfig | None: 说话人配置，不存在则返回 None
        """
        return self.speakers.get(name)

    def find_speaker_by_name_or_alias(self, name: str) -> SpeakerConfig | None:
        """
        根据名称或别名查找说话人

        Args:
            name: 说话人名称或别名

        Returns:
            SpeakerConfig | None: 说话人配置，未找到则返回 None
        """
        # 先直接查找
        speaker = self.speakers.get(name)
        if speaker:
            return speaker

        # 通过别名查找
        for speaker_cfg in self.speakers.values():
            if name in speaker_cfg.alias_list:
                return speaker_cfg

        return None

    def get_emotion(self, speaker_name: str, emotion_name: str) -> EmotionConfig | None:
        """
        根据说话人名称和情绪名称获取情绪配置

        Args:
            speaker_name: 说话人名称
            emotion_name: 情绪名称

        Returns:
            EmotionConfig | None: 情绪配置，不存在则返回 None
        """
        speaker = self.get_speaker(speaker_name)
        if not speaker:
            return None

        return speaker.get_emotion(emotion_name)

    def match_emotion(self, speaker_name: str, text: str) -> EmotionConfig | None:
        """
        根据文本关键词匹配情绪配置

        Args:
            speaker_name: 说话人名称
            text: 要匹配的文本

        Returns:
            EmotionConfig | None: 匹配的情绪配置，未匹配则返回 None
        """
        speaker = self.get_speaker(speaker_name)
        if not speaker:
            return None

        for emotion in speaker.emotions_list:
            if isinstance(emotion, dict):
                emotion = EmotionConfig(emotion)

            keywords = emotion.keywords if hasattr(emotion, "keywords") else []
            for keyword in keywords:
                if keyword in text:
                    return emotion

        return None

    def get_all_speaker_names(self) -> list[str]:
        """
        获取所有说话人名称

        Returns:
            list[str]: 说话人名称列表
        """
        return list(self.speakers.keys())

    def get_all_emotion_names(self, speaker_name: str) -> list[str]:
        """
        获取指定说话人的所有情绪名称

        Args:
            speaker_name: 说话人名称

        Returns:
            list[str]: 情绪名称列表
        """
        return self.cfg.get_all_emotion_names(speaker_name)

    def get_default_speaker_name(self) -> str:
        """
        获取默认说话人名称

        Returns:
            str: 默认说话人名称
        """
        return self.cfg.default_speaker
