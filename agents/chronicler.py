import time
from typing import List, Dict, Any, Iterator, Optional
from llm_client import LLMClient
from world_state import RoundLog, WorldState
from config import classify_genre

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
        """根据小说题材动态匹配文学宗师风格设定，支持全流派小说创作"""
        cat = classify_genre(genre, book_title)
        if cat == "urban":
            return {
                "role_desc": "顶级现代都市爽文与商战逆袭宗师级作家，文风凌厉霸道、节奏明快、戏剧张力拉满",
                "core_rule": (
                    "突出各方角色的身份反差、暗中势力盘根错节、豪门倾轧与快意恩仇。"
                    "既要写出商战暗算与人情冷暖的残酷真实，又要写出绝地反杀的酣畅淋漓！"
                ),
                "tone": "都市冷峻博弈，热血逆袭，装逼打脸收放自如，对话极具现代张力与情绪价值。"
            }
        elif cat == "history":
            return {
                "role_desc": "顶级历史权谋与明清正剧宗师级作家，精研《大明王朝1566》与高阳式历史大作",
                "core_rule": (
                    "注重典章制度、官制仪轨与庙堂杀机。每一句话背后皆是党争倾轧，举手投足皆关乎九族生死。"
                    "写出皇权冷酷、文官奸滑、锦衣卫森严与主角从微末步步为营的惊险破局。"
                ),
                "tone": "沉稳厚重，史笔如铁，刀光隐于奏折朝堂，言辞古雅考究，格局恢弘。"
            }
        elif cat == "scifi":
            return {
                "role_desc": "顶级硬核科幻与星海争霸宗师级作家，文风宏大深邃，充满冷酷机械与星空美学",
                "core_rule": (
                    "刻画宇宙黑暗森林法则、星系地缘政治、高维文明造物遗迹、义体改造与轨道舰队实弹交锋。"
                    "写出科技爆炸带来的伦理震荡、底层废土的挣扎以及宏大星海的无情冷彻。"
                ),
                "tone": "宏大深邃，理性冷彻，太空战争压迫感十足，科技感与史诗感并重。"
            }
        elif cat == "suspense":
            return {
                "role_desc": "顶级悬疑惊悚与规则怪谈宗师级作家，文风细思极恐、密室压迫感拉满",
                "core_rule": (
                    "注重氛围铺垫、感官放大、不可名状之物的阴影与规则推理。"
                    "写出心跳加速的窒息感、san值狂降的心理畸变与绝境中凭借理智撕开生路的孤注一掷。"
                ),
                "tone": "阴冷窒息，细思极恐，惊心动魄，推理严密，反转扣人心弦。"
            }
        elif cat == "fantasy":
            return {
                "role_desc": "顶级西方史诗奇幻与剑与魔法宗师级作家，精研冰与火之歌与龙与地下城美学",
                "core_rule": (
                    "描绘古老神祇信仰、家族封臣博弈、元素法术吟唱、血腥领地攻防与魔兽撕咬。"
                    "写出中世纪的铁血残酷与魔法秘境的璀璨神秘，各方势力动机深沉。"
                ),
                "tone": "庄重雄浑，史诗感拉满，魔幻色彩浓郁，骑士精神与冷酷权谋交织。"
            }
        elif cat == "gaming":
            return {
                "role_desc": "顶级无限流与游戏数据流宗师级作家，文风快节奏、机制严密、爽感密集",
                "core_rule": (
                    "严格遵守主神/系统机制与数值博弈，技能组合与极限微操层出不穷。"
                    "写出轮回空间生死副本的残酷淘汰，以及主角凭借机制理解与心理战极限通关的极致爽感。"
                ),
                "tone": "快节奏，高燃刺激，机制智斗，副本悬念层出不穷。"
            }
        elif cat == "wuxia":
            return {
                "role_desc": "顶级传统武侠与新派武侠宗师级作家，精研金古温梁武侠神韵",
                "core_rule": (
                    "刀光剑影、血雨腥风，白描江湖门派纷争、恩怨情仇与侠骨柔肠。"
                    "招式对决快准狠，内力气机流转于草木竹石之间，尽显快意恩仇。"
                ),
                "tone": "萧瑟苍茫，风骨卓然，招式凌厉，尽显快意恩仇与江湖侠义。"
            }
        elif cat == "doomsday":
            return {
                "role_desc": "顶级末日生存与天灾囤货爽文宗师级作家，文风节奏极快、压迫感强、反差打脸极致爽快",
                "core_rule": (
                    "突出极端恶劣环境（极寒/高温/丧尸/酸雨/毒雾）与主角安全屋/异能空间的奢华享受形成天壤之别。"
                    "绝不圣母！对贪婪恶霸邻居、绿茶白莲花施以雷霆果决手段，把物资诱惑、人性撕裂、战力碾压写得淋漓尽致。"
                ),
                "tone": "末日残酷，冷酷铁血，杀伐果断，生活享受与外界地狱极度反差，爽感爆棚。"
            }
        else:
            return {
                "role_desc": "顶级凡人修仙群像史诗宗师级作家，精研忘语、耳根式修仙现实主义",
                "core_rule": (
                    "人人皆主角，绝无降智送命工具人。深入描摹每一个在场角色的生存执念与生死挣扎。"
                    "法宝交锋、灵符爆裂、偷袭反杀干净利落，充满刀尖舔血的真实压迫感。"
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

        cat = classify_genre(genre, book_title)

        if cat == "urban":
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

        elif cat == "history":
            return f"""{title_suffix}

奉天殿外的玉阶之上，九卿重臣面面相觑，寒风猎猎，将猩红的大理寺仪仗锦旗吹得猎猎作响。

{c1}手按绣春刀柄，面色沉静如渊，一双眸子冷冷扫过跪伏在阶前的满朝朱紫。锦衣卫的皂靴踏在青石板上，发出沉重而冷冽的回响。

“沈大人，通敌谋逆之罪非同小可，可有真凭实据？”户部侍郎胡显宗咬着牙关，袖中手指不住颤抖，犹在作垂死挣扎。

{c1}从容上前一步，从怀中取出一枚沾着紫黑血迹的铜符，掷于丹墀之上，发出清脆的铮鸣：“胡大人，宣府那三万石军粮究竟运去了何处，你袖中的密信，是否要本座当着皇上的面亲自为你诵读？”

刹那间，满殿死寂，落针可闻。

{c2}与{c3}对视一眼，皆从对方眼中看到了彻骨的寒意。天子震怒，伏尸百万，这场席卷朝野的大清洗，才不过刚刚掀开冰山一角……"""

        elif cat == "scifi":
            return f"""{title_suffix}

猩红的警报光束如脉冲般撕裂了第七重轨道的深冷真空。重力偏转力场发出刺耳的高频过载嘶鸣，全息视界被铺天盖地的乱码警示染成血红。

“警告：三级曲率坍缩点已撕裂柯伊伯带防线，敌对机械蜂群跃迁倒计时：三、二……”

主控台前，{c1}面无表情地反手将一枚高密度量子神经插栓直接刺入颈后腺体接口。狂暴的数据洪流如烈火般灼烧着视网膜，神经元与重型星舰的超导曲率引擎强行接驳！

“疯子！你的生物脑容载率已经突破94%！”损管舱室内，{c2}一把扯下被高能电弧烧灼变形的防护面罩，声嘶力竭地在通讯频段中怒吼，“这是泰坦级歼星炮的超载过热反冲！强行点火，整座主舰桥都会在引力阱中被压成二向箔！”

而在舰艏破碎的钛合金装甲板边缘，机械女武神{c3}已单膝跪地，掌心那柄散发着幽蓝反物质幽光的裂解重炮缓缓抬起，直指漆黑深空中那尊庞大如月球般的古老硅基母巢。

“航向已锁定，超频解限。”{c1}缓缓吐出一口混杂着金属机油味的血雾，嘴角掠过一抹冰冷的弧度，“传令全舰——人类退役舰队第七联队，今日绝不在虚空中悄无声息地熄灭。主炮……全功率过载发射！”"""

        elif cat == "suspense":
            return f"""{title_suffix}

走廊尽头的老旧挂钟发出沉闷而粘稠的“咔哒”声，指针停在诡异的十一点六十一分。

空气中弥漫着一股刺鼻的福尔马林与潮湿泥土混合的腐败气味。

{c1}紧紧贴在冰冷渗水的墙壁上，呼吸压得极低，甚至不敢眨一下干涩的双眼。掌心那张泛黄褶皱的《公寓租客生存守则（第三修正版）》上，第七条红字正以肉眼可见的速度渗出新鲜的血迹：
【切记：若在午夜听到三声敲门声，请立刻将镜子反扣，绝不要回答门外的任何询问——哪怕声音来自你最亲近之人。】

“咚……咚……咚。”

沉重的敲门声，在死寂得能听见血管搏动的黑暗中突兀响起。

门外传来{c2}熟悉而温柔的声音，语调却僵硬得如同一具没有声带的提线木偶：“开门呀……我给你买了你最爱吃的热汤……快把门打开……”

{c1}后背的汗毛根根倒竖，因为他分明看见，门缝底下的阴影里，根本没有任何人的双脚，只有一滩缓缓蔓延开来的黑色粘稠肉须！

就在此时，头顶天花板发出轻微的异响。{c3}不知何时已如倒挂的蝙蝠般潜伏在房梁暗影中，苍白干瘦的手指轻轻抵在唇边，示意他看向猫眼——在那里，正有一只没有瞳仁的猩红眼球，死死贴在玻璃内侧，贪婪地窥视着屋内！"""

        elif cat == "fantasy":
            return f"""{title_suffix}

暴风雪无情地肆虐着黑石堡巍峨的角楼，寒鸦在冻结的箭垛上发出凄厉的啼鸣。

壁炉中干燥的橡木柴噼啪作响，火光映照在{c1}那一身布满刀痕与干涸龙血的银灰秘银铠甲上。他将宽刃十字大剑重重插入古老的石砌地图台，剑身铭刻的破晓符文依然散发着微弱的金色暖光。

“北境的凛冬领主们已经在谷口集结了三千重甲骑士，”{c2}裹紧了厚重的白熊皮斗篷，阴郁的目光扫过地图上被冰霜覆盖的绝望平原，“更别提深渊裂缝里爬出来的那些黑血食尸鬼。单凭我们黑石堡这几百名农兵和雇佣兵，根本守不到春分时节！”

“我们不需要撑到春分。”

伴随着一道低沉空灵的咒语呢喃，高塔首席法师{c3}推开了厚重的橡木门。她纤细苍白的手指间，悬浮着一颗散发着纯净以太风暴的远古魔核，耀眼的紫色雷弧在空气中噼啪作响。

“巨龙的血裔从未真正灭绝。”{c1}缓缓拔出巨剑，金色的斗气自手臂向剑锋轰然蔓延，“敲响集结钟，告诉城墙上的每一个守卫——以破晓黎明的名义，向所有入侵者发起决死冲锋！”"""

        elif cat == "gaming":
            return f"""{title_suffix}

【叮！全服系统通告：终焉副本“虚空竞技场”S级难度已激活，当前存活玩家：3/100！】
【剩余安全区半径已收缩至50米，环境毒雾侵蚀速率提升300%！】

淡蓝色的全息数据瀑布在{c1}眼前疯狂刷新。他的血量条仅仅只剩下危险的7%，但嘴角却浮现出一抹近乎疯癫的冷静笑意。

“终于把你们逼到死角了。”

战圈中心，身穿暗金骨龙重甲的顶级公会会长{c2}拄着燃烧地狱火的巨剑剧烈喘息，身上挂着七个致盲与流血的DEBUFF：“不可能……你的敏捷加点明明是刺客模版，怎么可能扛得住我的三阶‘灭世重斩’？！”

“因为从进入副本的第一秒起，我的被动技能‘绝对破绽计算’就已经叠满了九百层。”{c1}指尖微动，双子匕首在掌心化作两道令人眼花缭乱的光弧。

阴影之中，虚空游侠{c3}的重型狙击弩机已经发出充能完毕的嗡鸣，终极奥义的锁定红线穿透毒雾，死死钉在核心弱点之上！

“胜负已分。”随着键盘微操般的一记极限折线位移，{c1}的身影在0.01秒内完成三段判定突刺，整片虚空在技能交汇的璀璨光爆中轰然破碎！"""

        elif cat == "wuxia":
            return f"""{title_suffix}

关外大雪，封冻了黑石驿站外三千里的苍茫古道。

破旧的黄泥酒垆里，炭火盆泛着幽微的暗红，门外狂风裹挟着冰粒子，将残破的酒旗扯得猎猎作响。

{c1}头戴破斗笠，一袭洗得发白的粗布麻衣上落满了残雪。他独坐于角落长凳，一言不发，唯有一双布满冻疮与老茧的手掌，始终按在桌角那柄缠着渗血麻布的生锈铁刀刀柄之上。十年塞外饮冰，他在等一个人，也在等一场迟到了十年的生死宿怨。

“吱呀——”

两扇单薄的木门轰然被狂暴的真气震碎！四溢的风雪狂涌而入，{c2}手持一柄泛着森森寒光的出鞘长剑，踏雪而入，身后更有数十名头戴青铜面具的黑衣刀客将酒肆四方围得水泄不通。

“姓{c1[0]}的，当年名门大比你废了我兄长双足，今夜塞外风雪正紧，正好送你归西！”{c2}厉声喝道，剑尖微颤，空气中瞬间爆发出刺耳的风雷爆鸣。

{c1}连眼皮都未曾抬起半分，只是缓缓提起酒壶，往嘴里灌了一大口辛辣刺喉的烧刀子：“当年之事，是非曲直江湖自有公论。你的剑太慢，心也太急。”

“找死！”

剑光乍现，如匹练经天，直取咽喉！

就在这电光石火的一刹那，酒肆梁上忽然传来一声清脆的折扇合拢之音。{c3}不知何时已如孤鸿般掠下，一柄金丝软鞭在虚空中划出一道凌厉弧线，生生荡开了那必杀的一剑：“上官家做事，何时轮得到你们这些名门伪君子在关外越俎代庖？他的命，是我上官家的！”

风雪呼啸，杀气四溢。三股深沉的内力气机在逼仄的酒垆中剧烈碰撞，生锈的铁刀微微震颤，发出饥渴的清吟……刀客拔刀，不为名利，只为心头这一抹未凉的热血！"""

        else:
            return f"""{title_suffix}

荒古死地，万丈雷云压顶，幽蓝色的罡风将方圆千里的乱石古木尽数绞为齑粉。

{c1}藏匿于青铜巨岩的阴影之中，周身护体灵光收敛得近乎于无，甚至连心跳都已降至数息一搏。他的目光死死锁定着悬浮在寒潭中央的那枚混沌道种，袖中扣着的三柄无影毒针已被煞气淬得隐隐发紫。

修仙界自古以来便无情义二字可言，唯有活着走出这片绝地，方配谈及长生大道！

忽然，半空中传来一声撕心裂肺的冷笑，{c2}脚踏赤火玄轮破空而至，双手法诀翻飞，数十道焚天烈焰直扑寒潭中心：“既然尔等藏头露尾，此宝便归老夫所有了！”

“休想！”伴随着一声娇叱，{c3}身化青鸾剑光后发先至，九柄寒霜飞剑如游龙出海，瞬间封死了{c2}的退路！

三方杀机在电光石火间骤然交汇。{c1}眼底掠过一丝冰冷的光芒，身形忽如鬼魅般自暗处暴起——他等的就是这两败俱伤的一瞬！

轰！法宝碰撞的巨响震彻寰宇，因果纠缠，生死只在一线之间……"""
