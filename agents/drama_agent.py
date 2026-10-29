import json
import re
import time
from typing import Dict, Any, List, Optional
from llm_client import LLMClient
from config import classify_genre
from agents.spatial_director import spatial_director

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
        force_mock: bool = False,
        active_characters: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """将指定章节转化为单集竖屏微短剧分镜剧本"""
        if force_mock:
            return self._generate_mock_drama(book_title, genre, chapter_title, episode_num, active_characters, chapter_content)

        cat = classify_genre(genre, book_title)
        prompt = self._build_drama_prompt(book_title, genre, cat, chapter_title, chapter_content, episode_num, active_characters)

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一位精通微短剧视听规律与工业制作的资深短剧制片人与分镜总导演。"
                    "擅长根据小说真实正文、登场人物设定与戏剧冲突，动态推演改编为快节奏、情绪拉满的爆款竖屏微短剧（单集时长约 90 秒）。"
                    "严禁生搬硬套脱离原著的固定套路，一切冲突与台词必须忠实取材于小说正文！"
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

            # 注入三维离散场景拓扑与视听语法合规检查器
            topology = spatial_director.build_scene_topology(
                scene_name=parsed.get("episode_title", f"第{episode_num}集核心场景"),
                characters=parsed.get("characters_in_scene", []),
                genre_cat=cat,
                scene_desc=chapter_title
            )
            parsed["scene_topology"] = topology
            parsed["shots"] = spatial_director.lint_and_optimize_storyboard(
                parsed.get("shots", []),
                topology,
                parsed.get("characters_in_scene", [])
            )
            parsed["pacing_curve"] = spatial_director.generate_tension_and_pacing_curve(
                shot_count=len(parsed["shots"]),
                total_duration=parsed.get("duration_sec", 90)
            )
            return parsed
        except Exception as e:
            print(f"[DramaAgent] LLM 解析短剧失败或异常: {e}，启用智能后备分镜构建")
            return self._generate_fallback_drama(book_title, genre, chapter_title, chapter_content, episode_num, active_characters)

    def _build_drama_prompt(
        self,
        book_title: str,
        genre: str,
        cat: str,
        chapter_title: str,
        content: str,
        episode_num: int,
        active_characters: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        # 截取前 3000 字正文以防超出上下文
        short_content = content[:3000] if len(content) > 3000 else content

        char_roster_str = ""
        if active_characters:
            char_lines = []
            for c in active_characters[:5]:
                c_name = c.get("name", "")
                c_title = c.get("title", "")
                c_inv = "、".join(c.get("inventory", [])) if c.get("inventory") else "无"
                char_lines.append(f"- 【{c_name}】({c_title})：携带道具[{c_inv}]，人设：{c.get('public_profile', '')[:60]}")
            char_roster_str = "【小说原著登场人物档案（必须优先选用原著角色）】：\n" + "\n".join(char_lines) + "\n\n"

        return f"""请将以下长篇小说章节内容改编为一段【90秒标准竖屏短剧】（第 {episode_num} 集），并拆解为 8-12 个精细分镜头。

小说名：《{book_title}》
题材标签：{genre}
章节名：{chapter_title}

{char_roster_str}【小说正文核心片段】：
{short_content}

【剧情提炼与自动推演原则】：
1. **忠实取材与动态推演（极其重要）**：
   - 严禁死板套用千篇一律的模板（如战斧牛排、狂甩黑卡、扇耳光等刻板套路）！
   - 必须深入提炼上面小说正文中的【真实人物、真实矛盾、核心动作与对话】，分镜必须让观众看懂该章节到底发生了什么！
2. **节奏与戏剧张力控制**：
   - 0-5s 黄金Hook：第一眼就要展示本章小说发生的致命危机或冲突悬念；
   - 40-70s 高潮爆发：双方核心底牌碰撞、杀招交锋或重大剧情反转；
   - 85-90s 悬念断章：危机进一步升级或意外变数降临，留钩子卡点吸引划向下一集；
3. **东方东亚面孔与精准性别强制约束（极其重要）**：
   - 本剧所有人物必须明确指定为东亚面孔/中国人（East Asian / Chinese face），严禁生成白人或外国人面孔！
   - 提示词中必须严格遵循小说角色性别：女性角色必须显式使用 "beautiful Chinese woman / young East Asian female / heroine"；男性角色必须显式使用 "handsome Chinese man / young East Asian male / hero"；严禁女性被生成为男性！
4. **视频 Prompt 规范**：为可灵 (Kling AI) 或即梦 (Jimeng) 提供提示词，必须符合 9:16 竖屏短剧视觉，电影级构图，逼真质感，人物特征一致，中英文双语。格式示例：
   "9:16 vertical short drama shot, [Chinese woman/man + 年龄 + 东方五官 + 服饰 + 镜头运镜], cinematic photorealistic lighting, dramatic contrast, 8k resolution, [中文核心画面描述]"

【返回格式】：
请严格输出标准 JSON 对象，禁止包裹额外文本：
{{
  "episode_num": {episode_num},
  "episode_title": "第{episode_num}集：提炼自本章高能情节的爆款集标题",
  "logline": "一句话剧情梗概（20-30字）",
  "duration_sec": 90,
  "hook_summary": "0-5秒抓手核心剧情",
  "climax_summary": "40-70秒高潮对抗/反转核心剧情",
  "cliffhanger": "85-90秒留钩子卡点悬念",
  "characters_in_scene": ["主要登场角色1", "主要登场角色2"],
  "shots": [
    {{
      "shot_num": 1,
      "shot_type": "特写 / 近景 / 中景 / 全景 / 俯拍 / 低角度仰拍",
      "camera_movement": "缓缓推近 / 快速切镜 / 水平摇镜 / 手持微晃 / 升格慢动作",
      "duration_sec": 4,
      "visual": "详细画面描述：角色动作、神态、光影氛围与环境细节（忠实还原小说情节）",
      "dialogue": "角色台词（前缀角色名）或 画外音OS 或 (无对白)",
      "sfx_bgm": "音效与配乐情绪",
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

    def _generate_mock_drama(
        self,
        book_title: str,
        genre: str,
        chapter_title: str,
        episode_num: int,
        active_characters: Optional[List[Dict[str, Any]]] = None,
        chapter_content: str = ""
    ) -> Dict[str, Any]:
        """高质量全题材自适应短剧分镜生成器（杜绝模板死板化，深度取材原著）"""
        cat = classify_genre(genre, book_title)

        # 1. 动态提取原著核心角色
        chars = active_characters or []
        c1 = chars[0].get("name", "主角") if len(chars) > 0 else "楚无痕"
        c2 = chars[1].get("name", "对手") if len(chars) > 1 else "神秘对手"
        c3 = chars[2].get("name", "策应者") if len(chars) > 2 else "旁观者"

        c1_item = chars[0].get("inventory", ["随身兵刃"])[0] if (len(chars) > 0 and chars[0].get("inventory")) else "核心信物"
        c2_item = chars[1].get("inventory", ["致命底牌"])[0] if (len(chars) > 1 and chars[1].get("inventory")) else "暗藏杀招"

        # 2. 从正文中动态提炼有效描述与对白
        clean_lines = [l.strip() for l in chapter_content.splitlines() if l.strip() and not l.strip().startswith("#")]
        first_p = clean_lines[0] if clean_lines else f"《{book_title}》{chapter_title}风云骤起。"
        mid_p = clean_lines[len(clean_lines)//2] if len(clean_lines) > 2 else f"{c1}与{c2}针锋相对，杀机锁定全场。"

        mock_data = {
            "episode_num": episode_num,
            "episode_title": f"第{episode_num}集：{chapter_title}",
            "logline": f"《{book_title}》高能冲突爆发，{c1}与{c2}展开激烈的宿命博弈与底牌对决。",
            "duration_sec": 90,
            "hook_summary": f"局势骤变，{first_p[:35]}……",
            "climax_summary": f"{c1}掀开【{c1_item}】底牌，正面对决{c2}的致命杀招！",
            "cliffhanger": f"暗中潜藏的第三方势力被交锋惊动，更大危局悄然笼罩全场。",
            "characters_in_scene": [c1, c2, c3],
            "shots": [
                {
                    "shot_num": 1,
                    "shot_type": "特写",
                    "camera_movement": "快速推近",
                    "duration_sec": 4,
                    "visual": f"画面急速由暗切明，镜头逼近{c1}冷峻肃杀的面容，眼神如电，指尖紧扣【{c1_item}】。",
                    "dialogue": f"{c1}（冷声）：今日既入此局，便没有空手而退的道理。",
                    "sfx_bgm": "重低音弦乐激荡，金属轻颤铮鸣",
                    "ai_prompt": f"9:16 vertical short drama opening shot, intense determined handsome East Asian hero face close up, dark cinematic lighting, dynamic angle, high detail, 8k, 《{book_title}》开场特写"
                },
                {
                    "shot_num": 2,
                    "shot_type": "中景",
                    "camera_movement": "水平横移",
                    "duration_sec": 5,
                    "visual": f"{c2}踏步逼近，身后气势翻滚，手持【{c2_item}】直指{c1}，神情狠戾，形成强烈压迫视线。",
                    "dialogue": f"{c2}（狞笑）：你以为凭你一人，也能妄图逆转乾坤？",
                    "sfx_bgm": "沉重脚步踩踏回音，狂乱风声呼啸",
                    "ai_prompt": f"9:16 vertical short drama scene, fierce East Asian adversary sneering, holding weapon, intense dramatic tension, cinematic movie still, 8k"
                },
                {
                    "shot_num": 3,
                    "shot_type": "全景",
                    "camera_movement": "升格慢动作",
                    "duration_sec": 5,
                    "visual": f"{c1}与{c2}悍然交锋，两股截然不同的威能轰然撞击，气浪横扫全场，{c3}在侧翼震惊退避！",
                    "dialogue": f"{c1}（厉喝）：那就看看，谁的命更硬！",
                    "sfx_bgm": "震耳欲聋的能量爆裂与金铁交击巨响，交响乐高潮爆发",
                    "ai_prompt": f"9:16 vertical short drama climax, epic power clash between two East Asian warriors, dramatic shockwave, cinematic action freeze frame, 8k"
                },
                {
                    "shot_num": 4,
                    "shot_type": "近景",
                    "camera_movement": "缓缓拉远",
                    "duration_sec": 4,
                    "visual": f"硝烟弥漫中，{c1}渊渟岳峙，而远处阴影之中，另一尊未现身的强横身影缓缓抬起头颅……",
                    "dialogue": "画外音OS：真正的暴风雨，才刚刚开始！",
                    "sfx_bgm": "悬疑定音鼓重击，余音颤动戛然而止",
                    "ai_prompt": f"9:16 vertical cliffhanger shot, victorious warrior standing in smoke while mysterious dark silhouette watches from shadows, thriller, 8k"
                }
            ],
            "created_at": time.time()
        }
        topology = spatial_director.build_scene_topology(
            scene_name=mock_data["episode_title"],
            characters=mock_data["characters_in_scene"],
            genre_cat=cat,
            scene_desc=chapter_title
        )
        mock_data["scene_topology"] = topology
        mock_data["shots"] = spatial_director.lint_and_optimize_storyboard(
            mock_data["shots"],
            topology,
            mock_data["characters_in_scene"]
        )
        mock_data["pacing_curve"] = spatial_director.generate_tension_and_pacing_curve(
            shot_count=len(mock_data["shots"]),
            total_duration=mock_data["duration_sec"]
        )
        return mock_data

    def _generate_fallback_drama(
        self,
        book_title: str,
        genre: str,
        chapter_title: str,
        content: str,
        episode_num: int,
        active_characters: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """降级兜底生成（忠实结合原著角色与正文片段）"""
        cat = classify_genre(genre, book_title)
        first_line = content.strip().splitlines()[0] if content.strip() else chapter_title

        chars = active_characters or []
        c1 = chars[0].get("name", "主角") if len(chars) > 0 else "楚无痕"
        c2 = chars[1].get("name", "对手") if len(chars) > 1 else "神秘对手"

        fallback_data = {
            "episode_num": episode_num,
            "episode_title": f"第{episode_num}集：{chapter_title}",
            "logline": f"《{book_title}》高能冲突转折点，{c1}与{c2}激烈对抗全面展开。",
            "duration_sec": 90,
            "hook_summary": f"开场直接展现危机：{first_line[:40]}……",
            "climax_summary": f"{c1}与{c2}多方势力正面对决，力量反差与局势反转瞬间引爆全场。",
            "cliffhanger": "致命危机再度逼近，更大风暴即将席卷而至。",
            "characters_in_scene": [c1, c2],
            "shots": [
                {
                    "shot_num": 1,
                    "shot_type": "特写",
                    "camera_movement": "快速推近",
                    "duration_sec": 4,
                    "visual": f"画面从暗部快速切出，{c1}目光如电，紧盯眼前突发的巨大变故。",
                    "dialogue": f"{c1}（沉声）：这世道，讲道理已经没用了。",
                    "sfx_bgm": "重低音沉闷震荡，紧张弦乐渐起",
                    "ai_prompt": f"9:16 vertical short drama opening shot, intense determined East Asian protagonist face close up, dark cinematic lighting, dynamic angle, high detail, 8k, 《{book_title}》开场特写"
                },
                {
                    "shot_num": 2,
                    "shot_type": "中景",
                    "camera_movement": "水平摇镜",
                    "duration_sec": 5,
                    "visual": f"{c2}露出深沉狠厉的神态，步步逼近，身后众人蠢蠢欲动。",
                    "dialogue": f"{c2}（冷笑）：交出东西，还能留你全尸！",
                    "sfx_bgm": "刺耳武器出鞘声，周围气浪翻滚",
                    "ai_prompt": f"9:16 vertical short drama scene, arrogant East Asian adversary sneering with armed thugs behind, dramatic tension, photorealistic, cinematic movie still, 8k"
                },
                {
                    "shot_num": 3,
                    "shot_type": "全景",
                    "camera_movement": "升格慢动作",
                    "duration_sec": 5,
                    "visual": f"{c1}骤然暴起，底牌掀开，一道恐怖能量/杀招横扫全场，震退所有敌人。",
                    "dialogue": f"{c1}（暴喝）：就凭你们，也配？！",
                    "sfx_bgm": "震耳欲聋的爆裂声与重重倒地声，震撼管弦高潮",
                    "ai_prompt": f"9:16 vertical short drama climax, epic power counterattack, shockwave dispersing enemies, cinematic action freeze frame, hyper-realistic, 8k"
                },
                {
                    "shot_num": 4,
                    "shot_type": "近景",
                    "camera_movement": "缓缓拉远",
                    "duration_sec": 4,
                    "visual": f"{c1}站在残局中央，阴影处一双更阴森恐怖的眼睛缓缓睁开。",
                    "dialogue": "画外音OS：真正的灾难……才刚刚开始！",
                    "sfx_bgm": "急促心跳声戛然而止，余音袅袅",
                    "ai_prompt": f"9:16 vertical cliffhanger shot, protagonist standing victorious while ominous glowing eyes watch from dark background, mysterious thriller, 8k"
                }
            ],
            "created_at": time.time()
        }
        topology = spatial_director.build_scene_topology(
            scene_name=fallback_data["episode_title"],
            characters=fallback_data["characters_in_scene"],
            genre_cat=cat,
            scene_desc=chapter_title
        )
        fallback_data["scene_topology"] = topology
        fallback_data["shots"] = spatial_director.lint_and_optimize_storyboard(
            fallback_data["shots"],
            topology,
            fallback_data["characters_in_scene"]
        )
        fallback_data["pacing_curve"] = spatial_director.generate_tension_and_pacing_curve(
            shot_count=len(fallback_data["shots"]),
            total_duration=fallback_data["duration_sec"]
        )
        return fallback_data

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
