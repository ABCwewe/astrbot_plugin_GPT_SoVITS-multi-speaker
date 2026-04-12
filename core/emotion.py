import json

from astrbot.api import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .config import PluginConfig
from .entry import SpeakerManager


class EmotionJudger:
    def __init__(self, config: PluginConfig, speaker_mgr: SpeakerManager):
        self.cfg = config
        self.speaker_mgr = speaker_mgr

    async def judge_emotion(
        self,
        event: AstrMessageEvent,
        speaker_name: str,
        *,
        text: str = "",
        image_urls: list[str] | None = None,
    ) -> str | None:
        """
        使用 LLM 判断文本情感并返回情感标签。

        对外行为约定：
        - 本方法 **不会抛出异常**，失败时返回 None
        - 若 event.extra 中已存在 emotion，则直接使用（避免重复调用 LLM）
        - 成功解析后会将 emotion 写入 event.extra，供后续流程复用

        :param event: AstrBot 消息事件
        :param speaker_name: 说话人名称（用于获取该说话人的情绪列表）
        :param text: 需要进行情感分析的文本
        :param image_urls: 可选的图片 URL（用于多模态模型）
        :return:
            - 成功时返回情感标签字符串
            - 失败时返回 None
        """
        # 检查是否已有缓存的情感判断
        if cached := event.get_extra("emotion"):
            # 检查该情感是否在当前说话人的情绪列表中
            emotion_names = self.speaker_mgr.get_all_emotion_names(speaker_name)
            if cached in emotion_names:
                logger.debug(f"复用情感标签：{cached}")
                return cached

        try:
            provider = self.cfg.get_judge_provider(event.unified_msg_origin)

            # 获取当前说话人的所有情绪名称作为 labels
            labels = self.speaker_mgr.get_all_emotion_names(speaker_name)
            if not labels:
                logger.warning(f"说话人 {speaker_name} 没有配置任何情绪")
                return None

            system_prompt, prompt = self._build_prompt(text, labels)

            resp = await provider.text_chat(
                system_prompt=system_prompt,
                prompt=prompt,
                image_urls=image_urls,
            )

            emotion = self._parse_llm_response(resp.completion_text)

            # 验证返回的情感是否在可用列表中
            if emotion not in labels:
                logger.warning(f"LLM 返回的情感 {emotion} 不在可用列表中：{labels}")
                return None

            logger.debug(f"情感分析结果：{emotion}")

            event.set_extra("emotion", emotion)
            return emotion

        except Exception as e:
            logger.exception(f"情感分析失败：{e}")
            return None

    def _build_prompt(
        self,
        text: str,
        labels: list[str],
    ) -> tuple[str, str]:
        label_hint = f"只能从以下情感标签中选择：{labels}\n"

        system_prompt = (
            "你是一个情感分析专家。\n"
            f"{label_hint}"
            '如果没有对应的感情，请输出：{"emotion": "默认"}'
            "请严格按照 JSON 格式输出，不要包含任何多余内容。\n"
            '输出示例：{"emotion": "开心"}'
        )

        prompt = f"文本内容：{text}"
        return system_prompt, prompt

    def _parse_llm_response(self, text: str) -> str:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM 返回非 JSON: {text}") from e

        emotion = data.get("emotion")
        if not emotion or not isinstance(emotion, str):
            raise ValueError(f"LLM JSON 缺少或非法 emotion 字段：{data}")

        return emotion
