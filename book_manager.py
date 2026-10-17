import os
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

from world_state import WorldState, RoundLog, CharacterAction
from config import load_dotenv, classify_genre

BOOKS_DIR = Path(__file__).parent / "output" / "books"
BOOKS_DIR.mkdir(parents=True, exist_ok=True)
NOVEL_OUTPUT_DIR = Path(__file__).parent / "output"

class Book:
    """单一世界观的小说实体，包含天地格局、登场修士/人物、演化历史、正文章节、短剧分镜"""
    def __init__(
        self,
        book_id: str,
        title: str,
        genre: str,
        synopsis: str,
        theme_prompt: str = "",
        world: Optional[WorldState] = None,
        chapters: Optional[List[Dict[str, Any]]] = None,
        dramas: Optional[List[Dict[str, Any]]] = None,
        outline: Optional[Dict[str, Any]] = None,
        foreshadowings: Optional[List[Dict[str, Any]]] = None,
        current_round: int = 0
    ):
        self.id = book_id
        self.title = title
        self.genre = genre
        self.synopsis = synopsis
        self.theme_prompt = theme_prompt
        self.world = world or WorldState()
        self.current_round = current_round
        self.chapters = chapters or []
        self.dramas = dramas or []
        self.outline = outline or {
            "world_view": "",
            "power_system": "",
            "main_plot": "",
            "volumes": [],
            "chapter_outlines": []
        }
        self.foreshadowings = foreshadowings or []
        self.created_at = time.time()
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """将书籍序列化为字典以便存入 JSON"""
        history_list = []
        for r in self.world.history:
            history_list.append({
                "round_number": r.round_number,
                "environment_state": r.environment_state,
                "tiandao_intervention": r.tiandao_intervention,
                "arbitration_result": r.arbitration_result,
                "actions": [
                    {
                        "char_id": a.char_id,
                        "char_name": a.char_name,
                        "inner_thought": a.inner_thought,
                        "speech": a.speech,
                        "action": a.action
                    }
                    for a in r.actions
                ]
            })

        return {
            "id": self.id,
            "title": self.title,
            "genre": self.genre,
            "synopsis": self.synopsis,
            "theme_prompt": self.theme_prompt,
            "current_round": self.current_round,
            "max_rounds": self.world.max_rounds,
            "scene_title": self.world.title,
            "scene_description": self.world.scene_description,
            "characters": self.world.characters,
            "history": history_list,
            "chapters": self.chapters,
            "dramas": self.dramas,
            "outline": self.outline,
            "foreshadowings": self.foreshadowings,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Book":
        world = WorldState(max_rounds=data.get("max_rounds", 5))
        world.title = data.get("scene_title", "【大千混沌】")
        world.scene_description = data.get("scene_description", "")
        world.characters = data.get("characters", {})

        # 还原历史记录
        world.history = []
        for h in data.get("history", []):
            actions = [
                CharacterAction(
                    char_id=a.get("char_id", ""),
                    char_name=a.get("char_name", ""),
                    inner_thought=a.get("inner_thought", ""),
                    speech=a.get("speech", ""),
                    action=a.get("action", "")
                )
                for a in h.get("actions", [])
            ]
            world.history.append(
                RoundLog(
                    round_number=h.get("round_number", 1),
                    environment_state=h.get("environment_state", ""),
                    tiandao_intervention=h.get("tiandao_intervention"),
                    actions=actions,
                    arbitration_result=h.get("arbitration_result", "")
                )
            )

        book = cls(
            book_id=data.get("id", f"book_{int(time.time())}"),
            title=data.get("title", "未命名小说"),
            genre=data.get("genre", "通用修仙"),
            synopsis=data.get("synopsis", ""),
            theme_prompt=data.get("theme_prompt", ""),
            world=world,
            chapters=data.get("chapters", []),
            dramas=data.get("dramas", []),
            outline=data.get("outline", {}),
            foreshadowings=data.get("foreshadowings", []),
            current_round=data.get("current_round", 0)
        )
        book.created_at = data.get("created_at", time.time())
        book.updated_at = data.get("updated_at", time.time())
        return book

    def save(self):
        """保存本书到本地 JSON 文件"""
        if not self.id:
            return
        self.updated_at = time.time()
        file_path = BOOKS_DIR / f"{self.id}.json"
        try:
            file_path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[书籍保存失败] {self.id}: {e}")


class BookManager:
    """全站多书库管理器"""
    def __init__(self):
        self.books: Dict[str, Book] = {}
        self.active_book_id: str = ""
        self.load_all_books()

    def load_all_books(self):
        """从 BOOKS_DIR 加载所有书籍，默认不预置任何预设书籍，完全保持纯净"""
        self.books = {}
        book_files = list(BOOKS_DIR.glob("*.json"))
        if book_files:
            for bf in book_files:
                try:
                    data = json.loads(bf.read_text(encoding="utf-8"))
                    book = Book.from_dict(data)
                    self._self_heal_book_genre(book)
                    self.books[book.id] = book
                except Exception as e:
                    print(f"[读取书籍失败] {bf}: {e}")

        if self.books:
            if self.active_book_id not in self.books:
                self.active_book_id = list(self.books.keys())[0]
        else:
            self.active_book_id = ""

    def _self_heal_book_genre(self, book: Book):
        """自动纠偏：若现代都市作品此前因关键词误判被赋予了古代大明人物或大纲，执行自我纠偏修复"""
        if not book or not book.id:
            return
        cat = classify_genre(book.genre, book.title, book.theme_prompt or book.synopsis)
        if cat == "urban":
            needs_heal = False
            if book.outline and any(k in str(book.outline) for k in ["大明", "老朱", "朱元璋", "奉天殿", "戴枷七品知县"]):
                needs_heal = True
                book.outline = {}
            if book.world and book.world.characters:
                char_names = [c.get("name") for c in book.world.characters.values()]
                if any(n in ["顾长风", "萧景琰", "李斯年"] for n in char_names):
                    needs_heal = True
                    self._populate_new_book_archetypes(book, book.genre, book.theme_prompt or book.synopsis)
            if needs_heal:
                book.save()
                print(f"[天道自愈纠偏] 成功修正现代都市书籍《{book.title}》的题材与人物设定！")

    def get_active_book(self) -> Book:
        if self.active_book_id and self.active_book_id in self.books:
            return self.books[self.active_book_id]
        if self.books:
            self.active_book_id = list(self.books.keys())[0]
            return self.books[self.active_book_id]
        return Book(
            book_id="",
            title="暂无作品",
            genre="未选择",
            synopsis="当前书库为空，请点击顶部【➕ 新建作品】开始创作！",
            chapters=[],
            current_round=0
        )

    def set_active_book(self, book_id: str) -> bool:
        if book_id in self.books:
            self.active_book_id = book_id
            return True
        return False

    def list_books_summary(self) -> List[Dict[str, Any]]:
        """列出所有书籍的概览元数据"""
        summaries = []
        for b in self.books.values():
            word_total = sum(c.get("word_count", 0) for c in b.chapters)
            summaries.append({
                "id": b.id,
                "title": b.title,
                "genre": b.genre,
                "synopsis": b.synopsis,
                "theme_prompt": b.theme_prompt,
                "chapter_count": len(b.chapters),
                "word_count": word_total,
                "char_count": len(b.world.characters),
                "current_round": b.current_round,
                "is_active": b.id == self.active_book_id,
                "dramas_count": len(b.dramas),
                "has_outline": bool(b.outline and b.outline.get("main_plot")),
                "outline_summary": (b.outline.get("main_plot", "")[:100] + "...") if b.outline.get("main_plot") else ""
            })
        return summaries

    def create_book(self, title: str, genre: str, theme_prompt: str, synopsis: str = "") -> Book:
        """管理员开辟一本全新小说（支持任意自定义题材与故事设定）"""
        book_id = f"book_{int(time.time())}"
        clean_title = title.strip()
        if not clean_title.startswith("《"):
            clean_title = f"《{clean_title}》"

        clean_genre = genre.strip() or "自定义幻想"
        clean_theme = theme_prompt.strip() or "大千世界因果推演"
        clean_synopsis = synopsis.strip() or f"围绕【{clean_genre}】展开的全新群像长篇巨著。{clean_theme}"

        new_book = Book(
            book_id=book_id,
            title=clean_title,
            genre=clean_genre,
            synopsis=clean_synopsis,
            theme_prompt=clean_theme,
            current_round=1
        )
        new_book.world.title = f"【{clean_title} · 序幕现世】"
        new_book.world.scene_description = f"在这个以【{clean_genre}】为主轴的大千世界里：{clean_synopsis}"

        # 动态智能合成该题材的4位开篇人物与初始章节
        self._populate_new_book_archetypes(new_book, clean_genre, clean_theme)

        new_book.save()
        self.books[new_book.id] = new_book
        self.active_book_id = new_book.id
        return new_book

    def _populate_new_book_archetypes(self, book: Book, genre: str, theme: str):
        """根据管理员选定的风格题材，自动捏造初始极具张力的人物与第一章正文"""
        cat = classify_genre(genre, book.title, theme)

        if cat == "urban":
            book.world.characters = {
                "c1": {
                    "name": "沈凌霄",
                    "title": "隐匿暗夜至尊",
                    "camp": "绝密财阀",
                    "cultivation_level": "巅峰掌控者",
                    "public_profile": "神情淡漠，着装低调，习惯在角落旁观一切喧嚣。",
                    "secret_profile": "【算无遗策】掌管世界前十地下金库，视名流为蝼蚁。",
                    "inventory": ["黑龙信物", "至尊黑卡"],
                    "status": "alive"
                },
                "c2": {
                    "name": "林婉儿",
                    "title": "豪门第一掌舵人",
                    "camp": "林氏财团",
                    "cultivation_level": "百亿总裁",
                    "public_profile": "优雅端庄，商战果决，却深陷家族联姻陷阱。",
                    "secret_profile": "【暗藏锋芒】不甘为人棋子，一直在暗中培养私人力量。",
                    "inventory": ["财团印鉴", "密闭协议"],
                    "status": "alive"
                },
                "c3": {
                    "name": "宋天豪",
                    "title": "嚣张阔少 / 地头蛇",
                    "camp": "宋氏联盟",
                    "cultivation_level": "顶级二世祖",
                    "public_profile": "豪车开道，嚣张跋扈，行事不择手段。",
                    "secret_profile": "【贪婪狠辣】企图以暴力手段吞并所有异己，夺取一切财富。",
                    "inventory": ["改装跑车", "雇佣令"],
                    "status": "alive"
                }
            }
        elif cat == "history":
            book.world.characters = {
                "c1": {
                    "name": "顾长风",
                    "title": "现代灵魂穿越者",
                    "camp": "微末寒士",
                    "cultivation_level": "前世博导 / 今生布衣",
                    "public_profile": "一袭青衫，目光如炬，谈吐从容不迫。",
                    "secret_profile": "【降维打击】拥有超越时代的数理、刑侦与经济谋略。",
                    "inventory": ["现代札记", "改良火药配方"],
                    "status": "alive"
                },
                "c2": {
                    "name": "萧景琰",
                    "title": "铁血储君 / 王侯",
                    "camp": "皇权中枢",
                    "cultivation_level": "统兵亲王",
                    "public_profile": "身披重铠，威严沉稳，渴望打破权贵垄断。",
                    "secret_profile": "【求贤若渴】暗中探寻救国之策，敢于打破陈规。",
                    "inventory": ["亲王佩剑", "虎符"],
                    "status": "alive"
                },
                "c3": {
                    "name": "李斯年",
                    "title": "内阁权臣门阀之主",
                    "camp": "千年门阀",
                    "cultivation_level": "当朝重臣",
                    "public_profile": "满面春风，看似忠君爱国，实则盘根错节。",
                    "secret_profile": "【权倾朝野】操纵粮道与赋税，架空皇权。",
                    "inventory": ["密折奏章", "门阀私章"],
                    "status": "alive"
                }
            }
        elif cat == "scifi":
            book.world.characters = {
                "c1": {
                    "name": "陈雷",
                    "title": "第七联队退役特战先锋",
                    "camp": "星际拾荒反抗军",
                    "cultivation_level": "军用义体三阶 (神经超频)",
                    "public_profile": "身穿磨损严重的重型动力外骨骼，右眼泛着机械义眼的幽蓝光芒，神情冷峻。",
                    "secret_profile": "【幽灵协议】体内植入了已灭绝高维硅基文明的先驱密钥，任何星舰主脑皆可被其强行覆写。",
                    "inventory": ["高频粒子战术刃", "EMP电磁手雷x2", "超导神经插栓"],
                    "status": "alive"
                },
                "c2": {
                    "name": "艾莲娜",
                    "title": "星环重工执行董事",
                    "camp": "巨型寡头财阀",
                    "cultivation_level": "泰坦执政官 (深空特权)",
                    "public_profile": "一身定制仿生晚礼服，面容清冷高雅，身后悬浮两尊微型球状智能浮游护卫机。",
                    "secret_profile": "【冰冷收割】视下层星区拾荒者为消耗原料，誓要夺取先驱密钥完成财阀的永生进化。",
                    "inventory": ["引力偏转手环", "量子加密密钥", "浮游拦截机x2"],
                    "status": "alive"
                },
                "c3": {
                    "name": "沃克",
                    "title": "地下黑市改造义医",
                    "camp": "中立混沌",
                    "cultivation_level": "义体工程师",
                    "public_profile": "浑身布满焊接疤痕，机械左臂搭载着各式微型焊枪与激光切割器，满嘴机油味。",
                    "secret_profile": "【唯利是图】在各大势力间倒卖军火违禁芯片，随时准备在双方死斗后拆解尸体上的昂贵义体。",
                    "inventory": ["等离子切割枪", "黑客破解器", "战地纳米急救注射剂"],
                    "status": "alive"
                }
            }
        elif cat == "suspense":
            book.world.characters = {
                "c1": {
                    "name": "陆巡",
                    "title": "深夜守夜调查员",
                    "camp": "异常对策局编外",
                    "cultivation_level": "序列九·执灯人",
                    "public_profile": "身披微潮的黑雨衣，右手提着一盏散发微弱煤油光晕的青铜风灯，眼球布满血丝。",
                    "secret_profile": "【直视深渊】双眼因接触禁忌而产生认知异变，能看到不可名状怪谈的杀人规则与漏洞死角。",
                    "inventory": ["破旧的辟邪煤油灯", "染血的黄铜怀表", "镇静药剂x3"],
                    "status": "alive"
                },
                "c2": {
                    "name": "苏青青",
                    "title": "红衣公寓滞留者",
                    "camp": "不可知诡异/怨念",
                    "cultivation_level": "怨念具现体 (伪装生者)",
                    "public_profile": "容貌清秀苍白的年轻女子，身着红色毛衣，神色柔弱无助，脚步却悄无声息。",
                    "secret_profile": "【替死契约】早已死于三年前的火灾，正试图引诱外来调查员违背规则成为自己的替死鬼。",
                    "inventory": ["烧焦的布娃娃", "半张规则遗书"],
                    "status": "alive"
                },
                "c3": {
                    "name": "严老九",
                    "title": "古董当铺盲眼掌柜",
                    "camp": "中立古董商",
                    "cultivation_level": "通灵人",
                    "public_profile": "戴着一副圆框黑墨镜，手持盲杖，坐在布满蛛网的柜台后，声音沙哑诡异。",
                    "secret_profile": "【收容商人】暗中收集带有诅咒的收容遗物，以活人阳气或诡异核心为筹码做无序交易。",
                    "inventory": ["引魂铜铃", "黑狗血蜡烛", "镇煞桃木钉"],
                    "status": "alive"
                }
            }
        elif cat == "fantasy":
            book.world.characters = {
                "c1": {
                    "name": "凯恩",
                    "title": "落魄破晓骑士",
                    "camp": "圣堂放逐者",
                    "cultivation_level": "黄金阶大剑士 (斗气显化)",
                    "public_profile": "一头金发略显凌乱，身穿刻满伤痕的秘银胸甲，背负双手阔剑，眼神坚毅如铁。",
                    "secret_profile": "【屠龙宿命】体内流淌着古老黄金巨龙之血，在生死绝境中可觉醒龙息斗气，战力暴涨。",
                    "inventory": ["破晓双手大剑", "圣水药剂x2", "先祖龙鳞护符"],
                    "status": "alive"
                },
                "c2": {
                    "name": "薇薇安",
                    "title": "高塔禁咒秘术学徒",
                    "camp": "奥术评议会",
                    "cultivation_level": "三阶奥术法师",
                    "public_profile": "身披深紫星月法袍，手握一颗悬浮着微型魔力旋涡的水晶法杖，神情清冷傲慢。",
                    "secret_profile": "【禁忌求知】暗中研读深渊禁典，为了探寻以太本源不惜以领地生灵做魔导实验。",
                    "inventory": ["星月橡木法杖", "瞬发火球卷轴x2", "闪烁传送石"],
                    "status": "alive"
                },
                "c3": {
                    "name": "血斧格罗姆",
                    "title": "黑石兽人劫掠领主",
                    "camp": "荒原氏族联盟",
                    "cultivation_level": "狂暴战将",
                    "public_profile": "身高近两米五，肌肉如花岗岩虬结，手持一柄两米长的嗜血重战斧，獠牙毕露。",
                    "secret_profile": "【嗜血狂怒】在鲜血刺激下免疫三阶以下一切精神控制与魔法伤害，狂暴无前。",
                    "inventory": ["嗜血黑铁战斧", "狂怒图腾", "硬皮重盾"],
                    "status": "alive"
                }
            }
        elif cat == "gaming":
            book.world.characters = {
                "c1": {
                    "name": "苏夜",
                    "title": "封弊者 / 极限独狼刺客",
                    "camp": "独行玩家",
                    "cultivation_level": "LV.45 影舞者 (全敏加点)",
                    "public_profile": "一身玄黑轻甲，面戴半截黑骨面具，双手各反握一柄泛着幽暗微光的短刃，身姿鬼魅。",
                    "secret_profile": "【神级被动】拥有内测遗留唯一专属被动“绝对弱点洞悉”，暴击伤害无视一切护甲上限。",
                    "inventory": ["幽影双子短刃", "瞬移逃脱卷轴", "特级生命恢复药剂x5"],
                    "status": "alive"
                },
                "c2": {
                    "name": "霸天傲神",
                    "title": "霸天神域公会会长",
                    "camp": "十大超级公会联盟",
                    "cultivation_level": "LV.48 圣堂重骑士 (全身史诗)",
                    "public_profile": "全身暗金重装铠甲，手持三米金光巨盾与裁决战锤，麾下数十名精锐簇拥，威势滔天。",
                    "secret_profile": "【唯我独尊】垄断副本首杀与关键建帮令，视散人玩家为蝼蚁炮灰，敢阻其公会霸业者必全服追杀。",
                    "inventory": ["泰坦之壁暗金大盾", "圣裁战锤", "公会集结令"],
                    "status": "alive"
                },
                "c3": {
                    "name": "风语者",
                    "title": "暗网顶级情报贩子",
                    "camp": "中立商人协会",
                    "cultivation_level": "LV.42 虚空机械游侠",
                    "public_profile": "身披伪装迷彩披风，操作微型机械蜘蛛探测器，总能在安全区外贩售稀有道具与BOSS坐标。",
                    "secret_profile": "【通吃双方】暗中挑动顶级公会与独行高手的血战，借机大发横财收割掉落遗产。",
                    "inventory": ["折跃隐形披风", "微型自爆机械蛛x5", "全服广播喇叭"],
                    "status": "alive"
                }
            }
        elif cat == "wuxia":
            book.world.characters = {
                "c1": {
                    "name": "燕十三",
                    "title": "落魄寒刀客",
                    "camp": "关外浪人",
                    "cultivation_level": "天榜刀魁 (隐匿重伤)",
                    "public_profile": "一袭残破蓑衣，斗笠压低，腰悬一柄生锈铁刀，眼神如苍鹰般森冷孤绝。",
                    "secret_profile": "【十三绝命】刀出必饮血，十步之内不论王公巨寇，绝无生还之人。",
                    "inventory": ["生锈寒铁刀", "半葫芦烧刀子", "染血镖银"],
                    "status": "alive"
                },
                "c2": {
                    "name": "白凝霜",
                    "title": "点苍派当代掌门女",
                    "camp": "名门名宿",
                    "cultivation_level": "点苍回风剑真传",
                    "public_profile": "素白劲装，背负双剑，眉目如画却冷若冰霜，行走江湖只问青红皂白。",
                    "secret_profile": "【寻仇血誓】宗门惨遭神秘势力血洗，誓要手刃真凶，绝不惜身。",
                    "inventory": ["青霜软剑", "九花玉露丸", "点苍掌门信物"],
                    "status": "alive"
                },
                "c3": {
                    "name": "上官枭",
                    "title": "七十二路黑道总瓢把子",
                    "camp": "绿林邪魁",
                    "cultivation_level": "金钟罩大圆满",
                    "public_profile": "魁梧如山，锦衣狐裘，指戴九枚血玉扳指，谈笑间伏尸百步。",
                    "secret_profile": "【枭雄之志】暗中联合朝廷鹰犬，欲将江湖九大派一网打尽，独霸武林。",
                    "inventory": ["金丝盘龙鞭", "霹雳透骨钉", "绿林调兵令牌"],
                    "status": "alive"
                }
            }
        else:
            # 仙侠修真 / 传统凡人流通用
            book.world.characters = {
                "c1": {
                    "name": "楚无痕",
                    "title": "隐忍苟道散修",
                    "camp": "散修/亡命徒",
                    "cultivation_level": "练气八层巅峰(伪装五层)",
                    "public_profile": "楚无痕，相貌平平，身穿洗旧麻布道袍，神情谨小慎微，双手拢在宽袖之中。",
                    "secret_profile": "【绝对谨慎】精通敛息龟息之术，袖中暗藏淬毒追魂钉与疾风符，永远先寻三条逃跑路线。",
                    "inventory": ["淬毒追魂钉", "匿灵地行符x2", "阴雷子"],
                    "status": "alive"
                },
                "c2": {
                    "name": "封不破",
                    "title": "千幻魔宗暗桩",
                    "camp": "魔煞邪修",
                    "cultivation_level": "练气九层巅峰",
                    "public_profile": "封不破，一袭暗紫华袍，手摇折扇，言谈举止看似儒雅随和，眼底隐有嗜血冷光。",
                    "secret_profile": "【笑里藏刀】精通魔道幻术与化骨血毒，惯于以大义挑拨正道相残，再趁乱收割精血与金丹。",
                    "inventory": ["千幻阴煞扇", "化骨透心毒钉", "天魔血遁符"],
                    "status": "alive"
                },
                "c3": {
                    "name": "陆青霜",
                    "title": "天剑宗真传剑子",
                    "camp": "名门正道",
                    "cultivation_level": "筑基初期",
                    "public_profile": "白衣染血，青罡残剑断裂于渊石之上，眉心凝霜，宁死不屈。",
                    "secret_profile": "【孤绝剑道】宁折不弯，为护宗门尊严舍命斩碎魔修煞阵，行事刚烈绝伦。",
                    "inventory": ["青罡灵剑", "破风剑符"],
                    "status": "alive"
                }
            }

        book.chapters = []
        book.dramas = []

    def delete_book(self, book_id: str) -> bool:
        """彻底删除一本书并清理关联文件"""
        if book_id not in self.books:
            return False

        del self.books[book_id]
        file_path = BOOKS_DIR / f"{book_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                print(f"[删除文件失败] {file_path}: {e}")

        # 清理对应的番茄同步暂存目录
        bid_str = book_id if str(book_id).startswith("book_") else f"book_{book_id}"
        fanqie_dir = NOVEL_OUTPUT_DIR / "fanqie_sync" / bid_str
        if fanqie_dir.exists():
            try:
                import shutil
                shutil.rmtree(fanqie_dir)
            except Exception:
                pass

        # 若已无书籍，active_book_id 置空，绝不自动补充任何预设或占位作品
        if self.books:
            if self.active_book_id == book_id or self.active_book_id not in self.books:
                self.active_book_id = list(self.books.keys())[0]
        else:
            self.active_book_id = ""
        return True

    def delete_chapter(self, book_id: str, chapter_id) -> bool:
        """删除指定章节并重新排序重排索引"""
        book = self.books.get(book_id)
        if not book:
            return False
        orig_count = len(book.chapters)
        book.chapters = [c for c in book.chapters if str(c.get("id")) != str(chapter_id)]
        if len(book.chapters) != orig_count:
            for idx, c in enumerate(book.chapters):
                c["id"] = idx + 1
            book.current_round = len(book.chapters)
            book.save()
            return True
        return False

    def clear_chapters(self, book_id: str) -> bool:
        """清空本书所有正文章节，从零开篇"""
        book = self.books.get(book_id)
        if not book:
            return False
        book.chapters = []
        book.current_round = 0
        book.world.history = []
        book.save()
        return True

    def reset_book(self, book_id: str) -> bool:
        """管理员重置一本书的演化天地（仅管理员可操作）"""
        if book_id not in self.books:
            return False
        book = self.books[book_id]
        book.current_round = 0
        book.world.history = []
        book.save()
        return True

    def update_book_outline(self, book_id: str, outline_data: Dict[str, Any]) -> bool:
        """更新并保存书籍大纲"""
        if book_id not in self.books:
            return False
        book = self.books[book_id]
        book.outline = outline_data
        book.save()
        return True

    def get_active_foreshadowings(self, book: Book) -> List[Dict[str, Any]]:
        """获取当前尚未完全揭开或回收的长程伏笔线索列表"""
        return [f for f in book.foreshadowings if f.get("status") in ("planted", "progressing")]

    def add_or_update_foreshadowing(self, book: Book, f_data: Dict[str, Any]):
        """新增或更新一个主线伏笔"""
        f_id = f_data.get("id") or f"f_{int(time.time()*1000)%1000000}"
        for existing in book.foreshadowings:
            if existing.get("id") == f_id:
                existing.update(f_data)
                book.save()
                return existing

        new_f = {
            "id": f_id,
            "title": f_data.get("title", "未命名暗线伏笔"),
            "detail": f_data.get("detail", ""),
            "planted_chapter": f_data.get("planted_chapter", len(book.chapters) + 1),
            "status": f_data.get("status", "planted"),
            "resolved_chapter": f_data.get("resolved_chapter", None)
        }
        book.foreshadowings.append(new_f)
        book.save()
        return new_f

    def delete_foreshadowing(self, book: Book, f_id: str) -> bool:
        """删除一个伏笔"""
        orig_len = len(book.foreshadowings)
        book.foreshadowings = [f for f in book.foreshadowings if f.get("id") != f_id]
        if len(book.foreshadowings) != orig_len:
            book.save()
            return True
        return False

    def apply_deterministic_settlement(self, book: Book, settlement: Dict[str, Any]):
        """
        确定性状态机结算：
        1. 道具/符箓法宝严格扣除与新增（杜绝凭空变出道具）
        2. 伤势与真实健康度状态更新（杜绝凭空愈合）
        3. 生死与脱逃判定落盘
        """
        if not settlement or not isinstance(settlement, dict):
            return

        chars = book.world.characters

        # 1. 道具消耗与获取
        consumed_items = settlement.get("consumed_items", {})
        for char_name, items in consumed_items.items():
            for c_id, c in chars.items():
                if c.get("name") == char_name:
                    inv = c.get("inventory", [])
                    for item in items:
                        # 模糊匹配或精确移除
                        for existing_item in list(inv):
                            if item in existing_item or existing_item in item:
                                inv.remove(existing_item)
                                break
                    c["inventory"] = inv

        gained_items = settlement.get("gained_items", {})
        for char_name, items in gained_items.items():
            for c_id, c in chars.items():
                if c.get("name") == char_name:
                    inv = c.get("inventory", [])
                    for item in items:
                        if item not in inv:
                            inv.append(item)
                    c["inventory"] = inv

        # 2. 伤势记录与持久化
        injuries_dict = settlement.get("injuries", {})
        for char_name, injury in injuries_dict.items():
            for c_id, c in chars.items():
                if c.get("name") == char_name:
                    existing_injuries = c.get("injuries", [])
                    if isinstance(injury, list):
                        existing_injuries.extend(injury)
                    elif injury:
                        existing_injuries.append(injury)
                    c["injuries"] = list(set(existing_injuries))

        # 3. 生死命运与状态结算
        fates = settlement.get("character_fates", {})
        for char_name, fate in fates.items():
            for c_id, c in chars.items():
                if c.get("name") == char_name:
                    if fate in ("dead", "身死道消", "陨落"):
                        c["status"] = "dead"
                    elif fate in ("escaped", "远遁", "逃脱"):
                        c["status"] = "escaped"
                    elif fate in ("critically_injured", "重伤", "重创", "重伤垂死"):
                        c["status"] = "critically_injured"
                    elif fate in ("alive", "重伤存活", "在场", "存活"):
                        c["status"] = "alive"

        book.save()

    def generate_book_outline(self, book_id: str, llm_client: Any = None, force_mock: bool = False) -> Dict[str, Any]:
        """基于书名、题材和核心梗，由大纲规划师智能生成全书架构、力量体系与分卷设计"""
        if book_id not in self.books:
            return {}
        book = self.books[book_id]

        if not force_mock and llm_client and getattr(llm_client, "api_key", None):
            model = os.getenv("TIANDAO_MODEL") or os.getenv("MODEL_NAME") or "balanced-model"
            prompt = f"""
你是一位拥有百万字爆款网文架构经验的【终极大纲策划宗师】。
请为以下新书制定专业、高吸睛度、主线明确的【长篇全书总大纲】：

【书名】：{book.title}
【题材流派】：{book.genre}
【核心设定/脑洞】：{book.theme_prompt or book.synopsis}

请从网文黄金开局、钩子设计、战力/势力体系、主线总目标、分卷演进四个维度输出。
必须严格输出纯净 JSON 格式：
```json
{{
  "world_view": "宏大而独特的时代/世界观背景体系 (150~250字)",
  "power_system": "升级体系或阶层晋升脉络 (如修为境界/社会权柄/商业体量)",
  "main_plot": "全书最终极的核心主线目标与不可调和的矛盾冲突 (150~250字)",
  "protagonist_setting": "核心破局者的人设立体标签、金手指或生存信条",
  "volumes": [
    {{
      "volume_num": 1,
      "title": "第一卷 卷名 (如: 潜龙在渊 / 奉天风雨)",
      "theme": "本卷核心矛盾 (如: 摆脱微末死局，初掌锋芒)",
      "climax_event": "本卷终极高潮冲突大事件"
    }},
    {{
      "volume_num": 2,
      "title": "第二卷 卷名",
      "theme": "本卷核心矛盾",
      "climax_event": "本卷终极高潮冲突大事件"
    }},
    {{
      "volume_num": 3,
      "title": "第三卷 卷名",
      "theme": "本卷核心矛盾",
      "climax_event": "本卷终极高潮冲突大事件"
    }}
  ],
  "chapter_outlines": [
    {{
      "chapter_num": 1,
      "title": "第一章 章节名",
      "goal": "本章开局即爆发的生存/退婚/奇案危机与目标",
      "conflict": "主要对手或环境压迫的冲突点",
      "climax": "主角显露底牌或第一步破局",
      "ending_hook": "章末留下的巨大悬念"
    }}
  ]
}}
```
"""
            try:
                raw = llm_client.chat(model, [
                    {"role": "system", "content": "你是顶级网络文学总策划与架构宗师，擅长设计极具张力与因果逻辑的大纲。"},
                    {"role": "user", "content": prompt}
                ], temperature=0.7)
                parsed = llm_client.extract_json(raw)
                if parsed and isinstance(parsed, dict) and parsed.get("main_plot"):
                    book.outline = parsed
                    book.save()
                    return parsed
            except Exception as e:
                print(f"[大纲生成异常] {e}，将采用智能算法生成高质量结构化大纲...")

        # 智能模板与题材自适应大纲 (高质量动态兜底)
        cat = classify_genre(book.genre, book.title, book.theme_prompt or book.synopsis)
        title_core = (book.title or "当前作品").replace("《", "").replace("》", "").strip()
        theme_core = (book.theme_prompt or book.synopsis or "").strip()

        if cat == "urban":
            syn_text = f"聚焦{theme_core}。" if theme_core else "表面由四大千亿财阀与隐秘商会垄断，地下暗流涌动。"
            outline = {
                "world_view": f"当代繁华都市江城与现代资本市场。{syn_text} 各大家族与跨国资本集团暗流涌动，豪门博弈与名利角逐层出不穷。",
                "power_system": "草根蛰伏/低谷逆风 -> 初掌乾坤(千万资本/行业翘楚) -> 商业巨擘(掌控千亿商会) -> 镇国财阀(制定全球产业格局)",
                "main_plot": f"围绕《{title_core}》展开：主角在困局中破局崛起，以雷霆手腕与超前眼界横扫当年背叛与陷害自己的强敌，打脸豪门财阀，最终登顶现代都市巅峰！{('核心设定：' + theme_core) if theme_core else ''}",
                "protagonist_setting": "行事冷峻果决，底牌无穷，恩怨分明，擅长商战洞察与绝地反击。",
                "volumes": [
                    {"volume_num": 1, "title": "第一卷 · 龙腾云起", "theme": "微末破局，打脸豪门伪君子与初掌资本锋芒", "climax_event": "江州至尊商界晚宴，当众撕开阴谋伪证，全场震颤"},
                    {"volume_num": 2, "title": "第二卷 · 商海覆雨", "theme": "横扫东南财阀联盟，强力整合核心产业", "climax_event": "千亿跨国资本对赌决战，一举击穿做空主力"},
                    {"volume_num": 3, "title": "第三卷 · 鼎立天下", "theme": "制定全球行业新标准，成就不可撼动的财阀神话", "climax_event": "全球首富峰会加冕，执掌商业帝国牛耳"}
                ],
                "chapter_outlines": []
            }
        elif cat == "history":
            syn_text = f"围绕{theme_core}展开。" if theme_core else "紫禁城风云变幻，庙堂杀机四伏，百官战栗。"
            outline = {
                "world_view": f"古代王朝波诡云谲的庙堂历史风云。{syn_text} 官场倾轧、藩王割据与士绅门阀盘根错节，天下大势系于一线。",
                "power_system": "戴枷微末寒士 -> 钦差提刑官 -> 都察院御史 -> 参知政事 / 当朝首辅",
                "main_plot": f"围绕《{title_core}》展开：主角以缜密谋略与格物新政为刃，在金殿朝堂之上自证清白并撕开弥天大案！随后持天子剑整肃吏治，平定四方边患，位极人臣！",
                "protagonist_setting": "心细如发，微表情测谎，深谙帝王心术与律法刑名，不畏强权。",
                "volumes": [
                    {"volume_num": 1, "title": "第一卷 · 金殿惊雷", "theme": "戴枷自辩，力挽狂澜破江南税银大案", "climax_event": "当庭手撕假账伪证，天子赐尚方宝剑"},
                    {"volume_num": 2, "title": "第二卷 · 江南血案", "theme": "巡抚衙门密室惊变与官绅门阀围剿", "climax_event": "连斩贪墨大员，震慑东南百年士族"},
                    {"volume_num": 3, "title": "第三卷 · 治隆盛世", "theme": "革新赋税钱粮，开海通商，帝师首辅", "climax_event": "奉天殿封公拜相，开创万世太平"}
                ],
                "chapter_outlines": []
            }
        elif cat == "scifi":
            outline = {
                "world_view": f"太阳系柯伊伯带外围，第七深空舰队在硅基机械蜂群与高维天灾的夹缝中苦苦支撑。{book.synopsis}",
                "power_system": "军用义体三阶 -> 轨道重装突击队长 -> 星际巡洋舰长 -> 戴森球执政官 -> 高维机械飞升",
                "main_plot": f"面对巨型财阀的残酷剥削与深空外星蜂群的灭顶之灾，主角凭借绝密先驱密钥与硬核舰队战术，率领底层拾荒者与退役老兵绝地反攻，撕碎高维文明的灭世阴谋！",
                "protagonist_setting": "冷酷理性，超频神经反应，兼具深空星舰战术大师与底层义体游侠风骨。",
                "volumes": [
                    {"volume_num": 1, "title": "第一卷 · 废土锈带", "theme": "底层空间站拾荒觉醒，破解先驱幽灵密钥", "climax_event": "单兵突入轨道空间港，抢夺泰坦巡洋舰"},
                    {"volume_num": 2, "title": "第二卷 · 跃迁风暴", "theme": "深入小行星带黑市，组建第七退役联合舰队", "climax_event": "伏击财阀主力舰队，引爆木星引力弹弓"},
                    {"volume_num": 3, "title": "第三卷 · 星火不熄", "theme": "直面外星远古母巢，点燃恒星级反物质熔炉", "climax_event": "跨维度歼星主炮对轰，重铸太阳系防线"}
                ],
                "chapter_outlines": []
            }
        elif cat == "suspense":
            outline = {
                "world_view": f"表世界平静繁华，里世界怪谈横行。在不可逆的规则污染下，常识被全面颠覆。{book.synopsis}",
                "power_system": "守夜执灯人 -> 禁忌收容级调查员 -> 规则解构大师 -> 序列零·不可名状主宰",
                "main_plot": f"每当午夜降临，诡异规则怪谈无差别吞噬生灵。主角觉醒‘直视规则裂隙’异能，在绝境收容副本中以命为饵推演生存守则，揭开全城诡异降临背后的终极灾厄真相！",
                "protagonist_setting": "极度理智克制，抗San值狂降，善于从荒诞死局的字里行间抓出规则逻辑漏洞。",
                "volumes": [
                    {"volume_num": 1, "title": "第一卷 · 迷雾公寓", "theme": "破解租客守则十三条，逃离红衣诡异追杀", "climax_event": "反向利用敲门杀人规则，封印房东真身"},
                    {"volume_num": 2, "title": "第二卷 · 幽灵列车", "theme": "末班地铁上的连环收容失控事件", "climax_event": "列车脱轨瞬间，撕碎列车长面具篡夺掌控权"},
                    {"volume_num": 3, "title": "第三卷 · 终焉源头", "theme": "深潜异常对策局地下收容总库，直面旧日根源", "climax_event": "以凡人之躯点燃薪火，重写世界底层因果"}
                ],
                "chapter_outlines": []
            }
        elif cat == "fantasy":
            outline = {
                "world_view": f"艾泽兰德古大陆，七大人类王国受深渊黑潮侵蚀，巨龙沉睡，圣堂神权衰微。{book.synopsis}",
                "power_system": "青铜扈从 -> 白银剑士 -> 黄金阶圣殿骑士 -> 传奇魔剑圣 -> 半神位面领主",
                "main_plot": f"黑石堡领地危在旦夕，主角觉醒沉睡千年的破晓龙皇血脉，内惩腐败贵族与审判庭猎巫狂热，外抗深渊食尸鬼与荒原兽人入侵，一步步征服四方领地，铸就永恒不落的黎明帝国！",
                "protagonist_setting": "沉稳果敢，精通领地经营与冷兵器军团战术，拥有至高龙息金焰。",
                "volumes": [
                    {"volume_num": 1, "title": "第一卷 · 黑石破晓", "theme": "守卫孤堡黑石崖，抗击兽人军团第一波血战", "climax_event": "雪夜斩首兽人统领，觉醒黄金龙鳞斗气"},
                    {"volume_num": 2, "title": "第二卷 · 凛冬风暴", "theme": "荡平北境割据领主，破获教廷深渊异端密谋", "climax_event": "千骑夜袭冰封要塞，加冕北境公爵"},
                    {"volume_num": 3, "title": "第三卷 · 诸神黄昏", "theme": "深渊裂隙全面崩塌，迎战深渊魔神降临", "climax_event": "拔起誓约破晓圣剑，以龙神之火净化世间"}
                ],
                "chapter_outlines": []
            }
        elif cat == "gaming":
            outline = {
                "world_view": f"划时代沉浸潜行网游《神域纪元》公测，实则是神级文明筛选生灵的诸天竞技场。{book.synopsis}",
                "power_system": "新人学徒(LV.1~10) -> 进阶职业(LV.20~40) -> 觉醒圣域(LV.60~80) -> 诸天神祇(LV.100+)",
                "main_plot": f"身为重生封弊者的主角带着前世十年的攻略记忆开局，首杀隐藏神级隐藏BOSS，疯狂叠加唯一被动与神装词条，单挑超级公会垄断联盟，最终带领全服玩家打破虚空壁垒！",
                "protagonist_setting": "极限微操独狼，机制怪，冷酷无情，利益最大化，深谙游戏底层数值逻辑。",
                "volumes": [
                    {"volume_num": 1, "title": "第一卷 · 幽影觉醒", "theme": "新手村通关地狱隐藏副本，夺得唯一神级匕首", "climax_event": "单人团灭霸天公会百人精英团，名震全服"},
                    {"volume_num": 2, "title": "第二卷 · 公会争霸", "theme": "抢占天下第一公会要塞，首通跨服深渊秘境", "climax_event": "要塞守城决战，以一敌万激活禁咒神罚"},
                    {"volume_num": 3, "title": "第三卷 · 终焉神选", "theme": "全球跨服总决赛与世界壁垒降临之战", "climax_event": "弑神之战，打破虚拟现实边界成就至高"}
                ],
                "chapter_outlines": []
            }
        elif cat == "wuxia":
            outline = {
                "world_view": f"风雨飘摇的大熙江湖，名门正派与绿林七十二道各怀宿怨，朝廷鹰犬与塞外胡虏虎视眈眈。{book.synopsis}",
                "power_system": "三流趟子手 -> 二流镖师/名宿真传 -> 一流刀剑客 -> 绝顶地榜宗师 -> 天榜神话",
                "main_plot": f"围绕《{title_core}》展开：主角一人一刀踏入腥风血雨的江湖，斩破名门伪君子的重重陷阱与魔门阴谋，快意恩仇，踏平天下不平事！",
                "protagonist_setting": "冷峻萧瑟，孤胆仗义，信守承诺，拔刀必见血。",
                "volumes": [
                    {"volume_num": 1, "title": "第一卷 · 关外寒刀", "theme": "雪夜破杀局，斩断名门追杀令", "climax_event": "黑风寨雪夜决死战，一人一刀斩三十六骑"},
                    {"volume_num": 2, "title": "第二卷 · 龙门风云", "theme": "入中原追查灭门真相，名门大会问剑", "climax_event": "华山顶问剑天下名宿，撕开武林盟主伪善面具"},
                    {"volume_num": 3, "title": "第三卷 · 绝顶沧桑", "theme": "抗击塞外大军围城，孤身直捣敌营", "climax_event": "千军万马前刀斩敌酋，留名青史拂衣去"}
                ],
                "chapter_outlines": []
            }
        else:
            outline = {
                "world_view": f"大千浩瀚修仙界，九重天地万族林立，古老秘境杀机四伏。{book.synopsis}",
                "power_system": "练气 -> 筑基 -> 结丹 -> 元婴 -> 化神 -> 飞升",
                "main_plot": "天道无情，人人争渡！无钦定天命主角，众生各怀鬼胎在生死绝地中谋求长生一线机缘。主角秉承绝对谨慎与果决杀伐，在宗门倾轧与魔道围猎中步步夺天造化，独断仙路！",
                "protagonist_setting": "极度谨慎内敛，谋定而后动，暗扣三道退路，绝不贪功冒进。",
                "volumes": [
                    {"volume_num": 1, "title": "第一卷 · 寒渊争渡", "theme": "绝地夺宝，弱肉强食与生死脱困", "climax_event": "古修遗府坍塌，斩筑基夺机缘遁走"},
                    {"volume_num": 2, "title": "第二卷 · 乱星碎魔", "theme": "散修扮猪吃虎，猎妖夺丹与宗门围猎", "climax_event": "结丹雷劫降临，万仙大阵血洗仇敌"},
                    {"volume_num": 3, "title": "第三卷 · 踏破苍穹", "theme": "逆行伐仙，直面无情天道因果浩劫", "climax_event": "飞升天门大开，独掌大千命数"}
                ],
                "chapter_outlines": []
            }

        book.outline = outline
        book.save()
        return outline

    def get_or_plan_chapter_outline(self, book: Book, chapter_num: int, llm_client: Any = None, force_mock: bool = False) -> Dict[str, Any]:
        """获取或智能规划特定章节的细纲蓝图（核心矛盾、目标、冲突、高潮、钩子）"""
        if not book.outline or not book.outline.get("main_plot"):
            self.generate_book_outline(book.id, llm_client, force_mock)

        # 检查是否已存在当前章细纲
        chap_outlines = book.outline.get("chapter_outlines", [])
        for co in chap_outlines:
            if co.get("chapter_num") == chapter_num:
                return co

        # 根据全书主线、卷大纲与前文进展动态生成本章细纲
        vol_info = ""
        if book.outline.get("volumes"):
            # 假定约 20~30 章一卷
            vol_idx = min(len(book.outline["volumes"]) - 1, (chapter_num - 1) // 25)
            vol = book.outline["volumes"][vol_idx]
            vol_info = f"所属分卷：{vol.get('title')}（{vol.get('theme')}）"

        # 提取当前待推进的长程伏笔线索
        active_foreshadowings = self.get_active_foreshadowings(book)
        foreshadow_hint = ""
        if active_foreshadowings:
            f_list = [f"- 【{f['title']}】：{f['detail']}（已潜伏 {max(0, chapter_num - f.get('planted_chapter', 1))} 章）" for f in active_foreshadowings[:3]]
            foreshadow_hint = "【当前待推进/揭开的长程暗线伏笔（建议本章适度呼应）】：\n" + "\n".join(f_list) + "\n"

        # 提取前一章标题作为上下文承接
        prev_chap_title = "开篇启程"
        if book.chapters:
            prev_chap_title = book.chapters[-1].get("title", f"第{len(book.chapters)}章")

        new_plan = {
            "chapter_num": chapter_num,
            "title": f"第{chapter_num}章 宿命对峙，风云激变",
            "goal": f"围绕主线核心目标推进剧情，在前章【{prev_chap_title}】基础上激化各方博弈",
            "conflict": "各方核心势力的利益碰撞与生死对决，危机逼近极限",
            "climax": "关键底牌掀开，胜负天平出现剧烈反转",
            "ending_hook": "危机暂歇但引出更深层的未知迷局或外部强敌",
            "foreshadowing_notes": ""
        }

        if not force_mock and llm_client and getattr(llm_client, "api_key", None):
            model = os.getenv("TIANDAO_MODEL") or os.getenv("MODEL_NAME") or "fast-model"
            prompt = f"""
请为长篇小说《{book.title}》（{book.genre}）规划【第 {chapter_num} 章】的详细剧情细纲：
【全书主线】：{book.outline.get('main_plot')}
【分卷背景】：{vol_info}
【前一章标题】：{prev_chap_title}
{foreshadow_hint}
请确保情节环环相扣，有爆发、有反转、有伏笔回收。输出严格 JSON：
```json
{{
  "chapter_num": {chapter_num},
  "title": "第{chapter_num}章 章节名 (如: 第{chapter_num}章 绝地反杀，暗度陈仓)",
  "goal": "本章核心人物的行动目标",
  "conflict": "本章的核心阻碍与矛盾交锋",
  "climax": "本章最高潮的情节爆点与反转",
  "ending_hook": "章末留给读者的强烈追更悬念",
  "new_foreshadowing": {{
    "title": "本章新埋下的隐秘伏笔标题 (若无则填空)",
    "detail": "伏笔具体细节（如一件神秘残破法宝的暗槽、一位身份成谜的过客）"
  }},
  "resolved_foreshadowing_title": "本章揭晓或回收的前文伏笔标题 (若无填空)"
}}
```
"""
            try:
                raw = llm_client.chat(model, [
                    {"role": "system", "content": "你是资深小说策划，擅长为连载网文设计高吸睛度、节奏明快的分章细纲与伏笔体系。"},
                    {"role": "user", "content": prompt}
                ], temperature=0.7)
                parsed = llm_client.extract_json(raw)
                if parsed and isinstance(parsed, dict) and parsed.get("title"):
                    new_plan.update(parsed)
                    new_plan["chapter_num"] = chapter_num

                    # 处理新埋伏笔
                    new_f = parsed.get("new_foreshadowing")
                    if new_f and isinstance(new_f, dict) and new_f.get("title"):
                        self.add_or_update_foreshadowing(book, {
                            "title": new_f["title"],
                            "detail": new_f.get("detail", ""),
                            "planted_chapter": chapter_num,
                            "status": "planted"
                        })

                    # 处理回收伏笔
                    res_title = parsed.get("resolved_foreshadowing_title")
                    if res_title:
                        for f in book.foreshadowings:
                            if res_title in f.get("title", "") or f.get("title", "") in res_title:
                                f["status"] = "resolved"
                                f["resolved_chapter"] = chapter_num
                                break
            except Exception as e:
                print(f"[章节细纲策划提示] 使用自适应算法规划第 {chapter_num} 章: {e}")

        chap_outlines.append(new_plan)
        book.outline["chapter_outlines"] = chap_outlines
        book.save()
        return new_plan



# 全局多书库单例
book_mgr = BookManager()
