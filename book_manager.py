import os
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

from world_state import WorldState, RoundLog, CharacterAction
from config import load_dotenv

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
        book.created_at = data.get("created_at", time.time())
        book.updated_at = data.get("updated_at", time.time())
        return book

    def save(self):
        """保存本书到本地 JSON 文件"""
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
        self.active_book_id: str = "book_xiuxian"
        self.load_all_books()

    def load_all_books(self):
        """从 BOOKS_DIR 加载所有书籍，若为空则初始化默认的3本标杆大作"""
        book_files = list(BOOKS_DIR.glob("*.json"))
        if book_files:
            for bf in book_files:
                try:
                    data = json.loads(bf.read_text(encoding="utf-8"))
                    book = Book.from_dict(data)
                    self.books[book.id] = book
                except Exception as e:
                    print(f"[读取书籍失败] {bf}: {e}")

        # 若无书籍或缺少修仙标杆书，进行内置初始化
        if not self.books:
            self._init_default_showcase_books()

        if self.active_book_id not in self.books:
            self.active_book_id = list(self.books.keys())[0]

    def _init_default_showcase_books(self):
        """预置3本不同风格的完整长篇书籍：凡人修仙、都市逆袭、历史大明"""
        # 1. 凡人修仙
        novel_path = NOVEL_OUTPUT_DIR / "novel_chapter_01.md"
        xiuxian_ch1_content = ""
        if novel_path.exists():
            try:
                xiuxian_ch1_content = novel_path.read_text(encoding="utf-8")
            except Exception:
                pass
        if not xiuxian_ch1_content:
            xiuxian_ch1_content = "## 第一章 万绝古渊\n\n万绝古渊上空，天光裂开一道百丈长缝隙，暗紫煞气如瀑倾泻……"

        book_xiuxian = Book(
            book_id="book_xiuxian",
            title="《大千争渡录：万绝古渊篇》",
            genre="传统凡人修仙",
            synopsis="万绝古渊天光破裂百丈长缝，暗紫煞气如瀑倾泻，古老仙煞残图出世！天剑宗真传陆青霜持青罡孤剑而战，千幻魔修封不破笑里藏刀暗布化骨毒钉，苟道散修楚无痕匿形背阴处暗扣破空地行符，摸金散修百里遁潜行夺宝……大道无情，万仙争渡，人人皆怀鬼胎，生死尽归天道！",
            theme_prompt="传统凡人修仙群像，冷酷暗黑智斗，人人皆主角",
            current_round=2
        )
        book_xiuxian.world.title = "【万绝古渊 · 仙煞残图出世】"
        book_xiuxian.world.scene_description = "万绝古渊上空，天光裂开一道百丈长缝隙，暗紫煞气如瀑倾泻，古老封禁被地脉震裂。四方灵压狂暴如沸水，各路争渡修士闻风破空而至！"
        book_xiuxian.world.characters = {
            "char_1": {
                "name": "楚无痕",
                "title": "隐忍苟道散修",
                "camp": "散修/亡命徒",
                "cultivation_level": "练气八层巅峰(伪装五层)",
                "public_profile": "楚无痕，相貌平平，身穿洗旧麻布道袍，神情谨小慎微，双手拢在宽袖之中。",
                "secret_profile": "【绝对谨慎】精通敛息龟息之术，袖中暗藏淬毒追魂钉与疾风符，永远先寻三条逃跑路线。",
                "inventory": ["淬毒追魂钉", "匿灵地行符x2", "阴雷子"],
                "status": "alive"
            },
            "char_2": {
                "name": "封不破",
                "title": "千幻魔宗暗桩",
                "camp": "魔煞邪修",
                "cultivation_level": "练气九层巅峰",
                "public_profile": "封不破，一袭暗紫华袍，手摇折扇，言谈举止看似儒雅随和，眼底隐有嗜血冷光。",
                "secret_profile": "【笑里藏刀】精通魔道幻术与化骨血毒，惯于以大义挑拨正道相残，再趁乱收割精血与金丹。",
                "inventory": ["千幻阴煞扇", "化骨透心毒钉", "天魔血遁符"],
                "status": "alive"
            },
            "char_3": {
                "name": "灰袍神秘客",
                "title": "匿息邪修",
                "camp": "散修老怪",
                "cultivation_level": "筑基初期",
                "public_profile": "灰袍罩头，不见面容，断臂染血，周身隐有凄厉黑烟盘旋。",
                "secret_profile": "【绝地搏命】暗中祭炼万魂幡，断臂之仇深种，伺机召唤煞鬼同归于尽。",
                "inventory": ["幽冥白骨幡", "隐息匿形披风", "爆炎魔符"],
                "status": "alive"
            },
            "char_4": {
                "name": "百里遁",
                "title": "地行夺宝客",
                "camp": "黑市摸金散修",
                "cultivation_level": "练气九层巅峰",
                "public_profile": "百里遁，身披土黄隐灵披风，悄无声息潜行于碎石废墟之中，双手戴满破禁金丝手套。",
                "secret_profile": "【唯利是图】专掏陨落大能遗蜕储物袋，绝不参与正面搏杀，得手瞬息遁地千里。",
                "inventory": ["天罗遁地铲", "绝息符x5", "烟罗遁影网"],
                "status": "alive"
            },
            "char_5": {
                "name": "陆青霜",
                "title": "天剑宗真传剑子",
                "camp": "名门正道",
                "cultivation_level": "筑基初期",
                "public_profile": "白衣染血，青罡残剑断裂于渊石之上，眉心凝霜，宁死不屈。",
                "secret_profile": "【孤绝剑道】宁折不弯，为护宗门尊严舍命斩碎魔修煞阵，最终力竭陨落。",
                "inventory": ["青罡残剑", "破风剑符"],
                "status": "dead"
            }
        }
        book_xiuxian.world.history = [
            RoundLog(
                round_number=1,
                environment_state="深渊地脉崩裂，万丈霞光冲天而起，照彻万里苍穹，古阵封印被剧烈震裂！",
                tiandao_intervention="【天地因果初显】：仙煞残图现世，陆青霜、封不破、楚无痕同时降临，三方各怀鬼胎形成三角对峙。",
                actions=[
                    CharacterAction(char_id="楚无痕", char_name="楚无痕", inner_thought="此地煞气冲天必有大凶，我且隐于最下风处，暗扣地行符！", speech="在下偶感灵气路过，绝无与诸位争夺之意……", action="神色慌乱退至乱石背阴处，袖中暗扣追魂钉。"),
                    CharacterAction(char_id="陆青霜", char_name="陆青霜", inner_thought="这帮散修与邪修心怀鬼胎，待灵图现世，唯有一剑斩之！", speech="天材地宝有缘者得之，宵小之徒妄动休怪飞剑无情！", action="青罡灵剑出鞘三寸，护体剑气绞碎方圆三丈碎石。"),
                    CharacterAction(char_id="封不破", char_name="封不破", inner_thought="桀桀，一个胆怯散修，一个傲慢剑修，待他们火并力竭，储物袋全归我！", speech="仙子何必如此凌厉？宝物现世见者有份，不如合力探寻？", action="折扇轻摇踏前一步，袖底将化骨透心毒钉按入冻土。")
                ],
                arbitration_result="三方修士于深渊边缘对峙，神识与暗器已死死锁定彼此，杀机一触即发！"
            ),
            RoundLog(
                round_number=2,
                environment_state="雷火狂暴炸裂，断崖峭壁巨石崩裂，古阵法纹被余波撕开数十丈裂痕！",
                tiandao_intervention="【因果生死结算】：陆青霜青罡剑气绞碎大阵，却遭封不破暗毒偷袭与灰袍客夹攻【身死道消】！楚无痕趁乱夺得半卷残图【远遁脱离】！摸金修士百里遁趁乱潜入！",
                actions=[
                    CharacterAction(char_id="陆青霜", char_name="陆青霜", inner_thought="剑修者宁折不弯！哪怕道基崩毁，亦要斩碎这魔道杀阵！", speech="青罡——破！", action="长剑化作璀璨青芒贯穿虚空，斩断灰袍客左臂，自身亦被雷火重创力竭。"),
                    CharacterAction(char_id="封不破", char_name="封不破", inner_thought="可惜太刚易折，你的储物袋与金丹皆是我的资粮！", speech="陆道友果然刚烈，可惜了。", action="引爆七枚化骨毒钉封死陆青霜退路，折扇一展夺取残图。"),
                    CharacterAction(char_id="楚无痕", char_name="楚无痕", inner_thought="势头不妙，残图已四分五裂，抢了半卷立刻遁地千里！", speech="得罪了！", action="掷出淬毒暗器阻挡封不破，抓起半卷残图拍碎地行符没入地底。"),
                    CharacterAction(char_id="百里遁", char_name="百里遁", inner_thought="你们打生打死，爷爷我只管搜刮储物袋！", speech="嘿嘿，借储物袋一用！", action="贴地疾驰如黑鸠，踏碎残石扯下陆青霜储物袋瞬息遁走。")
                ],
                arbitration_result="【陆青霜】力战陨落，血染深渊！【楚无痕】夺得残图遁地千里，【封不破】收拢残卷，【百里遁】搜刮战利品破空而去！"
            )
        ]
        book_xiuxian.chapters = [
            {
                "id": 1,
                "title": "第一章 万绝古渊",
                "word_count": len(xiuxian_ch1_content),
                "content": xiuxian_ch1_content
            }
        ]
        book_xiuxian.dramas = [
            {
                "id": 1,
                "title": "第1集 · 天光裂渊，残图现世",
                "duration": "01:25",
                "scenes": [
                    { "speaker": "旁白", "text": "万绝古渊上空，天光裂开一道百丈长缝，暗紫煞气如瀑倾泻！千年禁地，轰然开启！", "visual": "深渊裂隙 · 紫煞遮天", "effect": "thunder" },
                    { "speaker": "陆青霜", "text": "仙煞残图现世！宵小之徒若敢妄动半步，休怪我青罡飞剑无情！", "visual": "白衣剑仙 · 霜刃凌空", "effect": "sword" },
                    { "speaker": "封不破", "text": "仙子何必动怒？见者有份，不如……合力探寻？（七枚化骨毒钉已悄然按入冻土）", "visual": "儒雅魔修 · 笑里藏刀", "effect": "poison" },
                    { "speaker": "楚无痕", "text": "在下不过是路过的寻常散修，诸位前辈请便……（袖底暗扣破空地行符，静待时机）", "visual": "麻衣苟道 · 敛息阴影", "effect": "shadow" }
                ]
            },
            {
                "id": 2,
                "title": "第2集 · 毒钉穿心，剑仙力竭",
                "duration": "01:40",
                "scenes": [
                    { "speaker": "封不破", "text": "可惜了！太刚易折，你的储物袋与金丹，皆是我的资粮！化骨透心毒钉，爆！", "visual": "惨绿毒芒 · 封死四方", "effect": "explosion" },
                    { "speaker": "陆青霜", "text": "青罡——破！纵使道基崩毁，亦要斩碎尔等魔道奸徒！", "visual": "断剑悲鸣 · 碧血染渊", "effect": "sword" },
                    { "speaker": "楚无痕", "text": "就是此刻！残图已碎，抢了半卷立刻遁地千里！疾！", "visual": "地脉黄烟 · 破空遁走", "effect": "earth" },
                    { "speaker": "百里遁", "text": "嘿嘿嘿，你们打生打死，储物袋归爷爷我了！走也！", "visual": "黑影疾掠 · 顺手牵羊", "effect": "speed" }
                ]
            }
        ]
        book_xiuxian.save()
        self.books[book_xiuxian.id] = book_xiuxian

        # 2. 现代都市逆袭
        urban_ch1 = """## 第一章 寿宴退婚，龙王归来

海州，金碧辉煌的苏家百亿寿宴大厅内，水晶吊灯洒下耀眼光华。

满堂皆是身着高定西装与晚礼服的江南名流。而在主桌旁，楚云飞一身洗得泛白的旧夹克，显得与周围格格不入。

“三年了，楚云飞，你在我们苏家洗了整整三年衣服、扫了三年地，甚至连一条狗都不如！”
苏家大少苏浩然轻蔑地将一杯滚烫的龙井茶泼在楚云飞脚边，冷笑道：“今天是我奶奶七十大寿，也是江州四大家族江少向青曼提亲的大喜日子！你识相点，立刻把这份退婚协议签了，拿着五万块滚出海州！”

四周宾客顿时发出一阵毫不掩饰的嗤笑声。

“听说当年是老爷子病危糊涂了，才招了这个山上下来的野种当上门女婿。”
“白白浪费了苏大美女三年青春！江少可是身家过百亿的江氏集团继承人，随手甩出一块帝王绿翡翠就是八百万！”

身着一袭素黑抹胸晚礼服的苏青曼站在一旁，容颜绝美清冷。她紧咬着薄唇，美眸看着神情自若的楚云飞，眸底掠过一丝复杂与愧疚：“云飞……放手吧。江家背靠南境战神府，你斗不过他们的。签了字，我私下给你五百万，保你余生衣食无忧。”

楚云飞缓缓抬起头。
他的双手随意插在口袋里，嘴角勾起一抹玩味的弧度。

谁也不知道，就在十秒钟前，他的视网膜前悄然跳出一道全球绝密暗号，腕间那枚磨损的墨色青铜戒，正在微微发烫。

【万界龙王令已解除三年封印！南境八大军团、全球天王殿三十万精锐，恭迎龙王归位！】

“苏家，当真要退这门婚？”楚云飞语气平静如水。

主座上的江天成冷笑一声，傲然走上前来，一脚踢翻楚云飞身旁的椅子，讥讽道：“怎么，不服气？在江州，我江天成想要谁死，谁就见不到明天的太阳！你这只癞蛤蟆，凭什么配拥有青曼？给我跪下求饶，本少爷或许赏你一条活路！”

话音未落，江天成身后的两名两米高的退役特种保镖狞笑着上前，蒲扇般的大手直扣楚云飞的双肩！

下一瞬！
“轰！！”

没有任何人看清楚云飞是如何出手的。只听两道令人毛骨悚然的骨裂巨响，两名两百斤的壮汉如同断线风筝般倒飞出十几米，狠狠砸碎了寿宴大厅中央的迎宾水晶玄关！

全场骤然陷入死一般的寂静！

紧接着，大厅外传来震耳欲聋的螺旋桨轰鸣声！
十架涂装漆黑的武装重型直升机划破海州夜空，将整个苏家庄园照得亮如白昼！数十名全副武装、身披玄黑蟒龙铠的冷酷军士破窗索降而入，整齐划一地单膝跪地，声震霄汉：

“天王殿统领铁鹰，率三千玄甲，恭迎龙王大人归位！”

全场百亿名流手中的香槟杯，碎了一地。"""

        book_urban = Book(
            book_id="book_urban",
            title="《都市狂龙：隐忍三年逆袭绝巅》",
            genre="现代都市逆袭",
            synopsis="海州首富苏家寿宴，百亿名流齐聚。隐忍赘婿楚云飞遭豪门阔少当众撕毁婚书、百般羞辱。殊不知，南境万亿龙王令已然解封！一声令下，十架武装直升机掠过长空，三大世家家主跪迎战神归来！昔日受辱之仇，今日百倍偿还！",
            theme_prompt="现代都市神豪逆袭，隐忍战神打脸，反派豪门全员降维打击",
            current_round=2
        )
        book_urban.world.title = "【海州苏家 · 百亿寿宴退婚杀局】"
        book_urban.world.scene_description = "金碧辉煌的苏家寿宴大厅，百亿名流推杯换盏。豪门阔少步步紧逼，撕碎婚书，殊不知苍穹之上武装机群已死死锁定方圆百里！"
        book_urban.world.characters = {
            "char_u1": {
                "name": "楚云飞",
                "title": "隐忍三年赘婿 / 南境龙王",
                "camp": "龙王殿至尊",
                "cultivation_level": "神王境巅峰 (伪装平民)",
                "public_profile": "身穿洗白旧夹克，神态冷淡散漫，双手插兜，在豪门赘婿身份中隐忍三年。",
                "secret_profile": "【潜龙归位】南境万亿至尊，麾下三十万精锐天王军，掌握全球暗黑金融帝国命脉。",
                "inventory": ["墨龙至尊戒", "天王调兵符", "黑卡"],
                "status": "alive"
            },
            "char_u2": {
                "name": "苏青曼",
                "title": "海州第一美女总裁",
                "camp": "明玉集团",
                "cultivation_level": "千亿商业帝国新星",
                "public_profile": "黑纱礼服勾勒冷艳身段，美眸清冷，江南第一美人。",
                "secret_profile": "【身不由己】承受家族巨大联姻压力，对楚云飞心怀隐秘愧疚与探究。",
                "inventory": ["明玉总裁私章", "五百万支票"],
                "status": "alive"
            },
            "char_u3": {
                "name": "江天成",
                "title": "海州顶级阔少 / 江氏继承人",
                "camp": "江州四大家族",
                "cultivation_level": "百亿资产少董",
                "public_profile": "意气风发，定制白西装，腕戴千万名表，神情狂妄不可一世。",
                "secret_profile": "【心狠手辣】勾结境外雇佣兵，意图吞并苏家全部产业，强占苏青曼。",
                "inventory": ["帝王绿翡翠", "雇佣兵联络器"],
                "status": "alive"
            },
            "char_u4": {
                "name": "铁鹰",
                "title": "龙王殿第一统领",
                "camp": "龙王军部",
                "cultivation_level": "战神级大统领",
                "public_profile": "玄黑蟒龙铠，面容如刀削，背负精钢重刀，煞气冲天。",
                "secret_profile": "【死忠效命】誓死护卫龙王，谁敢辱龙王半句，灭其九族！",
                "inventory": ["战神重刀", "直升机编队指挥仪"],
                "status": "alive"
            }
        }
        book_urban.world.history = [
            RoundLog(
                round_number=1,
                environment_state="苏家寿宴乐曲戛然而止，全场百位名流围堵楚云飞，江天成当众将退婚协议摔在楚云飞胸口！",
                tiandao_intervention="【因果律初显】：江天成携千万翡翠逼宫退婚，苏家高层集体施压，楚云飞墨龙戒解封倒计时归零！",
                actions=[
                    CharacterAction(char_id="江天成", char_name="江天成", inner_thought="今晚踩死这个废物，苏青曼和苏家药业就全是我江家的囊中之物！", speech="一个洗衣服扫地的窝囊废，也配拥有青曼？立刻签字滚蛋！", action="脚踩退婚协议，挥手示意两名两百斤保镖包抄动手。"),
                    CharacterAction(char_id="楚云飞", char_name="楚云飞", inner_thought="隐忍三年，龙王令已然解封，尔等跳梁小丑死期已至。", speech="苏家，当真要退这门婚？", action="插兜冷立，指尖转动墨龙戒向南境发送最高指令。"),
                    CharacterAction(char_id="苏青曼", char_name="苏青曼", inner_thought="江家势大通天，楚云飞再不低头今晚必横尸街头……", speech="楚云飞，签字吧，我保你余生平安！", action="咬紧红唇侧过身去，暗中让秘书备好五百万保命支票。")
                ],
                arbitration_result="豪门逼宫达到顶点，楚云飞至尊令发，风暴即将在江州苍穹降临！"
            ),
            RoundLog(
                round_number=2,
                environment_state="雷鸣般的重型武装直升机破开夜雾，探照灯暴烈照透整座苏家庄园！玻璃幕墙应声炸裂！",
                tiandao_intervention="【龙王震怒 · 天王降临】：铁鹰统领索降破窗，两名江家保镖被楚云飞瞬息轰碎，全场宾客跪地惊恐！",
                actions=[
                    CharacterAction(char_id="楚云飞", char_name="楚云飞", inner_thought="既然你们嫌我太平静，那就让这江州为之颤栗！", speech="你们刚才，想让我跪下？", action="两指轻抬轰飞保镖，目光冷冽如玄冰俯瞰江天成。"),
                    CharacterAction(char_id="铁鹰", char_name="铁鹰", inner_thought="敢辱龙王者，碎尸万段！", speech="天王殿统领铁鹰，率三千玄甲，恭迎龙王大人归位！", action="单膝轰然跪地，身后战机列阵，枪口死死锁定江天成脑门。"),
                    CharacterAction(char_id="江天成", char_name="江天成", inner_thought="直……直升机军团？他到底是什么怪物？！", speech="你……你到底是人是鬼？！", action="双腿发软一屁股瘫坐在地，名表翡翠摔得粉碎。")
                ],
                arbitration_result="【江天成】吓瘫失禁！【楚云飞】龙王身份震撼曝光，海州百亿名流全员骇然俯首！"
            )
        ]
        book_urban.chapters = [
            {
                "id": 1,
                "title": "第一章 寿宴退婚，龙王归来",
                "word_count": len(urban_ch1),
                "content": urban_ch1
            }
        ]
        book_urban.dramas = [
            {
                "id": 1,
                "title": "第1集 · 豪门寿宴，一纸退婚",
                "duration": "01:30",
                "scenes": [
                    { "speaker": "旁白", "text": "海州苏家百亿寿宴，隐忍三年的赘婿楚云飞，正在承受豪门最屈辱的退婚！", "visual": "寿宴大厅 · 锦衣华服", "effect": "spotlight" },
                    { "speaker": "江天成", "text": "楚云飞，你一个洗衣服做饭的窝囊废，凭什么霸占苏大美女？立刻签字滚蛋！", "visual": "跋扈阔少 · 踩踏协议", "effect": "shatter" },
                    { "speaker": "苏青曼", "text": "云飞，算了吧……江家有战神撑腰，你斗不过他们的！签了字，我给你五百万离开海州！", "visual": "冷艳总裁 · 满目复杂", "effect": "sorrow" },
                    { "speaker": "楚云飞", "text": "三年隐忍已满，这江州，也是时候换一个主人了……（墨龙戒微光流转）", "visual": "冷眼睨视 · 戒指觉醒", "effect": "glow" }
                ]
            },
            {
                "id": 2,
                "title": "第2集 · 龙王令出，江州颤栗",
                "duration": "01:45",
                "scenes": [
                    { "speaker": "江天成", "text": "给我废了他四肢！丢出去喂狗！", "visual": "保镖扑杀 · 凶残狞笑", "effect": "attack" },
                    { "speaker": "楚云飞", "text": "找死。（轻拂衣袖，两百斤保镖倒飞砸穿迎宾水晶墙）", "visual": "气劲爆裂 · 碎屑纷飞", "effect": "explosion" },
                    { "speaker": "铁鹰", "text": "天王殿统领铁鹰，率十架武装重机、三千玄甲，恭迎龙王大人归位！！", "visual": "战机俯冲 · 玄甲破窗", "effect": "thunder" },
                    { "speaker": "江天成", "text": "龙……龙王殿？！这不可能！你不是个穷光蛋吗？！", "visual": "阔少瘫跪 · 浑身筛糠", "effect": "fear" }
                ]
            }
        ]
        book_urban.save()
        self.books[book_urban.id] = book_urban

        # 3. 穿越历史大明
        daming_ch1 = """## 第一章 奉天殿前，戴枷破案

洪武二十五年，初冬。

南京紫禁城，暴雨如注，冷风呼啸过奉天殿前八十一级汉白玉丹陛。

大殿之内，百官伏地，噤若寒蝉。整座金銮殿沉浸在一股令人窒息的血腥杀意之中。

大明开国皇帝朱元璋面如玄铁，龙目如电，狠狠将一本沾着暗红血迹的账册砸在金砖之上！

“户部尚书、江南三府巡抚，好大的胆子！两百万石漕粮，八十万两库银，全给咱喂了硕鼠！”
老朱声音低沉沙哑，却如九天闷雷炸响在大殿每一位官员头顶：“蒋瓛！锦衣卫的大狱还有空处吗？既然查不明白是谁干的，江南三品以上，全给咱拖出去砍了！”

满朝朱紫大员叩首如捣蒜，连大气都不敢喘。

就在此时，殿尾传来一阵沉重的铁链拖地声。

“启禀陛下，微臣江南江宁县知县陆寒舟，自请戴枷上殿，有密奏呈览！”

伏地的百官中，江南知府严嵩之侄严世藩眼角猛地一跳，眼底闪过一丝阴狠。

陆寒舟，原本是二十一世纪国际刑侦法医首席专家，三天前穿越到这位郁郁不得志的七品知县身上，却发现自己早已被卷入这桩惊天税银贪腐大案，成了幕后黑手推出来的替罪羊！

今天若是破不了局，锦衣卫的剥皮实草便在眼前！

“七品知县？也敢在奉天殿上喧哗？”朱元璋双眸微眯，冷冷盯着殿尾那个身穿囚服、神态却沉静得可怕的年轻人。

陆寒舟拖着几十斤重的铁枷，缓缓行礼，声音清晰有力穿透雨幕：

“陛下！方才锦衣卫呈上的账本是伪造的！若依此账杀人，真正的江南百万两税银，今夜便会被逆党装船偷运出长江口！”

此言一出，金殿之上犹如落下一道惊雷！"""

        book_daming = Book(
            book_id="book_daming",
            title="《大明第一权相：从斩贪官开始》",
            genre="穿越历史大明",
            synopsis="大明洪武二十五年，江南税银大案爆发，老朱挥下屠刀血染南京。现代首席刑侦专家陆寒舟魂穿七品知县，身处抄家灭门绝境。凭借现代刑侦微表情心理学与法医密卷，他在奉天殿上当朝手撕伪证，揭露百官朋党阴谋，一步步逆袭成为大明首辅！",
            theme_prompt="穿越历史大明，智斗权谋破案，洪武朝铁血反贪爽文",
            current_round=1
        )
        book_daming.world.title = "【南京紫禁城 · 奉天殿惊雷破奇案】"
        book_daming.world.scene_description = "洪武紫禁城风雨交加，老朱龙颜大怒屠刀高悬。七品知县戴枷立于金殿，以现代刑侦利剑直插百年权贵咽喉！"
        book_daming.world.characters = {
            "char_d1": {
                "name": "陆寒舟",
                "title": "现代刑侦专家 / 江宁知县",
                "camp": "寒门清流破局者",
                "cultivation_level": "七品知县 (神级推演案宗)",
                "public_profile": "身披囚服戴重枷，眉宇如墨剑，目光冷峻深邃，在帝王威压下毫无惧色。",
                "secret_profile": "【现代刑侦巨擘】精通法医物证、微表情测谎与复式记账法，任何贪官破绽皆遁无可遁。",
                "inventory": ["刑侦银针", "密折破案笔记", "乾隆御制透光镜"],
                "status": "alive"
            },
            "char_d2": {
                "name": "朱元璋",
                "title": "大明开国皇帝 / 洪武大帝",
                "camp": "大明皇权",
                "cultivation_level": "至高君主",
                "public_profile": "须发微白，龙袍金冠，目光嗜杀而雄猜，一言可决天下生死。",
                "secret_profile": "【铁血反贪】平生最恨贪官蠹虫，若真有奇才能破此案救百姓，敢破格拔擢！",
                "inventory": ["尚方斩马剑", "朱批御笔", "锦衣卫符牌"],
                "status": "alive"
            },
            "char_d3": {
                "name": "严世藩",
                "title": "江南布政司幕后黑手",
                "camp": "江南士绅利益集团",
                "cultivation_level": "从四品佥事",
                "public_profile": "锦缎官服，言辞看似惶恐忠顺，眼底深处尽是阴毒与算计。",
                "secret_profile": "【硕鼠核心】将两百万税银溶铸成佛像藏于秦淮河底，誓要灭陆寒舟之口。",
                "inventory": ["淬毒暗箭", "伪造官银账册"],
                "status": "alive"
            }
        }
        book_daming.world.history = [
            RoundLog(
                round_number=1,
                environment_state="奉天殿外风雨大作，百官伏地战栗，老朱雷霆震怒拔剑欲斩！陆寒舟戴枷朗声直陈账册破绽！",
                tiandao_intervention="【奉天殿惊雷】：七品知县陆寒舟当朝指出造假水浸墨痕，老朱收剑勒令彻查！严党爪牙大骇！",
                actions=[
                    CharacterAction(char_id="朱元璋", char_name="朱元璋", inner_thought="这小知县戴着枷锁竟无半点惧色，所言若是实情，咱必让他血洗这帮贪官！", speech="七品芝麻官，你若敢欺君，咱诛你九族！讲！", action="按剑立于御案前，目光如刀直锁陆寒舟。"),
                    CharacterAction(char_id="陆寒舟", char_name="陆寒舟", inner_thought="现代法医物证学面前，你严世藩的伪造账本漏洞百出！", speech="陛下，此账乃用新墨刻意熏黄做旧，且看封皮暗记，三处借贷根本不平！", action="双手举起账本迎着殿外天光，撕开涂蜡暗层。"),
                    CharacterAction(char_id="严世藩", char_name="严世藩", inner_thought="该死！这江宁穷酸怎么可能识破这等密法？！", speech="陛下明鉴！此人乃待罪囚徒，分明是垂死攀咬重臣啊！", action="冷汗浸透内衬，伏地嘶声叩首。")
                ],
                arbitration_result="【陆寒舟】当庭揭露贪案铁证，老朱御赐金牌准其七日彻查江南大案！"
            )
        ]
        book_daming.chapters = [
            {
                "id": 1,
                "title": "第一章 奉天殿前，戴枷破案",
                "word_count": len(daming_ch1),
                "content": daming_ch1
            }
        ]
        book_daming.dramas = [
            {
                "id": 1,
                "title": "第1集 · 洪武屠刀，戴枷提审",
                "duration": "01:20",
                "scenes": [
                    { "speaker": "旁白", "text": "洪武二十五年，江南税银大案爆发，太祖朱元璋挥下屠刀，金銮殿上血雨腥风！", "visual": "奉天大殿 · 暴雨雷霆", "effect": "rain" },
                    { "speaker": "朱元璋", "text": "查不出来？江南三品以上，全给咱拖出去剥皮实草！！", "visual": "洪武大帝 · 龙颜暴怒", "effect": "thunder" },
                    { "speaker": "严世藩", "text": "陛下息怒，罪魁祸首正是那江宁知县陆寒舟，微臣已将其押解殿外受死！", "visual": "阴险权臣 · 恶毒陷害", "effect": "shadow" },
                    { "speaker": "陆寒舟", "text": "陛下！微臣自请戴枷上殿！此账乃严党伪造，真正的两百万税银，今夜就在长江口！", "visual": "铁枷知县 · 傲然昂首", "effect": "sword" }
                ]
            }
        ]
        book_daming.save()
        self.books[book_daming.id] = book_daming

    def get_active_book(self) -> Book:
        if self.active_book_id not in self.books:
            if self.books:
                self.active_book_id = list(self.books.keys())[0]
            else:
                self._init_default_showcase_books()
        return self.books[self.active_book_id]

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
        """根据管理员选定的风格题材，自动捏造初始4位极具张力的人物与第一章正文"""
        is_urban = "都市" in genre or "神豪" in genre or "逆袭" in genre or "战神" in genre
        is_trans = "穿" in genre or "历史" in genre or "大明" in genre or "重生" in genre

        if is_urban:
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
        elif is_trans:
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
        else:
            # 仙侠或科幻/通用
            book.world.characters = {
                "c1": {
                    "name": "夜无咎",
                    "title": "独行求道者",
                    "camp": "散修浪客",
                    "cultivation_level": "凝元境巅峰",
                    "public_profile": "黑袍负刀，沉默寡言，行走于生死边缘。",
                    "secret_profile": "【坚毅道心】宁向死中求生，绝不屈服于既定宿命。",
                    "inventory": ["无名断刃", "回天造化丹"],
                    "status": "alive"
                },
                "c2": {
                    "name": "姬沧海",
                    "title": "远古遗族圣子",
                    "camp": "太古世家",
                    "cultivation_level": "天人境真传",
                    "public_profile": "华袍高冠，神光护体，视凡俗如尘埃。",
                    "secret_profile": "【霸道无匹】顺我者昌逆我者亡，意图祭炼全境生灵。",
                    "inventory": ["太虚神钟", "破界古符"],
                    "status": "alive"
                }
            }

        first_chapter_text = f"## 第一章 大道初显，风云汇聚\n\n天地苍茫，{book.synopsis}。\n\n大幕拉开，各方博弈在这一刻悄然拉开序幕！"
        book.chapters = [
            {
                "id": 1,
                "title": "第一章 大道初显，风云汇聚",
                "word_count": len(first_chapter_text),
                "content": first_chapter_text
            }
        ]
        book.dramas = [
            {
                "id": 1,
                "title": "第1集 · 风云变幻，天地破晓",
                "duration": "01:15",
                "scenes": [
                    { "speaker": "旁白", "text": f"大世初开！{book.title}的传奇序章，正式掀开！", "visual": "风云卷涌 · 异象横空", "effect": "thunder" },
                    { "speaker": list(book.world.characters.values())[0]["name"], "text": "棋局已定，诸位，谁敢与我一争天下？！", "visual": "主角登场 · 锋芒毕露", "effect": "glow" }
                ]
            }
        ]

    def delete_book(self, book_id: str) -> bool:
        """管理员删除一本书（仅管理员可操作）"""
        if book_id not in self.books:
            return False
        # 不允许删除最后一本书
        if len(self.books) <= 1:
            return False

        del self.books[book_id]
        file_path = BOOKS_DIR / f"{book_id}.json"
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                print(f"[删除文件失败] {file_path}: {e}")

        if self.active_book_id == book_id:
            self.active_book_id = list(self.books.keys())[0]
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

        # 智能模板与题材自适应大纲 (高质量兜底)
        is_urban = any(k in book.genre for k in ["都市", "神豪", "逆袭", "战神"])
        is_history = any(k in book.genre for k in ["大明", "历史", "穿越", "官场"])

        if is_urban:
            outline = {
                "world_view": f"当代繁华都市江州，表面由四大千亿财阀与隐秘商会垄断，地下暗流涌动。{book.synopsis}",
                "power_system": "微末赘婿 -> 隐匿黑卡至尊 -> 江南商会魁首 -> 镇国至尊龙王",
                "main_plot": "三年隐忍期满，墨龙至尊令彻底解封！主角以雷霆手段肃清当年背叛陷害自己的世家仇敌，横推江南豪门，重夺至尊之位！",
                "protagonist_setting": "行事冷峻果决，底牌无穷，恩怨分明，视权贵为蝼蚁。",
                "volumes": [
                    {"volume_num": 1, "title": "第一卷 · 龙王出渊", "theme": "寿宴打脸退婚，江南豪门震动", "climax_event": "江州至尊峰会，万人俯首称臣"},
                    {"volume_num": 2, "title": "第二卷 · 商海覆雨", "theme": "扫平东南财阀联盟，夺回家族重器", "climax_event": "千亿跨国对赌，一举定乾坤"},
                    {"volume_num": 3, "title": "第三卷 · 镇国天下", "theme": "域外黑榜暗杀与终极至尊争锋", "climax_event": "龙王殿三千战神合流，封狼居胥"}
                ],
                "chapter_outlines": []
            }
        elif is_history:
            outline = {
                "world_view": f"大明洪武二十五年初冬，南京紫禁城暴雨如注，老朱铁腕反贪，百官战栗。{book.synopsis}",
                "power_system": "戴枷七品知县 -> 钦差提刑按察使 -> 都察院御史 -> 文华殿大学士 / 当朝首辅",
                "main_plot": "主角以现代刑侦物证与法医心理学为利剑，在奉天殿上当朝撕开贪案伪证，自证清白！随后受老朱密令，手持尚方宝剑巡按江南，肃清江南士绅蛀虫，一步步重构大明赋税与刑狱，位极人臣！",
                "protagonist_setting": "现代首席法医刑侦专家穿越，心细如发，微表情测谎，精通数理格物，不畏强权。",
                "volumes": [
                    {"volume_num": 1, "title": "第一卷 · 奉天惊雷", "theme": "戴枷自辩，力挽狂澜破江南税银案", "climax_event": "当庭手撕假账，老朱赐尚方宝剑"},
                    {"volume_num": 2, "title": "第二卷 · 江南血案", "theme": "巡抚衙门密室杀人与秦淮河沉银", "climax_event": "连斩七名四品大员，震慑东南门阀"},
                    {"volume_num": 3, "title": "第三卷 · 治隆唐宋", "theme": "革新大明宝钞与开海通商，帝师首辅", "climax_event": "奉天殿封公拜相，开创盛世"}
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
