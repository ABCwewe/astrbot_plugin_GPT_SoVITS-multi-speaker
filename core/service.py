from typing import TYPE_CHECKING, Any

from astrbot.api import logger

from .client import GSVApiClient, GSVRequestResult
from .config import EmotionConfig, SpeakerConfig
from .local_data import LocalDataManager

if TYPE_CHECKING:
    from .config import TTSParamsConfig


class GPTSoVITSService:
    def __init__(
        self,
        speaker_config: SpeakerConfig,
        client: GSVApiClient,
        local_data: LocalDataManager,
        tts_params: "TTSParamsConfig | None" = None,
    ):
        self.speaker_cfg = speaker_config
        self.default_params = self._build_default_params()
        self.client = client
        self.local_data = local_data
        self.text_lang = getattr(speaker_config, "text_lang", "zh")
        self.tts_params = tts_params

    def _build_default_params(self) -> dict[str, Any]:
        """构建默认参数（优先使用名为"默认"的情绪，否则使用第一个情绪）"""
        emotions_list = self.speaker_cfg.emotions_list

        default_emotion = None
        for emotion_data in emotions_list:
            if isinstance(emotion_data, dict) and emotion_data.get("name") == "默认":
                default_emotion = emotion_data
                break

        if default_emotion is None and emotions_list:
            default_emotion = emotions_list[0]

        if default_emotion:
            if isinstance(default_emotion, dict):
                default_emotion = EmotionConfig(default_emotion)
            return default_emotion.to_params()
        return {}

    @staticmethod
    def _detect_lang(text: str) -> str:
        total = len(text)
        if total == 0:
            return "zh"
        kana_count = sum(
            1 for c in text if "\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff"
        )
        ratio = kana_count / total
        return "ja" if ratio > 0.4 else "zh"

    async def load_model(self):
        """加载说话人的模型"""
        if self.speaker_cfg.gpt_path:
            result = await self.client.set_gpt_weights(self.speaker_cfg.gpt_path)
            if result.ok:
                logger.info(f"GPT 模型已加载：{self.speaker_cfg.gpt_path}")
            else:
                logger.error(f"GPT 模型加载失败：{result.error}")

        if self.speaker_cfg.sovits_path:
            result = await self.client.set_sovits_weights(self.speaker_cfg.sovits_path)
            if result.ok:
                logger.info(f"SoVITS 模型已加载：{self.speaker_cfg.sovits_path}")
            else:
                logger.error(f"SoVITS 模型加载失败：{result.error}")

    async def inference(
        self,
        text: str,
        emotion_config: EmotionConfig | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> GSVRequestResult:
        """TTS 推理"""
        # 使用默认参数
        params = self.default_params.copy()

        # 添加默认合成语言
        params["text_lang"] = self.text_lang

        # 添加 TTS 全局参数
        if self.tts_params:
            params["media_type"] = getattr(self.tts_params, "media_type", "wav")
            params["text_split_method"] = getattr(
                self.tts_params, "text_split_method", "cut3"
            )
            params["batch_size"] = getattr(self.tts_params, "batch_size", 1)
            params["batch_threshold"] = getattr(
                self.tts_params, "batch_threshold", 0.75
            )
            params["parallel_infer"] = getattr(self.tts_params, "parallel_infer", True)
            params["split_bucket"] = getattr(self.tts_params, "split_bucket", True)

        if text:
            params["text"] = text

        # 合并情绪参数
        if emotion_config:
            emotion_params = emotion_config.to_params()
            # 过滤掉已经在默认参数中的键
            filtered_params = {
                k: v
                for k, v in emotion_params.items()
                if k in params
                or k not in ["ref_audio_path", "prompt_text", "prompt_lang"]
            }
            params.update(filtered_params)
            logger.debug(f"使用情绪参数：{emotion_config.name}")

        # 合并额外参数
        if extra_params:
            filtered_params = {k: v for k, v in extra_params.items() if k in params}
            params.update(filtered_params)
            logger.debug(f"已更新已有参数：{filtered_params}")

        # 自动检测语言
        if params.get("text_lang") == "zh_ja_auto":
            detected = self._detect_lang(text) if text else "zh"
            logger.debug(f"zh_ja_auto 检测结果：{detected}")
            params["text_lang"] = detected

        # 检查缓存
        cached_audio = self.local_data.get_cached_audio(params)
        if cached_audio:
            cache_path, cached_data = cached_audio
            logger.debug("命中缓存，跳过 TTS 请求")
            return GSVRequestResult(
                ok=True,
                data=cached_data,
                text=str(params.get("text", "")),
                file_path=str(cache_path),
            )

        logger.debug(f"向 GSV 发起 TTS 请求，参数：{params}")
        result = await self.client.tts(params)

        if bool(result):
            cache_path = self.local_data.save_audio(result.data, params)
            if cache_path:
                result.file_path = str(cache_path)
        else:
            logger.error(f"TTS 推理失败：{result.error}")

        return result

    async def restart(self):
        result = await self.client.restart()
        if not result.ok:
            logger.error(f"重启失败：{result.error}")
