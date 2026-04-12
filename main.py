from __future__ import annotations

import base64
import random

from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Plain, Record
from astrbot.core.platform import AstrMessageEvent

from .core.client import GSVApiClient, GSVRequestResult
from .core.config import PluginConfig
from .core.emotion import EmotionJudger
from .core.entry import SpeakerManager
from .core.local_data import LocalDataManager
from .core.service import GPTSoVITSService

if TYPE_CHECKING:
    from .core.config import EmotionConfig


class GPTSoVITSPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.cfg = PluginConfig(config, context)
        self.local_data = LocalDataManager(self.cfg)
        self.speaker_mgr = SpeakerManager(self.cfg)
        self.judger = EmotionJudger(self.cfg, self.speaker_mgr)

        # 为每个说话人创建独立的服务和客户端
        self.services: dict[str, GPTSoVITSService] = {}
        self.clients: dict[str, GSVApiClient] = {}
        self._init_services()

    def _init_services(self):
        """初始化所有说话人的服务和客户端"""
        for speaker_name in self.speaker_mgr.get_all_speaker_names():
            self._create_service(speaker_name)

    def _create_service(self, speaker_name: str) -> GPTSoVITSService:
        """创建说话人对应的服务实例（同步，不加载模型）"""
        if speaker_name not in self.services:
            speaker_cfg = self.speaker_mgr.get_speaker(speaker_name)
            if not speaker_cfg:
                raise ValueError(f"说话人 {speaker_name} 不存在")

            self.clients[speaker_name] = GSVApiClient(speaker_cfg)
            self.services[speaker_name] = GPTSoVITSService(
                speaker_cfg,
                self.clients[speaker_name],
                self.local_data,
                tts_params=self.cfg.tts_params,
            )

        return self.services[speaker_name]

    async def _get_or_create_service(self, speaker_name: str) -> GPTSoVITSService:
        """获取或创建说话人对应的服务实例，并加载模型（如需要）"""
        service = self._create_service(speaker_name)

        await service.load_model()

        return service

    async def initialize(self):
        if self.cfg.enabled:
            default_speaker = self.cfg.default_speaker
            if default_speaker in self.speaker_mgr.get_all_speaker_names():
                self._get_or_create_service(default_speaker)

    async def terminate(self):
        # 关闭所有客户端
        for client in self.clients.values():
            await client.close()

    @staticmethod
    def _to_record(res: GSVRequestResult) -> Record:
        if res.file_path:
            try:
                return Record.fromFileSystem(res.file_path)
            except Exception:
                logger.warning(f"无法读取文件：{res.file_path}, 已忽略")
                pass

        if not res.data:
            raise ValueError("无法获取结果数据")

        b64 = base64.urlsafe_b64encode(res.data).decode()
        return Record.fromBase64(b64)

    def _parse_say_command(
        self, message_str: str
    ) -> tuple[str | None, str | None, str]:
        """
        解析'说'指令参数

        返回：(speaker_name, emotion_name, text)
        - 说 你好 -> (None, None, "你好") 使用默认说话人
        - 说 B 你好 -> ("B", None, "你好")
        - 说 B 开心 你好 -> ("B", "开心", "你好")
        """
        parts = message_str.split()

        if len(parts) == 0:
            return None, None, ""

        speaker_name = None
        emotion_name = None
        text_start = 0

        # 先尝试通过名称或别名查找说话人
        if parts[0]:
            speaker_cfg = self.speaker_mgr.find_speaker_by_name_or_alias(parts[0])
            if speaker_cfg:
                speaker_name = speaker_cfg.speaker_name
                text_start = 1

        # 检查第二个词是否为情绪名称
        if text_start < len(parts):
            current_speaker = speaker_name or self.cfg.default_speaker
            speaker_cfg = self.speaker_mgr.find_speaker_by_name_or_alias(
                current_speaker
            )

            if speaker_cfg:
                emotion_names = speaker_cfg.get_emotion_names()
                if parts[text_start] in emotion_names:
                    emotion_name = parts[text_start]
                    text_start += 1

        # 剩余部分为文本
        text = " ".join(parts[text_start:]) if text_start < len(parts) else ""

        return speaker_name, emotion_name, text

    async def _get_emotion_params(
        self,
        event: AstrMessageEvent,
        speaker_name: str,
        text: str,
        specified_emotion_name: str | None = None,
    ) -> "EmotionConfig | None":
        """
        获取情绪配置

        优先级：指令指定情绪 > LLM 判断情绪 > 关键词匹配情绪

        Args:
            event: 消息事件
            speaker_name: 说话人名称
            text: 文本内容
            specified_emotion_name: 指令中指定的情绪名称

        Returns:
            EmotionConfig | None: 情绪配置
        """
        emotion_config = None

        # 优先级 1: 指令指定的情绪
        if specified_emotion_name:
            emotion_config = self.speaker_mgr.get_emotion(
                speaker_name, specified_emotion_name
            )
            if emotion_config:
                logger.debug(f"使用指令指定的情绪：{specified_emotion_name}")
                return emotion_config

        # 优先级 2: LLM 判断情绪
        if self.cfg.judge.enabled_llm:
            emotion_label = await self.judger.judge_emotion(
                event, speaker_name=speaker_name, text=text
            )
            if emotion_label:
                emotion_config = self.speaker_mgr.get_emotion(
                    speaker_name, emotion_label
                )
                if emotion_config:
                    logger.debug(f"使用 LLM 判断的情绪：{emotion_label}")
                    return emotion_config

        # 优先级 3: 关键词匹配
        emotion_config = self.speaker_mgr.match_emotion(speaker_name, text)
        if emotion_config:
            logger.debug("使用关键词匹配的情绪")
            return emotion_config

        return None

    @filter.on_decorating_result(priority=14)
    async def on_decorating_result(self, event: AstrMessageEvent):
        """消息入口（自动触发 TTS）"""
        if not self.cfg.enabled:
            return
        cfg = self.cfg.auto

        result = event.get_result()
        if not result:
            return
        chain = result.chain
        if not chain:
            return
        if cfg.only_llm_result and not result.is_llm_result():
            return
        if random.random() > cfg.tts_prob:
            return

        # 收集所有 Plain 文本片段
        plain_texts = []
        for seg in chain:
            if isinstance(seg, Plain):
                plain_texts.append(seg.text)

        # 仅允许只含有 Plain 的消息链通过
        if len(plain_texts) != len(chain):
            return

        # 合并所有 Plain 文本
        combined_text = "\n".join(plain_texts)

        # 仅允许一定长度以下的文本通过
        if len(combined_text) > cfg.max_msg_len:
            return

        # 使用默认说话人
        speaker_name = self.cfg.default_speaker

        # 获取情绪参数
        emotion_config = await self._get_emotion_params(
            event, speaker_name, combined_text
        )

        service = await self._get_or_create_service(speaker_name)
        res = await service.inference(combined_text, emotion_config=emotion_config)

        if not bool(res):
            return

        chain.clear()
        chain.append(self._to_record(res))

    @filter.command("说")
    async def on_command(self, event: AstrMessageEvent):
        """说 [说话人] [情绪] <内容>"""
        if not self.cfg.enabled:
            return

        # 去掉指令名 "说"
        msg = event.message_str
        stripped = False
        for alias in ["说 "]:
            if msg.startswith(alias):
                msg = msg[len(alias) :]
                stripped = True
                break
        if not stripped:
            if msg.startswith("说"):
                msg = msg[1:]
            msg = msg.lstrip()

        speaker_name, emotion_name, text = self._parse_say_command(msg)

        # 使用默认说话人
        if not speaker_name:
            speaker_name = self.cfg.default_speaker

        # 验证说话人是否存在（支持别名查找）
        speaker_cfg = self.speaker_mgr.find_speaker_by_name_or_alias(speaker_name)
        if not speaker_cfg:
            yield event.plain_result(f"说话人 {speaker_name} 不存在")
            return

        # 使用实际的说话人名称
        speaker_name = speaker_cfg.speaker_name

        # 获取情绪配置
        emotion_config = await self._get_emotion_params(
            event, speaker_name, text, emotion_name
        )

        service = await self._get_or_create_service(speaker_name)
        res = await service.inference(text, emotion_config=emotion_config)

        if not bool(res):
            yield event.plain_result(res.error)
            return

        yield event.chain_result([self._to_record(res)])

    @filter.command("设置默认说话人")
    async def set_default_speaker(self, event: AstrMessageEvent, speaker_name: str):
        """设置全局默认说话人"""
        # 支持别名查找
        speaker_cfg = self.speaker_mgr.find_speaker_by_name_or_alias(speaker_name)
        if not speaker_cfg:
            yield event.plain_result(f"说话人 {speaker_name} 不存在")
            return

        # 使用实际的说话人名称
        self.cfg.default_speaker = speaker_cfg.speaker_name
        self.cfg.save_config()
        yield event.plain_result(f"已设置默认说话人为：{speaker_cfg.speaker_name}")

    @filter.command("重启 GSV", alias={"重启 gsv"})
    async def tts_control(self, event: AstrMessageEvent):
        """重启 GPT-SoVITS"""
        if not self.cfg.enabled:
            return
        yield event.plain_result("重启 TTS 中...(报错信息请忽略，等待一会即可完成重启)")
        service = await self._get_or_create_service(self.cfg.default_speaker)
        await service.restart()

    @filter.command("GSV")
    async def on_gsv_command(self, event: AstrMessageEvent):
        """GSV 管理指令（不合成语音）"""
        if not self.cfg.enabled:
            return

        # 去掉指令名 "GSV" 或 "gsv"
        msg = event.message_str
        stripped = False
        for alias in ["GSV ", "gsv "]:
            if msg.startswith(alias):
                msg = msg[len(alias) :]
                stripped = True
                break
        if not stripped:
            if msg.startswith("GSV") or msg.startswith("gsv"):
                msg = msg[3:]
            msg = msg.lstrip()

        if not msg:
            yield event.plain_result(
                "GSV 指令用法：\n- GSV 列表：列出所有说话人\n- GSV 当前：查看当前默认说话人\n- GSV 设置默认 <说话人>：设置默认说话人\n- GSV 重启：重启 TTS 服务"
            )
            return

        parts = msg.split()
        sub_cmd = parts[0] if parts else ""

        if sub_cmd == "列表":
            async for _ in self.list_speakers(event):
                pass
        elif sub_cmd == "当前":
            async for _ in self.current_speaker(event):
                pass
        elif sub_cmd in ["设置默认", "设置"]:
            if len(parts) < 2:
                yield event.plain_result("用法：GSV 设置默认 <说话人>")
                return
            speaker_name = " ".join(parts[1:])
            async for _ in self.set_default_speaker(event, speaker_name):
                pass
        elif sub_cmd in ["重启", "重载"]:
            async for _ in self.tts_control(event):
                pass
        else:
            yield event.plain_result(
                f"未知指令：{sub_cmd}\n可用指令：列表、当前、设置默认、重启"
            )

    async def list_speakers(self, event: AstrMessageEvent):
        """列出所有可用说话人"""
        speakers = self.speaker_mgr.get_all_speaker_names()
        if not speakers:
            yield event.plain_result("暂无可用说话人")
            return

        result = "可用说话人：\n"
        for name in speakers:
            speaker = self.speaker_mgr.get_speaker(name)
            emotion_names = speaker.get_emotion_names() if speaker else []
            emotion_count = len(emotion_names)
            default_marker = " (默认)" if name == self.cfg.default_speaker else ""
            result += f"- {name} ({emotion_count} 个情绪){default_marker}\n"
            if emotion_names:
                result += f"  情绪：{', '.join(emotion_names)}\n"

        yield event.plain_result(result)

    async def current_speaker(self, event: AstrMessageEvent):
        """查看当前默认说话人"""
        yield event.plain_result(f"当前默认说话人：{self.cfg.default_speaker}")

    @filter.llm_tool()
    async def gsv_tts(self, event: AstrMessageEvent, message: str = ""):
        """
        用语音输出要讲的话
        Args:
            message(string): 要讲的话
        """
        try:
            speaker_name = self.cfg.default_speaker

            # 获取情绪参数
            emotion_config = await self._get_emotion_params(
                event, speaker_name, message
            )

            service = await self._get_or_create_service(speaker_name)
            res = await service.inference(message, emotion_config=emotion_config)

            if not bool(res):
                return res.error

            seg = self._to_record(res)
            await event.send(event.chain_result([seg]))
            return None

        except Exception as e:
            return str(e)
