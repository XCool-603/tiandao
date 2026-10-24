import json
import re
import time
from typing import Dict, Any, List, Optional
from llm_client import LLMClient
from config import classify_genre

class DramaAgent:
    """
    【竖屏微短剧生成 Agent (Short Drama & Storyboard Producer)】
    将小说章节一键提炼转化为符合当红微短剧爆款工业标准的分集剧本与分镜表：
    - 0-5s 强黄金抓手 (Hook)
    - 40-70s 密集反转打脸 (Climax)
    - 85-90s 绝命断章卡点 (Cliffhanger)
    - 逐镜头分镜脚本 (景别、运镜、画面、对白/OS、音效配乐)
    - 可灵 (Kling AI) / 即梦 (Jimeng) 9:16 专业 AI 视频生成 Prompt
    - 支持一键导出 CSV (AI生视频批量表)、SRT (剪映字幕)、TXT (导演剧本)
    """

    def __init__(self, llm_client: LLMClient, model_name: str):
        self.llm = llm_client
        self.model = model_name

    def generate_from_chapter(
        self,
        book_title: str,
        genre: str,
        chapter_title: str,
        chapter_content: str,
        episode_num: int = 1,
        force_mock: bool = False
    ) -> Dict[str, Any]:
        """将指定章节转化为单集竖屏微短剧分镜剧本"""
        if force_mock:
            return self._generate_mock_drama(book_title, genre, chapter_title, episode_num)

        cat = classify_genre(genre, book_title)
        prompt = self._build_drama_prompt(book_title, genre, cat, chapter_title, chapter_content, episode_num)

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一位精通抖音、快手、ReelShort、番茄短剧的资深短剧制片人与分镜总导演。"
                    "擅长将长篇小说改编为快节奏、情绪拉满、冲突密集的爆款竖屏微短剧（单集时长约 90 秒）。"
                    "你必须严格返回纯 JSON 格式数据，不得输出任何前言、后记或 markdown 外部散文。"
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        try:
            resp_str = self.llm.call_chat(messages, model=self.model, temperature=0.6, max_tokens=3000)
            cleaned = self._clean_json_str(resp_str)
            parsed = json.loads(cleaned)
            # 校验并填充默认值
            parsed.setdefault("episode_num", episode_num)
            parsed.setdefault("episode_title", f"第{episode_num}集：{chapter_title}")
            parsed.setdefault("duration_sec", 90)
            parsed.setdefault("shots", [])
            parsed.setdefault("characters_in_scene", [])
            parsed["created_at"] = time.time()
            return parsed
        except Exception as e:
            print(f"[DramaAgent] LLM 解析短剧失败或异常: {e}，启用智能后备分镜构建")
            return self._generate_fallback_drama(book_title, genre, chapter_title, chapter_content, episode_num)

    def _build_drama_prompt(self, book_title: str, genre: str, cat: str, chapter_title: str, content: str, episode_num: int) -> str:
        # 截取前 3000 字正文以防超出上下文
        short_content = content[:3000] if len(content) > 3000 else content

        genre_guideline = ""
        if cat == "doomsday":
            genre_guideline = (
                "【末日求生特别指南】：\n"
                "1. 强化极端天灾/丧尸与主角惬意安全的强烈视觉反差（如外界零下50度暴风雪拍门，屋内主角身着单衣涮战斧牛排；或丧尸撕咬邻居，主角堡垒防弹电网瞬间爆头）。\n"
                "2. 恶霸/绿茶邻居道德绑架越猖狂，主角冷酷反杀打脸越要残忍利落，拒绝任何圣母妥协！\n"
            )
        elif cat == "urban":
            genre_guideline = (
                "【都市逆袭特别指南】：\n"
                "1. 强化反派傲慢嘲讽与主角隐藏神级马甲亮出时的极度震撼；\n"
                "2. 突出耳光清脆、资产查封、黑卡甩脸等爽点动作镜头。\n"
            )
        else:
            genre_guideline = (
                "【短剧戏剧张力指南】：\n"
                "1. 视听化呈现，少内心独白，多眼神、微表情、手部特写与爆发性动作；\n"
                "2. 台词狠、准、精炼，每句台词都要带刀子或带反转。\n"
            )

        return f"""请将以下长篇小说章节内容改编为一段【90秒标准竖屏短剧】（第 {episode_num} 集），并拆解为 8-12 个精细分镜头。

小说名：《{book_title}》
题材标签：{genre}
章节名：{chapter_title}
小说内容片段：
{short_content}

{genre_guideline}

【短剧结构标准要求】：
1. 0-5s 黄金Hook：第一眼就要有致命危机或巨大冲突抓人眼球；
2. 40-70s 高潮爆发：正面冲突对峙、恶霸破门/主角亮剑、残忍反杀或无情反转；
3. 85-90s 悬念断章：危机升级/神秘势力到来/致命一击前戛然而止，促使观众划向下一集；
4. 东方东亚面孔与精准性别强制约束（极其重要）：
   - 本剧所有人物必须明确指定为东亚面孔/中国人（East Asian / Chinese face），严禁生成白人或外国人面孔！
   - 提示词中必须严格遵循小说角色性别：女性角色必须显式使用 "beautiful Chinese woman / young East Asian female / heroine"；男性角色必须显式使用 "handsome Chinese man / young East Asian male / hero"；严禁女性被生成为男性！
5. 视频 Prompt 规范：为可灵 (Kling AI) 或即梦 (Jimeng) 提供提示词，必须符合 9:16 竖屏短剧视觉，电影级构图，逼真质感，人物特征一致，中英文双语。格式示例：
   "9:16 vertical short drama shot, [Chinese woman/man + 年龄 + 东方五官 + 服饰 + 镜头运镜], cinematic photorealistic lighting, dramatic contrast, 8k resolution, [中文核心画面与东方气质描述]"

【返回格式】：
请严格输出标准 JSON 对象，禁止包裹额外文本：
{{
  "episode_num": {episode_num},
  "episode_title": "第{episode_num}集：极具短剧爆款网感的集标题",
  "logline": "一句话剧情梗概（20-30字）",
  "duration_sec": 90,
  "hook_summary": "0-5秒抓手核心剧情",
  "climax_summary": "40-70秒高潮打脸/反转核心剧情",
  "cliffhanger": "85-90秒留钩子卡点悬念",
  "characters_in_scene": ["主要角色1", "主要角色2"],
  "shots": [
    {{
      "shot_num": 1,
      "shot_type": "特写 / 近景 / 中景 / 全景 / 俯拍 / 低角度仰拍",
      "camera_movement": "缓缓推近 / 快速切镜 / 水平摇镜 / 手持微晃 / 升格慢动作",
      "duration_sec": 4,
      "visual": "详细画面描述：角色动作、神态、光影氛围与环境细节",
      "dialogue": "角色台词（前缀角色名）或 画外音OS 或 (无对白)",
      "sfx_bgm": "音效与配乐情绪，如：沉重金属锁链声，狂躁风雪低鸣，紧张心跳重音",
      "ai_prompt": "Kling/Jimeng 提示词：9:16 vertical short drama shot, [英文主体与镜头描述], cinematic photorealistic lighting, dramatic contrast, 8k resolution, [中文核心描述]"
    }}
  ]
}}
"""

    def _clean_json_str(self, text: str) -> str:
        text = text.strip()
        # 去除 markdown 代码块
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        # 寻找最外层的 {}
        m = re.search(r'(\{[\s\S]*\})', text)
        if m:
            text = m.group(1)
        return text

    def _generate_mock_drama(self, book_title: str, genre: str, chapter_title: str, episode_num: int) -> Dict[str, Any]:
        return {
            "episode_num": episode_num,
            "episode_title": f"第{episode_num}集：零下六十度！开门我就杀",
            "logline": "全球天灾暴雪降临，恶霸邻居持刀砸门抢粮，主角隔着防弹合金门悠然吃和牛牛排冷眼反杀。",
            "duration_sec": 90,
            "hook_summary": "暴风雪呼啸撞击窗棱，防盗门被铁锤猛砸，恶霸手持剔骨尖刀狞笑逼近！",
            "climax_summary": "主角打开微光单向视窗，单手搭在特种合金弩上，反手将企图破门的恶霸手指当场射穿！",
            "cliffhanger": "整栋楼业主群突然响起警报，楼道深处传来了丧尸化的非人嘶吼……",
            "characters_in_scene": ["林越", "张彪", "苏晴"],
            "shots": [
                {
                    "shot_num": 1,
                    "shot_type": "特写",
                    "camera_movement": "快速推近",
                    "duration_sec": 3,
                    "visual": "昏暗走廊，寒气凝结成霜。一柄锈迹斑斑的开山砍刀狠砸在铁门猫眼上，火星四溅。",
                    "dialogue": "张彪（凶残咆哮）：林越！我知道你屯了肉！今天不把吃的交出来，老子剁碎了你！",
                    "sfx_bgm": "刺耳金属撞击巨响，寒风尖啸混杂狂躁心跳声",
                    "ai_prompt": "9:16 vertical short drama shot, rusty machete violently chopping on steel security door, sparks flying in freezing dark apartment corridor, hyper-realistic, dramatic shadows, 8k --ar 9:16 铁门被砍刀猛劈火花飞溅"
                },
                {
                    "shot_num": 2,
                    "shot_type": "中景",
                    "camera_movement": "缓缓横移",
                    "duration_sec": 4,
                    "visual": "门内温暖如春，地暖数字显示26℃。林越身穿黑色真丝睡袍，左手端着红酒，右手优雅翻转平底锅中的A5战斧牛排。",
                    "dialogue": "林越（画外音冷笑）：前世就是你们这帮禽兽把我分食……这一世，你们连一粒米也别想碰。",
                    "sfx_bgm": "滋滋作响的热油煎肉声与门外的狂风撞门声形成尖锐反差，优雅古典交响低回",
                    "ai_prompt": "9:16 vertical shot, handsome cold young man in luxury silk robe cooking wagyu tomahawk steak inside ultra-modern warm shelter, snow visible through thick bulletproof glass, cinematic warm lighting, 8k 避难所内奢华吃肉"
                },
                {
                    "shot_num": 3,
                    "shot_type": "特写",
                    "camera_movement": "升格慢动作",
                    "duration_sec": 4,
                    "visual": "猫眼视窗滑开，主角眼神如鹰隼般冰冷，滑轮复合弩的黑钛合金箭头在暗光中闪烁着死神的光芒。",
                    "dialogue": "林越（声音平静如冰）：倒数三秒，不滚，死。",
                    "sfx_bgm": "机械弓弦紧绷拉满的金属咬合尖锐声，音效骤停陷入死寂",
                    "ai_prompt": "9:16 vertical extreme close up, sharp titanium hunting crossbow aimed at viewer through a narrow security slot, cold cruel eyes behind the scope, hyper-realistic, cinematic thriller lighting, 8k 瞄准镜与冷酷眼神特写"
                },
                {
                    "shot_num": 4,
                    "shot_type": "中近景",
                    "camera_movement": "手持剧烈晃动",
                    "duration_sec": 4,
                    "visual": "走廊外张彪狞笑变僵，一只冰冷惨白、布满青黑尸斑的手突然从身后楼梯拐角搭上了他的肩膀！",
                    "dialogue": "张彪（惊恐惨叫）：什么东西？！别咬……啊啊啊！",
                    "sfx_bgm": "非人恶鬼撕裂骨骼的嘶吼与骨折脆响，尖锐警报拉响",
                    "ai_prompt": "9:16 vertical horror thriller shot, zombie pale mutated claw grabbing thug's shoulder from dark freezing stairway, terrified expression, high motion blur, dramatic rim light, 8k 丧尸变异鬼爪搭上肩膀"
                }
            ],
            "created_at": time.time()
        }

    def _generate_fallback_drama(self, book_title: str, genre: str, chapter_title: str, content: str, episode_num: int) -> Dict[str, Any]:
        """降级兜底生成"""
        first_line = content.strip().splitlines()[0] if content.strip() else chapter_title
        return {
            "episode_num": episode_num,
            "episode_title": f"第{episode_num}集：{chapter_title}",
            "logline": f"《{book_title}》高能冲突转折点，核心人物激烈对抗展开。",
            "duration_sec": 90,
            "hook_summary": f"开场直接展现危机：{first_line[:40]}……",
            "climax_summary": "多方势力正面对决，力量反差与打脸反转瞬间引爆全场。",
            "cliffhanger": "致命危机再度逼近，更大风暴即将席卷而至。",
            "characters_in_scene": ["主角", "对手"],
            "shots": [
                {
                    "shot_num": 1,
                    "shot_type": "特写",
                    "camera_movement": "快速推近",
                    "duration_sec": 4,
                    "visual": "画面从暗部快速切出，主角目光如电，紧盯眼前突发的巨大变故。",
                    "dialogue": f"主角（沉声）：这世道，讲道理已经没用了。",
                    "sfx_bgm": "重低音沉闷震荡，紧张弦乐渐起",
                    "ai_prompt": f"9:16 vertical short drama opening shot, intense determined protagonist face close up, dark cinematic lighting, dynamic angle, high detail, 8k, 《{book_title}》开场特写"
                },
                {
                    "shot_num": 2,
                    "shot_type": "中景",
                    "camera_movement": "水平摇镜",
                    "duration_sec": 5,
                    "visual": "对手露出贪婪张狂的神态，步步逼近，身后众人蠢蠢欲动。",
                    "dialogue": "对手（嘲讽冷笑）：交出东西，还能留你全尸！",
                    "sfx_bgm": "刺耳武器出鞘声，周围人群哄笑起哄",
                    "ai_prompt": "9:16 vertical short drama scene, arrogant villain sneering with armed thugs behind, dramatic tension, photorealistic, cinematic movie still, 8k 反派嚣张逼近"
                },
                {
                    "shot_num": 3,
                    "shot_type": "全景",
                    "camera_movement": "升格慢动作",
                    "duration_sec": 5,
                    "visual": "主角骤然暴起，底牌掀开，一道恐怖能量/杀招横扫全场，震退所有敌人。",
                    "dialogue": "主角（暴喝）：就凭你们，也配？！",
                    "sfx_bgm": "震耳欲聋的爆裂声与重重倒地声，震撼管弦高潮",
                    "ai_prompt": "9:16 vertical short drama climax, epic power counterattack, shockwave dispersing enemies, cinematic action freeze frame, hyper-realistic, 8k 主角惊天反杀"
                },
                {
                    "shot_num": 4,
                    "shot_type": "近景",
                    "camera_movement": "缓缓拉远",
                    "duration_sec": 4,
                    "visual": "主角站在残局中央，阴影处一双更阴森恐怖的血红眼睛缓缓睁开。",
                    "dialogue": "画外音OS：真正的灾难……才刚刚开始！",
                    "sfx_bgm": "急促心跳声戛然而止，余音袅袅",
                    "ai_prompt": "9:16 vertical cliffhanger shot, protagonist standing victorious while ominous glowing red eyes watch from dark background, mysterious thriller, 8k 悬念血眼注视"
                }
            ],
            "created_at": time.time()
        }

    # ================= 导出实用工具 =================

    @staticmethod
    def export_shots_csv(drama_data: Dict[str, Any]) -> str:
        """导出为可灵/即梦批量生图生视频的 CSV 格式文本"""
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["镜号", "景别", "运镜方式", "时长(秒)", "画面描述", "对白台词/OS", "音效配乐", "AI视频提示词(9:16)"])
        for shot in drama_data.get("shots", []):
            writer.writerow([
                shot.get("shot_num", ""),
                shot.get("shot_type", ""),
                shot.get("camera_movement", ""),
                shot.get("duration_sec", ""),
                shot.get("visual", ""),
                shot.get("dialogue", ""),
                shot.get("sfx_bgm", ""),
                shot.get("ai_prompt", "")
            ])
        return output.getvalue()

    @staticmethod
    def export_srt(drama_data: Dict[str, Any]) -> str:
        """导出为剪映可直接导入的标准 SRT 字幕文件"""
        def format_time(seconds: float) -> str:
            hrs = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int((seconds - int(seconds)) * 1000)
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

        srt_lines = []
        cur_time = 0.0
        idx = 1
        for shot in drama_data.get("shots", []):
            dur = float(shot.get("duration_sec", 4))
            diag = shot.get("dialogue", "").strip()
            if diag and diag != "(无对白)":
                start_str = format_time(cur_time)
                end_str = format_time(cur_time + dur)
                srt_lines.append(f"{idx}")
                srt_lines.append(f"{start_str} --> {end_str}")
                srt_lines.append(diag)
                srt_lines.append("")
                idx += 1
            cur_time += dur
        return "\n".join(srt_lines)

    @staticmethod
    def export_script_txt(drama_data: Dict[str, Any]) -> str:
        """导出为导演/编剧排版打印的标准短剧分镜表 TXT"""
        title = drama_data.get("episode_title", "竖屏微短剧")
        logline = drama_data.get("logline", "")
        hook = drama_data.get("hook_summary", "")
        climax = drama_data.get("climax_summary", "")
        cliff = drama_data.get("cliffhanger", "")
        dur = drama_data.get("duration_sec", 90)

        lines = [
            f"============================================================",
            f"【爆款竖屏微短剧导演分镜脚本】{title}",
            f"预估单集时长：{dur}秒 | 视频画幅：9:16 (竖屏)",
            f"剧情梗概：{logline}",
            f"------------------------------------------------------------",
            f"【0-5s 黄金Hook】: {hook}",
            f"【40-70s 核心高潮】: {climax}",
            f"【85-90s 卡点断章】: {cliff}",
            f"============================================================\n",
            f"【分镜头明细】\n"
        ]

        for s in drama_data.get("shots", []):
            lines.append(f"▶ 镜头 {s.get('shot_num', 1)} | 【{s.get('shot_type', '')}】 | 运镜：{s.get('camera_movement', '')} | 时长：{s.get('duration_sec', 0)}s")
            lines.append(f"  [画面]: {s.get('visual', '')}")
            lines.append(f"  [台词]: {s.get('dialogue', '')}")
            lines.append(f"  [音效]: {s.get('sfx_bgm', '')}")
            lines.append(f"  [AI Prompt]: {s.get('ai_prompt', '')}")
            lines.append("-" * 50)

        return "\n".join(lines)
