# config.py
from __future__ import annotations

import json
import re
from collections.abc import Mapping, MutableMapping
from pathlib import Path, PureWindowsPath
from types import MappingProxyType, UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.provider.provider import Provider
from astrbot.core.star.context import Context
from astrbot.core.star.star_tools import StarTools
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_path


class ConfigNode:
    """
    配置节点，把 dict 变成强类型对象。

    规则：
    - schema 来自子类类型注解
    - 声明字段：读写，写回底层 dict
    - 未声明字段和下划线字段：仅挂载属性，不写回
    - 支持 ConfigNode 多层嵌套（lazy + cache）
    """

    _SCHEMA_CACHE: dict[type, dict[str, type]] = {}
    _FIELDS_CACHE: dict[type, set[str]] = {}

    @classmethod
    def _schema(cls) -> dict[str, type]:
        return cls._SCHEMA_CACHE.setdefault(cls, get_type_hints(cls))

    @classmethod
    def _fields(cls) -> set[str]:
        return cls._FIELDS_CACHE.setdefault(
            cls,
            {k for k in cls._schema() if not k.startswith("_")},
        )

    @staticmethod
    def _is_optional(tp: type) -> bool:
        if get_origin(tp) in (Union, UnionType):
            return type(None) in get_args(tp)
        return False

    def __init__(self, data: MutableMapping[str, Any]):
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_children", {})
        for key, tp in self._schema().items():
            if key.startswith("_"):
                continue
            if key in data:
                continue
            if hasattr(self.__class__, key):
                continue
            if self._is_optional(tp):
                continue
            logger.warning(f"[config:{self.__class__.__name__}] 缺少字段：{key}")

    def __getattr__(self, key: str) -> Any:
        if key in self._fields():
            value = self._data.get(key)
            tp = self._schema().get(key)

            if isinstance(tp, type) and issubclass(tp, ConfigNode):
                children: dict[str, ConfigNode] = self.__dict__["_children"]
                if key not in children:
                    if not isinstance(value, MutableMapping):
                        raise TypeError(
                            f"[config:{self.__class__.__name__}] "
                            f"字段 {key} 期望 dict，实际是 {type(value).__name__}"
                        )
                    children[key] = tp(value)
                return children[key]

            return value

        if key in self.__dict__:
            return self.__dict__[key]

        raise AttributeError(key)

    def __setattr__(self, key: str, value: Any) -> None:
        if key in self._fields():
            self._data[key] = value
            return
        object.__setattr__(self, key, value)

    def raw_data(self) -> Mapping[str, Any]:
        """
        底层配置 dict 的只读视图
        """
        return MappingProxyType(self._data)

    def save_config(self) -> None:
        """
        保存配置到磁盘（仅允许在根节点调用）
        """
        if not isinstance(self._data, AstrBotConfig):
            raise RuntimeError(
                f"{self.__class__.__name__}.save_config() 只能在根配置节点上调用"
            )
        self._data.save_config()


# ============ 插件自定义配置 ==================


class EmotionConfig(ConfigNode):
    """单个情绪配置"""

    name: str
    keywords: list[str]
    ref_audio_path: str
    prompt_text: str
    prompt_lang: str
    speed_factor: float
    fragment_interval: float

    def __init__(self, data: MutableMapping[str, Any]):
        super().__init__(data)
        self.ref_audio_path = PluginConfig.normalize_path(self.ref_audio_path)

    def to_params(self) -> dict[str, Any]:
        """转换为 TTS API 参数字典"""
        return {
            "ref_audio_path": self.ref_audio_path,
            "prompt_text": self.prompt_text,
            "prompt_lang": self.prompt_lang,
            "speed_factor": self.speed_factor,
            "fragment_interval": self.fragment_interval,
        }


class SpeakerConfig(ConfigNode):
    """单个说话人配置"""

    speaker_name: str
    alias: str
    gpt_path: str
    sovits_path: str
    base_url: str
    timeout: int
    text_lang: str
    emotions: str  # JSON 格式的字符串

    def __init__(self, data: MutableMapping[str, Any]):
        super().__init__(data)
        self.gpt_path = PluginConfig.normalize_path(self.gpt_path)
        self.sovits_path = PluginConfig.normalize_path(self.sovits_path)
        self._emotion_cache: dict[str, EmotionConfig] = {}
        self._emotions_list: list[dict[str, Any]] = []
        self._parse_emotions()
        self._parse_alias()

    def _parse_alias(self) -> None:
        """解析别名列表"""
        alias_str = getattr(self, "alias", "") or ""
        self._alias_list = [a.strip() for a in alias_str.split(",") if a.strip()]

    @property
    def alias_list(self) -> list[str]:
        """获取别名列表"""
        return self._alias_list

    def _parse_emotions(self) -> None:
        """解析 JSON 格式的情绪配置"""
        emotions_str = (
            self.emotions if hasattr(self, "emotions") and self.emotions else "[]"
        )

        # 如果是字符串，尝试解析为 JSON
        if isinstance(emotions_str, str):
            try:
                self._emotions_list = json.loads(emotions_str)
            except json.JSONDecodeError:
                logger.warning(
                    f"说话人 {self.speaker_name} 的情绪配置 JSON 解析失败，使用空列表"
                )
                self._emotions_list = []
        elif isinstance(emotions_str, list):
            self._emotions_list = emotions_str
        else:
            self._emotions_list = []

    @property
    def emotions_list(self) -> list[dict[str, Any]]:
        """获取情绪配置列表"""
        return self._emotions_list

    def get_emotion(self, emotion_name: str) -> EmotionConfig | None:
        """根据名称获取情绪配置"""
        if emotion_name in self._emotion_cache:
            return self._emotion_cache[emotion_name]

        for emotion_data in self._emotions_list:
            if isinstance(emotion_data, dict):
                if emotion_data.get("name") == emotion_name:
                    emotion = EmotionConfig(emotion_data)
                    self._emotion_cache[emotion_name] = emotion
                    return emotion

        return None

    def get_emotion_names(self) -> list[str]:
        """获取所有情绪名称"""
        names = []
        for emotion in self._emotions_list:
            if isinstance(emotion, dict):
                name = emotion.get("name", "")
                if name:
                    names.append(name)
        return names


