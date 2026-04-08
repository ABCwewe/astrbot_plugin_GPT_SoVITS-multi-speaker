#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPT-SoVITS 说话人配置批量生成脚本

使用方法：
1. 将此脚本放到模型根目录（包含所有说话人子目录的目录）
2. 运行：python3 generate_speakers_config.py
3. 脚本会在当前目录生成 speakers_config.json 文件
4. 将生成的内容复制到插件配置的 speakers 字段中
"""

import json
import os
import glob
from pathlib import Path


def find_model_files(speaker_dir: Path):
    """查找目录下的模型文件"""
    ckpt_files = list(speaker_dir.glob("*.ckpt"))
    pth_files = list(speaker_dir.glob("*.pth"))

    ckpt_path = str(ckpt_files[0]) if ckpt_files else ""
    pth_path = str(pth_files[0]) if pth_files else ""

    return ckpt_path, pth_path


def find_reference_audios(speaker_dir: Path):
    """查找参考音频文件"""
    # 可能的路径结构
    possible_paths = [
        speaker_dir / "reference_audios" / "中文" / "emotions",
        speaker_dir / "reference_audios" / "emotions",
        speaker_dir / "reference_audios" / "中文",
        speaker_dir / "emotions",
    ]

    audio_files = []
    for path in possible_paths:
        if path.exists() and path.is_dir():
            audio_files = list(path.glob("*.wav"))
            if audio_files:
                break

    return audio_files


def detect_language_from_name(dir_name: str) -> str:
    """根据目录名检测语言"""
    dir_name_lower = dir_name.lower()
    if "_zh" in dir_name_lower or "中文" in dir_name:
        return "zh"
    elif "_en" in dir_name_lower or "english" in dir_name_lower:
        return "en"
    elif "_ja" in dir_name_lower or "日语" in dir_name:
        return "ja"
    elif "_ko" in dir_name_lower or "韩语" in dir_name:
        return "ko"
    return "zh"  # 默认中文


def extract_speaker_name(dir_name: str) -> str:
    """从目录名提取说话人名称"""
    # 移除语言后缀，如 _ZH, _EN 等
    name = dir_name
    suffixes = ["_zh", "_en", "_ja", "_ko", "_ZH", "_EN", "_JA", "_KO"]
    for suffix in suffixes:
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name


def generate_emotion_from_filename(filename: str) -> dict:
    """从文件名生成情绪配置"""
    # 移除 .wav 后缀
    name = filename.replace(".wav", "")

    # 尝试从文件名提取情绪名称
    # 格式如："【默认】能开出龙须酥就好了…….wav" -> "默认"
    emotion_name = "默认"
    if "【" in name and "】" in name:
        try:
            emotion_name = name.split("【")[1].split("】")[0]
        except:
            pass

    # 提取参考文本（文件名中 【】 后面的部分）
    prompt_text = ""
    if "】" in name:
        prompt_text = name.split("】")[1].strip()
        # 清理一些特殊字符
        prompt_text = prompt_text.replace("……", "...")

    return {
        "name": emotion_name,
        "keywords": [],
        "ref_audio_path": "",  # 将在后面填充完整路径
        "prompt_text": prompt_text,
        "prompt_lang": "zh",
        "speed_factor": 1.0,
        "fragment_interval": 0.7,
    }


def scan_speakers(root_dir: Path):
    """扫描所有说话人目录"""
    speakers = []

    # 获取所有子目录
    for item in root_dir.iterdir():
        if not item.is_dir():
            continue

        # 跳过隐藏目录和特殊目录
        if item.name.startswith(".") or item.name.startswith("_"):
            continue

        print(f"扫描说话人目录: {item.name}")

        # 查找模型文件
        ckpt_path, pth_path = find_model_files(item)

        if not ckpt_path and not pth_path:
            print(f"  警告: 未找到模型文件，跳过: {item.name}")
            continue

        # 查找参考音频
        audio_files = find_reference_audios(item)

        # 生成说话人配置
        speaker_name = extract_speaker_name(item.name)
        language = detect_language_from_name(item.name)

        emotions = []
        for audio_file in audio_files:
            emotion = generate_emotion_from_filename(audio_file.name)
            emotion["ref_audio_path"] = str(audio_file.resolve())
            emotions.append(emotion)

        # 如果没有找到音频文件，添加一个默认配置
        if not emotions:
            emotions.append(
                {
                    "name": "默认",
                    "keywords": [],
                    "ref_audio_path": "",
                    "prompt_text": "",
                    "prompt_lang": language,
                    "speed_factor": 1.0,
                    "fragment_interval": 0.7,
                }
            )

        speaker_config = {
            "__template_key": "speaker",
            "speaker_name": speaker_name,
            "alias": "",
            "gpt_path": ckpt_path,
            "sovits_path": pth_path,
            "base_url": "http://127.0.0.1:9880",
            "timeout": 60,
            "text_lang": language,
            "emotions": json.dumps(emotions, ensure_ascii=False, indent=2),
        }

        speakers.append(speaker_config)
        print(f"  - GPT模型: {ckpt_path}")
        print(f"  - SoVITS模型: {pth_path}")
        print(f"  - 语言: {language}")
        print(f"  - 情绪数量: {len(emotions)}")

    return speakers


def main():
    # 获取当前目录
    root_dir = Path(".").resolve()

    print(f"=" * 50)
    print(f"GPT-SoVITS 说话人配置生成器")
    print(f"扫描目录: {root_dir}")
    print(f"=" * 50)
    print()

    # 扫描说话人
    speakers = scan_speakers(root_dir)

    if not speakers:
        print("错误: 未找到任何说话人配置")
        return

    print()
    print(f"=" * 50)
    print(f"共找到 {len(speakers)} 个说话人")
    print(f"=" * 50)

    # 生成配置
    config = {
        "enabled": True,
        "default_speaker": speakers[0]["speaker_name"] if speakers else "default",
        "speakers": speakers,
        "auto": {"only_llm_result": True, "tts_prob": 0.15, "max_msg_len": 50},
        "judge": {"enabled_llm": False, "provider_id": ""},
        "cache": {
            "enabled": True,
            "expire_hours": 0,
            "path": "data/plugins_data/astrbot_plugin_GPT_SoVITS/audio",
        },
    }

    # 输出配置文件
    output_file = root_dir / "speakers_config.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"配置文件已生成: {output_file}")
    print()
    print("使用方法:")
    print("1. 打开 AstrBot 插件配置页面")
    print("2. 将 speakers_config.json 中的 speakers 字段内容复制到配置中")
    print("3. 根据需要修改 base_url 等配置")


if __name__ == "__main__":
    main()
