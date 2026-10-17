import time
from typing import List, Dict, Any, Iterator, Optional
from llm_client import LLMClient
from world_state import RoundLog, WorldState

class ChroniclerAgent:
    """
    【全题材史官 Agent (The Chronicler / Novelist)】
    将多智能体演化的客观历史日志、角色心理博弈、天道因果判定，
    流式提炼撰写为极具质感的多题材长篇小说正文章节。
    支持：现代都市逆袭、历史穿越、传统凡人修仙、重生商战、科幻等全流派。
    """

    def __init__(self, llm_client: LLMClient, model_name: str):
        self.llm = llm_client
        self.model = model_name

    def _build_genre_style(self, genre: str, book_title: str) -> Dict[str, str]:
        """根据小说题材动态匹配文学宗师风格设定"""
        genre_lower = (genre or "").lower()
        if "都市" in genre_lower or "逆袭" in genre_lower or "战神" in genre_lower:
            return {
                "role_desc": "顶级都市爽文与商战逆袭宗师级作家，文风凌厉霸道、节奏明快、戏剧张力拉满",
                "core_rule": (
                    "突出各方角色的身份反差、暗中势力盘根错节、豪门倾轧与快意恩仇。"
                    "既要写出商战暗算与人情冷暖的残酷真实，又要写出反杀绝地反击的酣畅淋漓！"
                ),
                "tone": "都市冷峻博弈，热血逆袭，装逼打脸收放自如，对话极具现代张力。"
            }
        elif "大明" in genre_lower or "历史" in genre_lower or "穿越" in genre_lower:
            return {
                "role_desc": "顶级历史权谋与明史正剧宗师级作家，精研《大明王朝1566》与高阳式历史大作",
                "core_rule": (
                    "注重典章制度、官制仪轨与庙堂杀机。每一句话背后皆是党争倾轧，举手投足皆关乎九族生死。"
                    "写出皇权冷酷、文官奸滑、锦衣卫森严与主角从底层步步为营的惊险破局。"
                ),
                "tone": "沉稳厚重，史笔如铁，刀光隐于奏折朝堂，言辞古雅考究。"
            }
        elif "重生" in genre_lower or "商战" in genre_lower:
            return {
                "role_desc": "顶级商业谍战与时代大亨纪实宗师级作家，文风老辣敏锐",
                "core_rule": (
                    "精准刻画资本暗涌、时代风口抢占、股权对赌与商场无硝烟的生死围猎。"
                    "写出每一个资本巨鳄与政商枭雄的心机博弈，绝无低幼反派。"
                ),
                "tone": "格局宏大，时代感强烈，商海搏杀步步惊心。"
            }
        elif "科幻" in genre_lower or "星际" in genre_lower:
            return {
                "role_desc": "顶级硬核科幻与星海争霸宗师级作家，文风宏大冷酷，充满机械与星空美学",
                "core_rule": (
                    "刻画宇宙黑暗森林法则、星系地缘政治、古老文明造物遗迹与星舰实弹交锋。"
                ),
                "tone": "宏大深邃，理性冷彻，太空战争压迫感十足。"
            }
        else:
            return {
                "role_desc": "顶级凡人修仙群像史诗宗师级作家，精研忘语、耳根式修仙现实主义",
                "core_rule": (
                    "人人皆主角，绝无降智送命工具人。深入描摹每一个在场修士的道心执念与生死挣扎。"
                    "白描修仙界的残酷现实，法宝交锋、灵符爆裂、偷袭反杀干净利落，充满刀尖舔血的真实压迫感。"
                ),
                "tone": "苍凉冷峻，仙凡殊途，杀机内蕴，字字见血。"
            }

    def write_chapter_stream(
        self,
        world: WorldState,
        history: List[RoundLog],
        book_title: str = "",
        genre: str = "",
        chapter_num: int = 1,
        total_chapters: int = 1,
        is_final: bool = False,
        previous_summary: str = "",
        chapter_outline: Optional[Dict[str, Any]] = None,
        force_mock: bool = False
    ) -> Iterator[str]:
        """
        流式生成整篇小说章节，实时 yield 生成内容片段 (Token / Delta Chunk)
        """
        if force_mock:
            mock_text = self._generate_mock_chapter(book_title, genre, world, history, chapter_num, is_final)
            step_len = 6
            for i in range(0, len(mock_text), step_len):
                yield mock_text[i:i+step_len]
                time.sleep(0.015)
            return

        genre_info = self._build_genre_style(genre, book_title)

        # 构建演化全卷
        evolution_records = []
        for r in history[-3:] if len(history) > 3 else history:
            round_text = f"=== 【第 {r.round_number} 轮因果冲突】 ===\n"
            round_text += f"【现场态势与变局】：{r.environment_state}\n"
            if r.tiandao_intervention:
                round_text += f"【天地/外力变数】：{r.tiandao_intervention}\n"
            round_text += "【登场人物言行】：\n"
            for act in r.actions:
                round_text += (
                    f"  * 【{act.char_name}】：\n"
                    f"    - 心思盘算: {act.inner_thought}\n"
                    f"    - 表面所言: \"{act.speech}\"\n"
                    f"    - 举止动作: {act.action}\n"
                )
            round_text += f"【因果裁决判定】：{r.arbitration_result}\n"
            evolution_records.append(round_text)

        full_simulation_log = "\n\n".join(evolution_records)

        # 角色阵容名单
        char_roster = ", ".join([f"{c['name']}({c.get('title','')})" for c in world.characters.values()])

        outline_directive = ""
        if chapter_outline:
            outline_directive = f"""
【★★★ 本章剧情核心细纲蓝图（务必严格推进实现）★★★】：
- 拟定标题：{chapter_outline.get('title', f'第{chapter_num}章')}
- 本章核心行动目标：{chapter_outline.get('goal', '推进主线矛盾')}
- 核心冲突与危机：{chapter_outline.get('conflict', '各方势力交锋碰撞')}
- 最高潮情节爆点：{chapter_outline.get('climax', '关键底牌掀开与局势反转')}
- 章末追更悬念钩子：{chapter_outline.get('ending_hook', '留下强烈悬念')}
"""

        finale_directive = ""
        if is_final:
            finale_directive = f"""
【★★★ 终极裁定 · 全书大结局指令 ★★★】：
本章是全书《{book_title}》的【大结局 · 终章】！
请将全书所有因果线索、各方恩怨、宏大宿命全面推向最壮烈的高潮并完美收束！
写出最终决战的胜负走向，并在末尾给出一个荡气回肠、令人回味悠长的史诗终局结语！
"""
        elif total_chapters > 1:
            finale_directive = f"""
【连载定位】：
本书当前正处于连载推演阶段（第 {chapter_num} / {total_chapters} 章）。
请承接前文，既要完成本章的激烈高潮冲突，又要在本章末尾自然留下暗线与引人入胜的伏笔！
"""

        prev_hint = f"【前序剧情脉络摘要】：\n{previous_summary}\n\n" if previous_summary else ""

        prompt = f"""
你是一位{genre_info['role_desc']}。
当前创作的书名为：《{book_title or world.title}》，题材流派为：【{genre or '综合'}】。

【文学与叙事法则】：
1. {genre_info['core_rule']}
2. 文风基调：{genre_info['tone']}
3. 登场核心人物：{char_roster}。绝不能写出单一脸谱化工具人，写出各自立场与命运冲突。

{outline_directive}

【本场演化发生的情景舞台】：
{world.scene_description}

{prev_hint}
【以下是多角色在因果律下演化碰撞的最新卷宗】：
{full_simulation_log}

{finale_directive}

【著书输出要求】：
1. 第一行必须且仅为章节标题（格式必须为：第{chapter_num}章 章节名，如：第{chapter_num}章 寒潭夺宝，群雄争渡）。
2. 从第二行开始，必须是纯正流畅的长篇小说正文（段落清晰，自然空行），杜绝剧本台词式标注、杜绝'旁白'或'日志'格式。
3. 篇幅充沛详实，情节跌宕起伏，环境描写与人物心理刻画入骨。
"""

        messages = [
            {"role": "system", "content": f"你是一位享誉业界的顶级小说宗师。你擅长写作沉浸感拉满的{genre}长篇小说。"},
            {"role": "user", "content": prompt}
        ]

        model_to_use = self.model or "fast-model"
        chunk_received = False

        # 尝试使用主模型流式生成
        try:
            for chunk in self.llm.chat_stream(model_to_use, messages, temperature=0.75, max_tokens=3600):
                chunk_received = True
                yield chunk
            if chunk_received:
                return
        except Exception as e:
            print(f"[史官著书 流式告警] 模型 {model_to_use} 流式中断或失败: {e}，尝试使用 fast-model 备选流式生成...")

        # 备选 fast-model
        if not chunk_received:
            try:
                for chunk in self.llm.chat_stream("fast-model", messages, temperature=0.75, max_tokens=3600):
                    chunk_received = True
                    yield chunk
                if chunk_received:
                    return
            except Exception as e2:
                print(f"[史官著书 流式兜底] 备选 fast-model 亦失败: {e2}，启动沙盒拟真流式生成")

        # 兜底拟真流式生成（保证哪怕断网或无Key也有流畅流式打字效果体验）
        mock_text = self._generate_mock_chapter(book_title, genre, world, history, chapter_num, is_final)
        # 拟真打字机流式输出 (按 4~8 字符片段吐出)
        step_len = 6
        for i in range(0, len(mock_text), step_len):
            yield mock_text[i:i+step_len]
            time.sleep(0.015)

    def write_chapter(
        self,
        world: WorldState,
        history: List[RoundLog],
        book_title: str = "",
        genre: str = "",
        chapter_num: int = 1,
        total_chapters: int = 1,
        is_final: bool = False,
        previous_summary: str = ""
    ) -> str:
        """非流式调用入口，聚合流式 chunk 返回完整文本"""
        chunks = []
        for chunk in self.write_chapter_stream(
            world=world,
            history=history,
            book_title=book_title,
            genre=genre,
            chapter_num=chapter_num,
            total_chapters=total_chapters,
            is_final=is_final,
            previous_summary=previous_summary
        ):
            chunks.append(chunk)
        return "".join(chunks)

    def _generate_mock_chapter(
        self,
        book_title: str,
        genre: str,
        world: WorldState,
        history: List[RoundLog],
        chapter_num: int,
        is_final: bool
    ) -> str:
        """高质量离线/沙盒全题材章节生成器"""
        title_suffix = "终章 · 乾坤落定万古长青" if is_final else f"第{chapter_num}章 风起云涌，大局初定"
        chars = list(world.characters.values())
        c1 = chars[0]["name"] if len(chars) > 0 else "楚无痕"
        c2 = chars[1]["name"] if len(chars) > 1 else "沈炼"
        c3 = chars[2]["name"] if len(chars) > 2 else "赵青鸾"

        if "都市" in genre or "逆袭" in genre:
            return f"""{title_suffix}

夜色沉郁，暴雨倾盆。江城顶层的旋转玻璃幕墙外，霓虹在水汽中模糊成一片斑驳的光晕。

{c1}整了整略显发皱的黑色风衣领口，指尖摩挲着那枚沉甸甸的漆黑玄戒。三年了，自他在北境卸下甲胄，在这寸土寸金的商海迷局中隐姓埋名，所有人皆以为他是一无所有的落魄赘婿。可谁又曾料到，当年横扫半座南洋的资本巨鳄，正是此刻立在阴影中的他。

门扉骤然被撞开，伴随着皮鞋踩踏水渍的急促声响，{c2}面带冷笑大步闯入，手中赫然甩下一份盖有重印的清算合同：“姓{c1[0]}的，你以为抱住了林家的粗腿便能翻身？今夜十二点前，江城再无你立锥之地！”

空气中仿佛有无形的火花炸裂。

{c1}连眼皮都未曾抬起一下，嘴角却浮起一抹意味深长的弧度：“{c2}，你动用李氏三房的所有暗盘资金狙击我的盘口，难道就未曾想过，为你批复那笔十二亿过桥贷款的幕后主脑……究竟是谁？”

话音未落，办公桌上的保密红色专线骤然爆发出凄厉的盲音。{c2}脸色由讥讽瞬间化为惨白，抓起听筒的双手止不住地剧烈战栗起来。

“这……这绝不可能！怎么会是你？！”

{c3}不知何时已悄然出现在回廊尽头，身着一袭素黑旗袍，神情冷肃地将一份泛着金色烫印的委任书拍在桌案正中央：“少主，暗卫三十六舵已全面接管三江资本，各大家族族长，正冒雨在楼下候命！”

轰然之间，雷鸣划破夜空。命运的齿轮在这一刻疯狂咬合，所有的隐忍与蛰伏，终在此夜化作焚尽一切的滔天狂澜！"""
        elif "大明" in genre or "历史" in genre:
            return f"""{title_suffix}

奉天殿外的玉阶之上，九卿重臣面面相觑，寒风猎猎，将猩红的大理寺仪仗锦旗吹得猎猎作响。

{c1}手按绣春刀柄，面色沉静如渊，一双眸子冷冷扫过跪伏在阶前的满朝朱紫。锦衣卫的皂靴踏在青石板上，发出沉重而冷冽的回响。

“沈大人，通敌谋逆之罪非同小可，可有真凭实据？”户部侍郎胡显宗咬着牙关，袖中手指不住颤抖，犹在作垂死挣扎。

{c1}从容上前一步，从怀中取出一枚沾着紫黑血迹的铜符，掷于丹墀之上，发出清脆的铮鸣：“胡大人，宣府那三万石军粮究竟运去了何处，你袖中的密信，是否要本座当着皇上的面亲自为你诵读？”

刹那间，满殿死寂，落针可闻。

{c2}与{c3}对视一眼，皆从对方眼中看到了彻骨的寒意。天子震怒，伏尸百万，这场席卷朝野的大清洗，才不过刚刚掀开冰山一角……"""
        else:
            return f"""{title_suffix}

荒古死地，万丈雷云压顶，幽蓝色的罡风将方圆千里的乱石古木尽数绞为齑粉。

{c1}藏匿于青铜巨岩的阴影之中，周身护体灵光收敛得近乎于无，甚至连心跳都已降至数息一搏。他的目光死死锁定着悬浮在寒潭中央的那枚混沌道种，袖中扣着的三柄无影毒针已被煞气淬得隐隐发紫。

修仙界自古以来便无情义二字可言，唯有活着走出这片绝地，方配谈及长生大道！

忽然，半空中传来一声撕心裂肺的冷笑，{c2}脚踏赤火玄轮破空而至，双手法诀翻飞，数十道焚天烈焰直扑寒潭中心：“既然尔等藏头露尾，此宝便归老夫所有了！”

“休想！”伴随着一声娇叱，{c3}身化青鸾剑光后发先至，九柄寒霜飞剑如游龙出海，瞬间封死了{c2}的退路！

三方杀机在电光石火间骤然交汇。{c1}眼底掠过一丝冰冷的光芒，身形忽如鬼魅般自暗处暴起——他等的就是这两败俱伤的一瞬！

轰！法宝碰撞的巨响震彻寰宇，因果纠缠，生死只在一线之间……"""
