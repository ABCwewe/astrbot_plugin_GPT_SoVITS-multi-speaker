from __future__ import annotations

import base64
import json
import random
import copy
from sys import maxsize

from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request
from astrbot.core import AstrBotConfig
from astrbot.core.message.components import Node, Plain, Record
from astrbot.core.platform import AstrMessageEvent
from astrbot.core.star.filter.command import GreedyStr

from .core.client import GSVApiClient, GSVRequestResult
from .core.config import PluginConfig
from .core.emotion import EmotionJudger
from .core.entry import SpeakerManager
from .core.local_data import LocalDataManager
from .core.service import GPTSoVITSService

if TYPE_CHECKING:
    from .core.config import EmotionConfig, SpeakerConfig

PLUGIN_NAME = "astrbot_plugin_GPT_SoVITS-multi-speaker"


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

        self._register_web_apis()

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

    # ==================== Pages Web API ====================

    def _register_web_apis(self) -> None:
        """注册 WebUI Pages 所需的 API 端点"""
        self.context.register_web_api(
            f"/{PLUGIN_NAME}/config",
            self._api_get_config,
            ["GET"],
            "获取插件完整配置",
        )
        self.context.register_web_api(
            f"/{PLUGIN_NAME}/config",
            self._api_save_config,
            ["POST"],
            "保存插件配置",
        )
        self.context.register_web_api(
            f"/{PLUGIN_NAME}/providers",
            self._api_get_providers,
            ["GET"],
            "获取可用的 LLM 提供商列表",
        )

    async def _api_get_config(self):
        """GET /config -> 返回当前完整配置，emotions 字段解析为列表"""
        try:
            data = copy.deepcopy(dict(self.cfg.raw_data()))
            speakers = data.get("speakers", [])
            for speaker in speakers:
                if isinstance(speaker, dict):
                    emotions_raw = speaker.get("emotions", "[]")
                    if isinstance(emotions_raw, str):
                        try:
                            speaker["emotions"] = json.loads(emotions_raw)
                        except json.JSONDecodeError:
                            speaker["emotions"] = []
            return json_response(data)
        except Exception as e:
            logger.error(f"获取配置失败: {e}")
            return error_response(f"获取配置失败: {e}", status_code=500)

    async def _api_save_config(self):
        """POST /config -> 验证并保存配置，emotions 字段序列化为 JSON 字符串"""
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                return error_response("无效的请求数据")

            data = copy.deepcopy(payload)

            speakers = data.get("speakers", [])
            for speaker in speakers:
                if isinstance(speaker, dict):
                    emotions = speaker.get("emotions")
                    if isinstance(emotions, list):
                        speaker["emotions"] = json.dumps(
                            emotions, ensure_ascii=False, indent=2
                        )
                    elif isinstance(emotions, str):
                        try:
                            json.loads(emotions)
                        except json.JSONDecodeError:
                            return error_response(
                                f"说话人 {speaker.get('speaker_name', '?')} 的情绪配置 JSON 无效"
                            )
                    elif emotions is None:
                        speaker["emotions"] = "[]"

            self.cfg._data.clear()
            self.cfg._data.update(data)

            cache_cfg = self.cfg._data.get("cache")
            if isinstance(cache_cfg, dict):
                cache_cfg.pop("path", None)

            self.cfg.save_config()

            await self._reload_after_config_save()

            logger.info("WebUI Pages 配置已更新并保存")
            return json_response({"success": True})
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return error_response(f"保存配置失败: {e}", status_code=500)

    async def _api_get_providers(self):
        """GET /providers -> 返回可用的 LLM 提供商列表"""
        try:
            providers = self.context.get_all_providers()
            result = []
            for p in providers:
                try:
                    meta = p.meta()
                    provider_id = meta.id
                    model_name = meta.model or provider_id
                except Exception:
                    provider_id = getattr(p, "id", "") or p.provider_config.get("id", "")
                    model_name = getattr(p, "model_name", "") or provider_id
                display_name = f"{model_name} ({provider_id})" if model_name else provider_id
                result.append({"id": provider_id, "name": display_name})
            return json_response({"providers": result})
        except Exception as e:
            logger.error(f"获取提供商列表失败: {e}")
            return error_response(f"获取提供商列表失败: {e}", status_code=500)

    async def _reload_after_config_save(self) -> None:
        """保存配置后重新初始化服务和客户端"""
        for client in self.clients.values():
            await client.close()
        self.clients.clear()
        self.services.clear()

        self.cfg = PluginConfig(self.cfg._data, self.context)
        self.local_data = LocalDataManager(self.cfg)
        self.speaker_mgr = SpeakerManager(self.cfg)
        self.judger = EmotionJudger(self.cfg, self.speaker_mgr)

        self._init_services()

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

    def _parse_say_pattern(
        self, message_str: str
    ) -> tuple[str | None, str | None, str]:
        """
        解析 "说 " 触发模式（on-message hook）

        "说" 字后必须紧跟一个空格才会触发，避免误触。

        支持格式：
        - "说 <文本>"                          -> (默认说话人, None, 文本)
        - "<说话人>说 <文本>"                   -> (说话人, None, 文本)
        - "<说话人><情绪>说 <文本>"             -> (说话人, 情绪, 文本)
        - "<情绪>说 <文本>"                     -> (默认说话人, 情绪, 文本)

        Returns:
            (speaker_name, emotion_name, text) 或 (None, None, "")
        """
        msg = message_str.strip()
        if not msg:
            return None, None, ""

        say_trigger = "说 "

        # 情况 1: 以 "说 " 开头 -> 默认说话人，无情绪
        if msg.startswith(say_trigger):
            text = msg[len(say_trigger):].strip()
            if text:
                return self.cfg.default_speaker, None, text
            return None, None, ""

        # 收集所有 (名称, 说话人名, 说话人配置) 对，按名称长度降序
        all_names: list[tuple[str, str, SpeakerConfig]] = []
        for speaker_name in self.speaker_mgr.get_all_speaker_names():
            speaker_cfg = self.speaker_mgr.get_speaker(speaker_name)
            if not speaker_cfg:
                continue
            for name in [speaker_name] + speaker_cfg.alias_list:
                all_names.append((name, speaker_name, speaker_cfg))
        all_names.sort(key=lambda x: len(x[0]), reverse=True)

        # 情况 2/3: 说话人 + 可选情绪 + 说
        for name, speaker_name, speaker_cfg in all_names:
            if not msg.startswith(name):
                continue
            remainder = msg[len(name):]

            # 说话人 + 说
            if remainder.startswith(say_trigger):
                text = remainder[len(say_trigger):].strip()
                if text:
                    return speaker_name, None, text
                return None, None, ""

            # 说话人 + 情绪 + 说
            for emotion_name in sorted(
                speaker_cfg.get_emotion_names(), key=len, reverse=True
            ):
                if remainder.startswith(emotion_name):
                    after_emotion = remainder[len(emotion_name):]
                    if after_emotion.startswith(say_trigger):
                        text = after_emotion[len(say_trigger):].strip()
                        if text:
                            return speaker_name, emotion_name, text
                        return None, None, ""

        # 情况 4: 情绪 + 说（使用默认说话人）
        default_speaker_cfg = self.speaker_mgr.get_speaker(self.cfg.default_speaker)
        if default_speaker_cfg:
            for emotion_name in sorted(
                default_speaker_cfg.get_emotion_names(), key=len, reverse=True
            ):
                if msg.startswith(emotion_name):
                    remainder = msg[len(emotion_name):]
                    if remainder.startswith(say_trigger):
                        text = remainder[len(say_trigger):].strip()
                        if text:
                            return self.cfg.default_speaker, emotion_name, text
                        return None, None, ""

        return None, None, ""

    async def _get_emotion_params(
        self,
        event: AstrMessageEvent,
        speaker_name: str,
        text: str,
        specified_emotion_name: str | None = None,
        is_command: bool = False,
    ) -> "EmotionConfig | None":
        """
        获取情绪配置

        优先级：指令指定情绪 > LLM 判断情绪 > 关键词匹配情绪

        Args:
            event: 消息事件
            speaker_name: 说话人名称
            text: 文本内容
            specified_emotion_name: 指令中指定的情绪名称
            is_command: 是否由指令触发（区别于自动触发）

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
        use_llm_judge = False
        if is_command:
            if self.cfg.judge.enabled_command:
                speaker_cfg = self.speaker_mgr.get_speaker(speaker_name)
                if speaker_cfg and len(speaker_cfg.emotions_list) > 1:
                    use_llm_judge = True
        else:
            if self.cfg.judge.enabled_llm:
                use_llm_judge = True

        if use_llm_judge:
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

        # 获取情绪参数（自动触发）
        emotion_config = await self._get_emotion_params(
            event, speaker_name, combined_text, is_command=False
        )

        service = await self._get_or_create_service(speaker_name)
        res = await service.inference(combined_text, emotion_config=emotion_config)

        if not bool(res):
            return

        chain.clear()
        chain.append(self._to_record(res))

    @filter.event_message_type(filter.EventMessageType.ALL, priority=maxsize - 10)
    async def on_say_message(self, event: AstrMessageEvent):
        """on-message hook：检测 <说话人><情绪?>说 <文本> 模式"""
        if not self.cfg.enabled:
            return

        speaker_name, emotion_name, text = self._parse_say_pattern(
            event.message_str
        )
        if speaker_name is None:
            return

        # 验证说话人是否存在（支持别名查找）
        speaker_cfg = self.speaker_mgr.find_speaker_by_name_or_alias(speaker_name)
        if not speaker_cfg:
            return
        speaker_name = speaker_cfg.speaker_name

        # 获取情绪配置（指令触发）
        emotion_config = await self._get_emotion_params(
            event, speaker_name, text, emotion_name, is_command=True
        )

        service = await self._get_or_create_service(speaker_name)
        res = await service.inference(text, emotion_config=emotion_config)

        event.stop_event()

        if not bool(res):
            yield event.plain_result(res.error)
            return

        yield event.chain_result([self._to_record(res)])

    @filter.command_group("GSV", alias={"gsv"})
    def gsv_group(self):
        """GSV 管理指令组"""

    @gsv_group.command("列表", alias={"list"})
    async def gsv_list(self, event: AstrMessageEvent):
        """列出所有可用说话人"""
        if not self.cfg.enabled:
            return
        uin = event.get_self_id()
        yield event.chain_result(self.list_speakers_nodes(int(uin) if uin else 0))

    @gsv_group.command("当前", alias={"current"})
    async def gsv_current(self, event: AstrMessageEvent):
        """查看当前默认说话人"""
        if not self.cfg.enabled:
            return
        yield event.plain_result(f"当前默认说话人：{self.cfg.default_speaker}")

    @gsv_group.command("设置默认", alias={"设置"})
    async def gsv_set_default(self, event: AstrMessageEvent, speaker_name: GreedyStr):
        """设置默认说话人"""
        if not self.cfg.enabled:
            return
        speaker_name = (speaker_name or "").strip()
        if not speaker_name:
            yield event.plain_result("用法：GSV 设置默认 <说话人>")
            return
        speaker_cfg = self.speaker_mgr.find_speaker_by_name_or_alias(speaker_name)
        if not speaker_cfg:
            yield event.plain_result(f"说话人 {speaker_name} 不存在")
            return
        self.cfg.default_speaker = speaker_cfg.speaker_name
        self.cfg.save_config()
        yield event.plain_result(f"已设置默认说话人为：{speaker_cfg.speaker_name}")

    @gsv_group.command("重启", alias={"重载"})
    async def gsv_restart(self, event: AstrMessageEvent):
        """重启 GPT-SoVITS"""
        if not self.cfg.enabled:
            return
        yield event.plain_result("重启 TTS 中...(报错信息请忽略，等待一会即可完成重启)")
        service = await self._get_or_create_service(self.cfg.default_speaker)
        await service.restart()

    @gsv_group.command("帮助", alias={"help"})
    async def gsv_help(self, event: AstrMessageEvent):
        """查看 GSV 指令帮助"""
        if not self.cfg.enabled:
            return
        yield event.plain_result(
            "GSV 指令用法：\n"
            "- GSV 列表：列出所有说话人\n"
            "- GSV 当前：查看当前默认说话人\n"
            "- GSV 设置默认 <说话人>：设置默认说话人\n"
            "- GSV 重启：重启 TTS 服务\n"
            "- GSV 帮助：查看此帮助\n\n"
            "语音合成：直接发送 <说话人>[情绪]说 <内容>，"
            "例如「丹瑾说 你好」「丹瑾生气说 不喜欢你」"
        )

    def list_speakers_nodes(self, uin: int) -> list[Node]:
        """生成说话人列表的 Node 节点（单条消息包含所有说话人）"""
        speakers = self.speaker_mgr.get_all_speaker_names()

        lines = ["可用说话人："]
        for name in speakers:
            speaker = self.speaker_mgr.get_speaker(name)
            emotion_names = speaker.get_emotion_names() if speaker else []
            emotion_count = len(emotion_names)
            default_marker = " (默认)" if name == self.cfg.default_speaker else ""
            line = f"- {name} ({emotion_count} 个情绪){default_marker}"
            if emotion_names:
                line += f"\n  情绪：{', '.join(emotion_names)}"
            lines.append(line)

        content = Plain("\n".join(lines))
        return [Node(uin=uin, name="TTS 助手", content=[content])]

    @filter.llm_tool()
    async def gsv_tts(self, event: AstrMessageEvent, message: str = ""):
        """
        用语音输出要讲的话
        Args:
            message(string): 要讲的话
        """
        try:
            speaker_name = self.cfg.default_speaker

            # 获取情绪参数（LLM 工具触发）
            emotion_config = await self._get_emotion_params(
                event, speaker_name, message, is_command=False
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