class AutoConfig(ConfigNode):
    only_llm_result: bool
    tts_prob: float
    max_msg_len: int


class TTSParamsConfig(ConfigNode):
    """TTS 全局参数配置"""

    media_type: str
    text_split_method: str
    batch_size: int
    batch_threshold: float
    parallel_infer: bool
    split_bucket: bool


class JudgeConfig(ConfigNode):
    enabled_llm: bool
    provider_id: str


class CacheConfig(ConfigNode):
    enabled: bool
    expire_hours: int
    path: str


class PluginConfig(ConfigNode):
    enabled: bool
    default_speaker: str
    speakers: list[dict[str, Any]]
    tts_params: TTSParamsConfig
    auto: AutoConfig
    judge: JudgeConfig
    cache: CacheConfig

    _plugin_name: str = "astrbot_plugin_GPT_SoVITS"

    def __init__(self, cfg: AstrBotConfig, context: Context):
        super().__init__(cfg)
        self.context = context

        self.data_dir = StarTools.get_data_dir(self._plugin_name)
        self.plugin_dir = Path(get_astrbot_plugin_path()) / self._plugin_name

        self._migrate_old_config()

        # 初始化说话人列表
        self._speakers_cache: dict[str, SpeakerConfig] = {}
        speakers_data = self._data.get("speakers", [])
        for speaker_data in speakers_data:
            if isinstance(speaker_data, dict):
                speaker_cfg = SpeakerConfig(speaker_data)
                self._speakers_cache[speaker_cfg.speaker_name] = speaker_cfg

        self.audio_dir = (
            Path(self.cache.path) if self.cache.path else self.data_dir / "audio"
        )
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        self.save_config()

    def _migrate_old_config(self) -> None:
        """迁移旧配置格式到新格式"""
        cfg_dict = self._data if hasattr(self, "_data") else {}

        # 检测旧配置格式
        if "client" in cfg_dict or "model" in cfg_dict:
            logger.info("检测到旧配置格式，正在迁移...")

            # 获取旧配置值
            old_client = cfg_dict.get("client", {})
            old_model = cfg_dict.get("model", {})
            old_default_params = cfg_dict.get("default_params", {})
            old_entry_storage = cfg_dict.get("entry_storage", [])

            # 创建默认说话人
            default_speaker = {
                "speaker_name": "default",
                "gpt_path": old_model.get("gpt_path", ""),
                "sovits_path": old_model.get("sovits_path", ""),
                "base_url": old_client.get("base_url", "http://127.0.0.1:9880"),
                "timeout": old_client.get("timeout", 60),
                "emotions": old_entry_storage
                if old_entry_storage
                else [
                    {
                        "name": "默认",
                        "keywords": [],
                        "ref_audio_path": old_default_params.get("ref_audio_path", ""),
                        "prompt_text": old_default_params.get("prompt_text", ""),
                        "prompt_lang": old_default_params.get("prompt_lang", "zh"),
                        "speed_factor": old_default_params.get("speed_factor", 1.0),
                        "fragment_interval": old_default_params.get(
                            "fragment_interval", 0.7
                        ),
                        "top_k": old_default_params.get("top_k", 5),
                        "top_p": old_default_params.get("top_p", 1.0),
                        "temperature": old_default_params.get("temperature", 1.0),
                        "batch_size": old_default_params.get("batch_size", 1),
                        "media_type": old_default_params.get("media_type", "wav"),
                    }
                ],
            }

            # 设置新配置
            if "speakers" not in cfg_dict:
                cfg_dict["speakers"] = [default_speaker]
            if "default_speaker" not in cfg_dict:
                cfg_dict["default_speaker"] = "default"

            # 移除旧字段
            for key in ["client", "model", "default_params", "entry_storage"]:
                if key in cfg_dict:
                    del cfg_dict[key]

            logger.info("配置迁移完成")

    @staticmethod
    def normalize_path(p: str) -> str:
        if not p:
            return p
        path_text = p.strip()
        if not path_text:
            return path_text

        match = re.search(r"([A-Za-z]:[\\/].*)$", path_text)
        if match and PureWindowsPath(match.group(1)).is_absolute():
            return match.group(1)

        if PureWindowsPath(path_text).is_absolute():
            return path_text

        path = Path(path_text).expanduser()
        if path.is_absolute():
            return str(path)
        return str(path.resolve())

    def get_speaker(self, name: str) -> SpeakerConfig | None:
        """根据名称获取说话人配置"""
        return self._speakers_cache.get(name)

    def get_all_speaker_names(self) -> list[str]:
        """获取所有说话人名称"""
        return list(self._speakers_cache.keys())

    def get_all_emotion_names(self, speaker_name: str) -> list[str]:
        """获取指定说话人的所有情绪名��"""
        speaker = self.get_speaker(speaker_name)
        if speaker:
            return speaker.get_emotion_names()
        return []

    def get_judge_provider(self, umo: str | None = None) -> Provider:
        provider = self.context.get_provider_by_id(
            self.judge.provider_id
        ) or self.context.get_using_provider(umo)

        if not isinstance(provider, Provider):
            raise RuntimeError("未找到可用的 LLM Provider")

        return provider
