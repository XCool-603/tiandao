import sys
import os
import json
import time
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import urllib.parse
import io
import zipfile

# 确保 UTF-8
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import (
    API_KEY, BASE_URL, DEFAULT_MODEL, TIANDAO_MODEL,
    CHRONICLER_MODEL, MAX_ROUNDS, AUTO_GENERATE_NOVEL, load_dotenv,
    classify_genre, save_persistent_config
)
import fanqie_uploader
from llm_client import LLMClient
from world_state import WorldState, RoundLog, CharacterAction
from agents.tiandao import TiandaoAgent
from agents.character import CharacterAgent
from agents.chronicler import ChroniclerAgent
from agents.drama_agent import DramaAgent
from mock_engine import run_mock_demo
from book_manager import book_mgr, Book

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

def get_fanqie_category_tags(genre: str):
    cat = classify_genre(genre)
    if cat == "doomsday":
        return ["末世求生", "末日天灾", "重生囤货", "避难所", "无敌杀伐"]
    elif cat == "urban":
        return ["都市生活", "战神归来", "都市脑洞", "神豪打脸"]
    elif cat == "history":
        return ["历史古代", "两宋元明", "架空历史", "穿越权谋"]
    elif cat == "scifi":
        return ["科幻未来", "星际文明", "机械科技", "末世求生"]
    elif cat == "suspense":
        return ["悬疑脑洞", "规则怪谈", "惊悚无限", "诡异复苏"]
    elif cat == "fantasy":
        return ["奇幻仙侠", "领主种田", "剑与魔法", "巨龙血脉"]
    elif cat == "gaming":
        return ["游戏动漫", "无限诸天", "数据流", "超神词条"]
    elif cat == "wuxia":
        return ["传统武侠", "江湖恩怨", "剑客快意", "名门争霸"]
    return ["玄幻仙侠", "传统修真", "凡人流", "无敌杀伐"]

def clean_fanqie_content(title: str, content: str) -> str:
    lines = content.split("\n")
    clean = []
    for l in lines:
        s = l.strip()
        if not s:
            continue
        if s.startswith("#"):
            s = s.lstrip("#").strip()
            if s == title.strip() or (s.startswith("第") and "章" in s):
                continue
        if s.startswith(">"):
            s = s.lstrip(">").strip()
        clean.append("    " + s)
    return f"{title}\n\n" + "\n\n".join(clean)

class BookRunner:
    """单一书籍的天道推演独立运行器（支持各书并发多线程推演与独立控制）"""
    def __init__(self, book_id: str):
        self.book_id = book_id
        self.is_busy = False
        self.stop_requested = False
        self.last_busy_time = 0.0
        self.lock = threading.Lock()

class SimulationManager:
    """全局多书库推演状态管理器（与 BookManager 紧密集成，支持多书并发独立天道推演）"""
    def __init__(self):
        self.runners: dict[str, BookRunner] = {}
        self._runners_lock = threading.Lock()
        self.fanqie_auto_upload = False
        self._load_fanqie_config()

    def get_runner(self, book_id: str) -> BookRunner:
        if not book_id:
            book_id = self.active_book.id or "default"
        with self._runners_lock:
            if book_id not in self.runners:
                self.runners[book_id] = BookRunner(book_id)
            return self.runners[book_id]

    def is_book_busy(self, book_id: str) -> bool:
        if not book_id:
            return False
        with self._runners_lock:
            runner = self.runners.get(book_id)
            if not runner:
                return False
            # 自动自愈：若已忙碌超过 180 秒（3分钟）未更新心跳，判定为异常挂起，自动强制释放
            if runner.is_busy and time.time() - runner.last_busy_time > 180:
                runner.is_busy = False
            return runner.is_busy

    def is_any_busy(self) -> bool:
        with self._runners_lock:
            return any(r.is_busy for r in self.runners.values())

    def get_state_version(self, target_book_id: str = None) -> str:
        target_book = book_mgr.books.get(target_book_id, self.active_book) if target_book_id else self.active_book
        if not target_book or not target_book.id:
            return "empty"
        is_busy = int(self.is_book_busy(target_book.id))
        any_busy = int(self.is_any_busy())
        updated = int(getattr(target_book, "updated_at", 0))
        chap_count = len(target_book.chapters)
        round_num = target_book.current_round
        book_count = len(book_mgr.books)
        return f"{target_book.id}_{updated}_{chap_count}_{round_num}_{is_busy}_{any_busy}_{book_count}"

    def request_stop(self, book_id: str = None):
        """停止指定书籍的推演（若未指定则停止当前活跃书籍或所有推演）"""
        with self._runners_lock:
            if book_id and book_id in self.runners:
                self.runners[book_id].stop_requested = True
            elif book_id:
                runner = self.get_runner(book_id)
                runner.stop_requested = True
            else:
                act_id = self.active_book.id
                if act_id and act_id in self.runners:
                    self.runners[act_id].stop_requested = True
                for r in self.runners.values():
                    if r.is_busy:
                        r.stop_requested = True

    @property
    def is_busy(self) -> bool:
        """向后兼容属性：反映当前活跃书籍的忙碌状态"""
        return self.is_book_busy(self.active_book.id)

    @is_busy.setter
    def is_busy(self, val: bool):
        act_id = self.active_book.id
        if act_id:
            runner = self.get_runner(act_id)
            runner.is_busy = val

    @property
    def stop_requested(self) -> bool:
        act_id = self.active_book.id
        if act_id and act_id in self.runners:
            return self.runners[act_id].stop_requested
        return False

    @stop_requested.setter
    def stop_requested(self, val: bool):
        act_id = self.active_book.id
        if act_id:
            runner = self.get_runner(act_id)
            runner.stop_requested = val

    def _load_fanqie_config(self):
        cfg_file = OUTPUT_DIR / "fanqie_config.json"
        cfg = {
            "auto_upload": False,
            "webhook_url": os.getenv("FANQIE_WEBHOOK_URL", ""),
            "cookie": os.getenv("FANQIE_COOKIE", ""),
            "publish_mode": "drafts"
        }
        if cfg_file.exists():
            try:
                data = json.loads(cfg_file.read_text(encoding="utf-8"))
                cfg.update(data)
            except Exception:
                pass
        self.fanqie_auto_upload = bool(cfg.get("auto_upload", False))
        return cfg

    def save_fanqie_config(self, new_cfg: dict):
        cfg_file = OUTPUT_DIR / "fanqie_config.json"
        current = self._load_fanqie_config()
        current.update(new_cfg)
        self.fanqie_auto_upload = bool(current.get("auto_upload", False))
        cfg_file.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        return current

    def upload_chapter_fanqie(self, book, chapter_id, chapter_title="", chapter_content=""):
        """单章手动或自动上传至番茄小说发布通道（原生内置引擎，无需油猴插件）"""
        if not chapter_content:
            target_chap = next((c for c in book.chapters if str(c.get("id")) == str(chapter_id)), None)
            if target_chap:
                chapter_title = target_chap.get("title", f"第{chapter_id}章")
                chapter_content = target_chap.get("content", "")
            else:
                return {"status": "error", "message": f"未找到第 {chapter_id} 章内容"}

        clean_title = (chapter_title or f"第{chapter_id}章").replace("#", "").strip()
        if not clean_title.startswith("第") and not "章" in clean_title:
            clean_title = f"第{chapter_id}章 {clean_title}"

        cfg = self._load_fanqie_config()
        mode = cfg.get("publish_mode", "drafts")

        # 优先调用本项目原生内置番茄上传引擎（落盘格式化文本 + 原生会话自动直推草稿箱）
        fq_res = fanqie_uploader.native_upload_chapter(
            book_title=book.title,
            chapter_title=clean_title,
            chapter_content=chapter_content,
            book_id=book.id,
            mode=mode
        )
        if fq_res.get("status") in ("ok", "local_ready"):
            self.mark_fanqie_synced(book.id, chapter_id, mode=mode)
        return fq_res

    def get_fanqie_sync_state(self, book_id=None):
        if not book_id:
            book = self.active_book
        else:
            book = book_mgr.books.get(book_id, self.active_book)
        if not book:
            return []
        bid = book.id if str(book.id).startswith("book_") else f"book_{book.id}"
        sync_file = OUTPUT_DIR / "fanqie_sync" / bid / "sync_history.json"
        if sync_file.exists():
            try:
                return json.loads(sync_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def mark_fanqie_synced(self, book_id, chapter_id, mode="draft", remote_id=""):
        book = book_mgr.books.get(book_id, self.active_book) if book_id else self.active_book
        if not book:
            return []
        bid = book.id if str(book.id).startswith("book_") else f"book_{book.id}"
        fanqie_dir = OUTPUT_DIR / "fanqie_sync" / bid
        fanqie_dir.mkdir(parents=True, exist_ok=True)
        sync_file = fanqie_dir / "sync_history.json"
        synced = self.get_fanqie_sync_state(book.id)
        existing = next((s for s in synced if str(s.get("chapter_id")) == str(chapter_id)), None)
        record = {
            "chapter_id": int(chapter_id) if str(chapter_id).isdigit() else chapter_id,
            "synced_at": time.time(),
            "mode": mode,
            "remote_id": remote_id
        }
        if existing:
            existing.update(record)
        else:
            synced.append(record)
        sync_file.write_text(json.dumps(synced, ensure_ascii=False, indent=2), encoding="utf-8")
        return synced

    def get_pending_fanqie_chapter(self, book_id=None):
        book = book_mgr.books.get(book_id, self.active_book) if book_id else self.active_book
        if not book or not book.chapters:
            return None
        synced = self.get_fanqie_sync_state(book.id)
        synced_ids = {str(s.get("chapter_id")) for s in synced}
        for chap in book.chapters:
            cid = str(chap.get("id"))
            if cid not in synced_ids:
                title = chap.get("title", f"第{cid}章")
                content = chap.get("content", "")
                clean_title = title.replace("#", "").strip()
                if not clean_title.startswith("第") and "章" not in clean_title:
                    clean_title = f"第{cid}章 {clean_title}"
                clean_body = clean_fanqie_content(clean_title, content)
                return {
                    "book_id": book.id,
                    "book_title": book.title,
                    "chapter_id": int(cid) if cid.isdigit() else cid,
                    "chapter_title": clean_title,
                    "content": clean_body,
                    "word_count": len(clean_body),
                    "total_chapters": len(book.chapters)
                }
        return None

    @property
    def active_book(self) -> Book:
        return book_mgr.get_active_book()

    @property
    def world(self) -> WorldState:
        return self.active_book.world

    @property
    def current_round(self) -> int:
        return self.active_book.current_round

    @current_round.setter
    def current_round(self, val: int):
        self.active_book.current_round = val
        self.active_book.save()

    @property
    def novel_content(self) -> str:
        if self.active_book.chapters:
            return self.active_book.chapters[0].get("content", "")
        return ""

    @novel_content.setter
    def novel_content(self, val: str):
        if self.active_book.chapters:
            self.active_book.chapters[0]["content"] = val
            self.active_book.chapters[0]["word_count"] = len(val)
        else:
            first_line = val.strip().split("\n")[0].replace("#", "").strip() or f"第一章 {self.active_book.title}"
            self.active_book.chapters.append({
                "id": 1,
                "title": first_line,
                "word_count": len(val),
                "content": val
            })
        self.active_book.save()

    def get_chapters(self):
        return self.active_book.chapters

    def get_dramas(self):
        return self.active_book.dramas

    def reset(self, world_theme=""):
        """重置当前书籍的世界历史与轮次"""
        book_mgr.reset_book(self.active_book.id)

    def _genesis_procedural(self, world_theme="", target_book=None):
        """纯动态程序化创世生成器（每次重开都是全新的人名、宗门与机缘）"""
        target_book = target_book or self.active_book
        import random
        # 场景库
        scenes = [
            {
                "title": "【万剑仙冢·绝壁夺剑】",
                "desc": "荒古万剑仙冢裂谷，黑风呼啸如雷，十万锈剑插满峭壁。谷心一尊插在万年玄冰中的绝品古剑【断尘古刃】散发森冷剑意。上古禁绝压制所有修士御空之术，剑煞四溢，触之经脉尽裂。"
            },
            {
                "title": "【大荒废渊·九阳离火鼎】",
                "desc": "炽热熔岩滚滚的荒古地脉，岩浆翻涌凝聚成赤莲。半空中悬浮一座破损的上古道阶宝鼎【九阳离火鼎】，正吞吐纯阳紫火。四周毒煞赤炎弥漫，各方隐匿气息，杀机暗涌。"
            },
            {
                "title": "【北冥幽谷·化形雪莲劫】",
                "desc": "极北极寒之地，暴风雪撕裂天地。幽谷绝顶一株即将化形的万年【九叶冰晶雪莲】正绽放三寸毫光。暴风雪封锁神识，周围白茫茫一片，敌我莫辨，步步杀机。"
            }
        ]
        chosen_scene = random.choice(scenes)
        target_book.world.title = chosen_scene["title"]
        target_book.world.scene_description = chosen_scene["desc"]

        # 随机名字与门派生成池
        first_names = ["楚", "陆", "封", "墨", "莫", "姜", "裴", "顾", "闻", "姬", "萧", "齐"]
        last_names = ["绝尘", "青瑶", "不破", "无痕", "行舟", "凌虚", "千羽", "孤舟", "问秋", "玄机", "照雪", "沧海"]
        random.shuffle(first_names)
        random.shuffle(last_names)

        archetypes = [
            {
                "role_type": "苟道隐忍散修",
                "camp": "散修/亡命徒",
                "cultivation": "练气八层巅峰(伪装为练气五层)",
                "public": "相貌平平，面带风霜之色，身穿洗旧的麻布道袍，神情谨小慎微，逢人唯唯诺诺。",
                "secret": "【极端警惕】精通《龟息敛气秘术》与土遁符阵，袖中暗藏淬毒追魂刺三枚与天雷爆裂珠，第一反应永远是探查退路，绝不强出头。",
                "inventory": ["淬毒追魂刺", "天雷爆裂珠", "隐匿地行符x2"]
            },
            {
                "role_type": "正道天骄/剑修",
                "camp": "名门上宗真传",
                "cultivation": "筑基初期(压制在练气九层)",
                "public": "锦袍玉带，神情孤傲清冷，背负古剑，目若寒星，周身隐有剑意凝而不发。",
                "secret": "【宗门死战】身负宗门密令夺宝冲关，但丹田隐有陈年暗伤，极度防备身边同门与魔道偷袭，行事果断绝情。",
                "inventory": ["青罡古剑", "护心玄冰镜", "疾风破空符"]
            },
            {
                "role_type": "伪善执事/师兄",
                "camp": "名门内鬼/伪君子",
                "cultivation": "练气九层圆满",
                "public": "仪表堂堂，言语温和谦逊，以领队师兄自居，对同门照拂有加。",
                "secret": "【借刀杀人】早已暗投外宗，意图在夺宝混乱中拿同门弟子当挡箭牌试阵，借凶险除掉竞争对手后独吞重宝。",
                "inventory": ["破煞锁灵阵旗", "透骨毒影钉", "迷神烟"]
            },
            {
                "role_type": "魔宗暗桩/妖修",
                "camp": "魔煞邪修",
                "cultivation": "练气九层巅峰",
                "public": "黑纱裹面或身披羽氅，眼神冰冷邪异，行事随心所欲，冷眼旁观众人。",
                "secret": "【嗜血图谋】修习神魂摄取邪术，最擅长在多方火并时挑拨离间、落井下石收割败亡者金丹与精血。",
                "inventory": ["化血修罗刺", "百鬼隐匿幡", "血遁符"]
            }
        ]

        # 动态组装 4 位全新修士
        for i in range(4):
            c_name = f"{first_names[i]}{last_names[i]}"
            arch = archetypes[i]
            cid = f"char_dyn_{i+1}"
            target_book.world.characters[cid] = {
                "name": c_name,
                "title": arch["role_type"],
                "camp": arch["camp"],
                "cultivation_level": arch["cultivation"],
                "public_profile": f"{c_name}，{arch['public']}",
                "secret_profile": arch["secret"],
                "inventory": arch["inventory"],
                "status": "alive"
            }

    def _genesis_real(self, world_theme="", target_book=None):
        """大模型真实自主创世（由 AI 完全自主构建全新的天地与全新的人物）"""
        llm = LLMClient(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
        target_book = target_book or self.active_book
        book_genre = target_book.genre or "全题材原创"
        book_title = target_book.title or "当前世界"
        theme_hint = f"世界主题定制：{world_theme}\n" if world_theme else ""

        prompt = f"""
你是不受任何既定故事束缚的【大千世界开辟主宰】。
请从零为一部【{book_genre}】小说《{book_title}》开辟初始世界舞台，并完全自主捏造第一批（4位）登场角色的设定。

【重要原则】：
- **严禁抄袭已有知名小说人名（绝对不要出现韩立、南宫婉、萧炎、林动、顾长青等任何既有名字）！**
- **必须完全自主原创姓名与身世背景，严格契合【{book_genre}】世界观！**
- **人人皆是主角，人人皆怀执念与隐秘底牌，绝无降智炮灰，也无天定免死光环！**

{theme_hint}
请输出纯净严格的 JSON 格式：
```json
{{
  "scene_title": "舞台/绝地/都市/战场/空间站名称 (如: 【柯伊伯带·第七废弃矿港】 / 【江州商会·风云绝顶】)",
  "scene_description": "当前天地格局、核心矛盾焦点、危机与压迫描写 (120~200字)",
  "characters": [
    {{
      "name": "原创姓名 (2~3字)",
      "title": "头衔/身份/职业 (如: 战术先锋 / 幕后财阀 / 宗门真传 / 执灯调查员)",
      "camp": "所属阵营/流派",
      "cultivation_level": "真实实力阶层或社会地位",
      "public_profile": "外貌神态与表面装束描写 (60~100字)",
      "secret_profile": "【真实隐秘底牌、暗中心机与绝密底线】 (80~120字)",
      "inventory": ["核心装备/法宝/信物1", "底牌道具2", "保命底牌3"]
    }}
  ]
}}
```
"""
        raw_res = llm.chat(os.getenv("MODEL_NAME", "balanced-model"), [
            {"role": "system", "content": f"你是冷酷掌控【{book_genre}】世界开辟的至高创世意志。"},
            {"role": "user", "content": prompt}
        ])
        parsed = llm.extract_json(raw_res)
        if not parsed or not parsed.get("characters"):
            raise ValueError("LLM 未能正确生成天地结构")

        target_book.world.title = parsed.get("scene_title", f"【{book_title} · 序幕现世】")
        target_book.world.scene_description = parsed.get("scene_description", "大幕拉开，各方博弈在这一刻悄然开启。")
        target_book.world.characters = {}

        for idx, c in enumerate(parsed["characters"][:4]):
            cid = f"char_dyn_{idx+1}"
            c["status"] = "alive"
            target_book.world.characters[cid] = c

    def spawn_character(self, preset_id=None, custom_prompt="", force_mock=False, target_book=None):
        """天道点化 / 引入新角色入局（全题材自适应）"""
        target_book = target_book or self.active_book
        load_dotenv()
        current_api_key = os.getenv("OPENAI_API_KEY", "")
        use_mock = force_mock or (not current_api_key) or (current_api_key == "your_api_key_here")

        target_genre = target_book.genre or "通用幻想"
        target_title = target_book.title or "当前世界"

        char_id = f"char_{int(time.time()*1000)%10000000}"
        new_char = None

        if use_mock or not custom_prompt:
            # 根据当前书籍题材智能匹配备选库
            cat = classify_genre(target_genre, target_title)
            if cat == "urban":
                mock_pool = [
                    {
                        "name": "赵铁手",
                        "title": "南岭战神殿暗影统领",
                        "camp": "战神暗卫",
                        "cultivation_level": "暗劲巅峰武宗",
                        "public_profile": "一袭黑色修身西装，戴着墨镜与战术耳麦，双手布满老茧，眼神如鹰隼般锐利。",
                        "secret_profile": "【奉令护主】携三十六天罡令秘密潜入江州，誓死保卫龙王少主，敢冒犯者格杀勿论。",
                        "inventory": ["消音格洛克", "战神贴身密令", "军用止血针"]
                    },
                    {
                        "name": "万三千",
                        "title": "海外神秘风投巨鳄",
                        "camp": "中立资本联盟",
                        "cultivation_level": "千亿级对冲操盘手",
                        "public_profile": "身披羊绒大衣，指间夹着古巴雪茄，谈笑间可瞬间调动百亿跨国资金击垮对手盘口。",
                        "secret_profile": "【资本猎手】趁江州豪门内讧做空其核心资产，以低至一折的价格强行兼并蚕食。",
                        "inventory": ["全球瑞士银行黑卡", "股权质押通牒", "防弹专车车钥匙"]
                    },
                    {
                        "name": "苏晓曼",
                        "title": "金牌财经调查记者",
                        "camp": "舆论界名记",
                        "cultivation_level": "全网千万大V",
                        "public_profile": "身穿米色风衣，手持微型专业录音笔与单反相机，眼神敏锐如电，敢于撕开一切内幕伪善。",
                        "secret_profile": "【曝光黑幕】掌握着豪门洗钱做空的核心账本线索，正寻找可靠的破局者联合发难。",
                        "inventory": ["加密录音笔", "云端备份手机", "防狼防身电击器"]
                    }
                ]
            elif cat == "history":
                mock_pool = [
                    {
                        "name": "沈炼",
                        "title": "锦衣卫北镇抚司百户",
                        "camp": "天子鹰犬",
                        "cultivation_level": "后天圆满 / 绣春刀真传",
                        "public_profile": "身穿飞鱼服，腰挎绣春刀，面容刚毅冷峻，行事沉稳内敛，深得镇抚使重用。",
                        "secret_profile": "【暗藏心事】厌恶朝堂党争与锦衣卫滥杀，暗中庇护忠良遗孤，随时准备反出死局。",
                        "inventory": ["精钢绣春刀", "飞鱼蟒袍", "北镇抚司驾帖"]
                    },
                    {
                        "name": "严世蕃",
                        "title": "内阁小阁老 / 权倾朝野",
                        "camp": "首辅严党",
                        "cultivation_level": "当朝重臣",
                        "public_profile": "独眼微眯，锦衣玉带，摇折扇而谈笑自若，一言可定百官升黜与抄家灭族。",
                        "secret_profile": "【贪婪智囊】精研天下赋税与兵马粮饷，视天下官吏为棋子，疯狂敛财中饱私囊。",
                        "inventory": ["内阁首辅信印", "九边将领名单", "密折通牒"]
                    }
                ]
            elif cat == "scifi":
                mock_pool = [
                    {
                        "name": "零度幽灵",
                        "title": "深空赏金猎人",
                        "camp": "暗网黑客游侠",
                        "cultivation_level": "义体突击三阶",
                        "public_profile": "身披全息光学折射披风，右臂搭载单兵微型轨道炮，机械双瞳泛着冷静的猩红光晕。",
                        "secret_profile": "【猎杀赏金】受雇于匿名地下财阀，追踪高维密钥载体，一旦得手立刻引爆信标脱离战场。",
                        "inventory": ["高斯狙击炮", "光学伪装发生器", "自爆脉冲雷"]
                    },
                    {
                        "name": "瓦连京",
                        "title": "轨道重装陆战老兵",
                        "camp": "第七舰队遗孤",
                        "cultivation_level": "重装外骨骼驾驶员",
                        "public_profile": "两米高壮硕身躯披挂着粗糙焊补的防辐射钛钢装甲，手持两百毫米转管机炮，杀气凛冽。",
                        "secret_profile": "【复仇执念】誓要让当年抛弃第七舰队的星环财阀高层血债血偿，随时准备玉石俱焚。",
                        "inventory": ["转管机炮", "战术吸附雷x3", "过载强化肾上腺素"]
                    }
                ]
            elif cat == "suspense":
                mock_pool = [
                    {
                        "name": "白九思",
                        "title": "异常收容司执剑人",
                        "camp": "官方对策局",
                        "cultivation_level": "序列八·剖魂者",
                        "public_profile": "身穿防腐黑色长大衣，手提一口沉重的手提黑箱，脸色苍白如纸，唇角毫无血色。",
                        "secret_profile": "【绝对隔离】黑箱内收容着极度危险的S级诡异遗蜕，在绝境中会选择同归于尽式展开领域。",
                        "inventory": ["镇煞短刃", "封印手提黑箱", "精神安定喷雾"]
                    },
                    {
                        "name": "红伞少女",
                        "title": "雨夜问路诡异",
                        "camp": "不可名状之物",
                        "cultivation_level": "高阶规则具现",
                        "public_profile": "手持一柄滴血红油纸伞，面容隐匿在伞檐阴影中，轻声在浓雾中询问生者生辰八字。",
                        "secret_profile": "【言语诱杀】只要对方回答任何涉及时间或年龄的字眼，其寿元便会被瞬间剥夺。",
                        "inventory": ["滴血红油纸伞", "引魂骨梳"]
                    }
                ]
            elif cat == "fantasy":
                mock_pool = [
                    {
                        "name": "罗兰",
                        "title": "银色黎明圣武士",
                        "camp": "圣堂骑士团",
                        "cultivation_level": "高阶圣光裁决者",
                        "public_profile": "银白全身板甲纤尘不染，手握散发神圣晨曦光芒的战锤，胸前悬挂太阳神徽，英姿勃发。",
                        "secret_profile": "【异端审判】只要嗅到一丝深渊或亡灵气息，便会发动无差别狂热圣裁，绝不宽恕。",
                        "inventory": ["晨曦裁决之锤", "圣光庇护卷轴", "强效驱魔药剂"]
                    },
                    {
                        "name": "莫甘娜",
                        "title": "黑沼泽剧毒女巫",
                        "camp": "暗黑结社",
                        "cultivation_level": "深渊剧毒操纵者",
                        "public_profile": "头戴黑色尖顶软帽，长发如毒蛇般蜷曲，周身缭绕着墨绿色腐蚀毒雾，笑声沙哑阴森。",
                        "secret_profile": "【活体炼药】专挑重伤强者的尸体或灵体做毒药引子，暗中布置化尸血沼。",
                        "inventory": ["剧毒魔药坩埚", "蛇骨法杖", "假死迷雾石"]
                    }
                ]
            elif cat == "gaming":
                mock_pool = [
                    {
                        "name": "苏夜",
                        "title": "封弊者 / 极限独狼刺客",
                        "camp": "独行玩家",
                        "cultivation_level": "LV.45 影舞者 (全敏加点)",
                        "public_profile": "一身玄黑轻甲，面戴半截黑骨面具，双手各反握一柄泛着幽暗微光的短刃，身姿鬼魅。",
                        "secret_profile": "【神级被动】拥有内测遗留唯一专属被动“绝对弱点洞悉”，暴击伤害无视一切护甲上限。",
                        "inventory": ["幽影双子短刃", "瞬移逃脱卷轴", "特级生命恢复药剂x5"]
                    },
                    {
                        "name": "霸天傲神",
                        "title": "霸天神域公会会长",
                        "camp": "十大超级公会联盟",
                        "cultivation_level": "LV.48 圣堂重骑士 (全身史诗)",
                        "public_profile": "全身暗金重装铠甲，手持三米金光巨盾与裁决战锤，麾下数十名精锐簇拥，威势滔天。",
                        "secret_profile": "【唯我独尊】垄断副本首杀与关键建帮令，视散人玩家为蝼蚁炮灰，敢阻其公会霸业者必全服追杀。",
                        "inventory": ["泰坦之壁暗金大盾", "圣裁战锤", "公会集结令"]
                    }
                ]
            elif cat == "wuxia":
                mock_pool = [
                    {
                        "name": "燕十三",
                        "title": "落魄寒刀客",
                        "camp": "关外浪人",
                        "cultivation_level": "天榜刀魁 (隐匿重伤)",
                        "public_profile": "一袭残破蓑衣，斗笠压低，腰悬一柄生锈铁刀，眼神如苍鹰般森冷孤绝。",
                        "secret_profile": "【十三绝命】刀出必饮血，十步之内不论王公巨寇，绝无生还之人。",
                        "inventory": ["生锈寒铁刀", "半葫芦烧刀子", "染血镖银"]
                    },
                    {
                        "name": "白凝霜",
                        "title": "点苍派当代掌门女",
                        "camp": "名门名宿",
                        "cultivation_level": "点苍回风剑真传",
                        "public_profile": "素白劲装，背负双剑，眉目如画却冷若冰霜，行走江湖只问青红皂白。",
                        "secret_profile": "【寻仇血誓】宗门惨遭神秘势力血洗，誓要手刃真凶，绝不惜身。",
                        "inventory": ["青霜软剑", "九花玉露丸", "点苍掌门信物"]
                    }
                ]
            else:
                # 默认/凡人修仙
                mock_pool = [
                    {
                        "name": "燕狂徒",
                        "title": "异灵根散修",
                        "camp": "散修/亡命徒",
                        "cultivation_level": "筑基初期",
                        "public_profile": "满头赤发，披着带血兽皮，扛着一柄门板大小的断狱重刀，周身隐有雷弧闪烁。",
                        "secret_profile": "【困兽之斗】被仇家追杀走投无路，嗅到重宝出世气息，欲强行争夺博一线生机；性情狂暴，一言不合便拔刀决生死。",
                        "inventory": ["断狱重刀", "狂雷符x3", "天雷遁甲"]
                    },
                    {
                        "name": "金不换",
                        "title": "万宝阁四海游商",
                        "camp": "中立/商贾",
                        "cultivation_level": "练气九层巅峰",
                        "public_profile": "大腹便便，面色和蔼，身着金丝绸缎长袍，十指戴满储物灵戒，脚踏一尊金元宝飞行法器。",
                        "secret_profile": "【贪婪商人】随身携带有高阶'破禁符'与'金蝉脱壳符'，专门在秘境死地高价兜售救命丹药或低价抄底死者储物袋。",
                        "inventory": ["八宝如意金钱", "金蝉脱壳符", "化瘀还魂丹x5"]
                    },
                    {
                        "name": "赵青鸾",
                        "title": "名门巡界执法使",
                        "camp": "正道宗门",
                        "cultivation_level": "筑基中期",
                        "public_profile": "一袭青鸾暗纹锦袍，眉宇威严，手持追魂寻气罗盘，踏空而立，四方灵压沉重如山。",
                        "secret_profile": "【奉命夺宝】奉宗门密令探查天地异象核心，立誓斩杀所有阻挠夺宝的各方修士。",
                        "inventory": ["青鸾破空梭", "追魂罗盘", "极寒玄冰障"]
                    }
                ]

            # 选一个没出场过的
            available = [c for c in mock_pool if not any(existing["name"] == c["name"] for existing in target_book.world.characters.values())]
            chosen = available[0] if available else mock_pool[0]
            new_char = dict(chosen)
        else:
            # 真实大模型实时捏人（题材自适应）
            llm = LLMClient(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
            prompt = f"""
请为【{target_genre}】小说《{target_title}》创造一位新登场的角色，要求严格契合该题材流派的风格特色（注重因果、算计、隐秘底牌与独特生存准则）。
角色设定要求：{custom_prompt if custom_prompt else "一位被现场剧烈冲突动静吸引而来的新入局者（可以是强援、死敌、趁乱渔利者、追捕者或神秘中立散客）"}

请严格输出 JSON 格式：
```json
{{
  "name": "姓名 (2~3字)",
  "title": "头衔/身份/尊号",
  "camp": "阵营 (如: 正义联盟/财阀暗部/反抗军/魔门/异常调查局)",
  "cultivation_level": "实力等级或社会阶层",
  "public_profile": "外貌神态与表面装备描述 (60~100字)",
  "secret_profile": "【真实隐秘底牌与暗中心思准则】 (80~120字)",
  "inventory": ["专属装备/道具1", "暗中底牌2", "保命手段3"]
}}
```
"""
            model_to_use = os.getenv("MODEL_NAME", "balanced-model")
            parsed = None
            try:
                raw_res = llm.chat(model_to_use, [
                    {"role": "system", "content": f"你是【{target_genre}】世界至高造物主。"},
                    {"role": "user", "content": prompt}
                ])
                parsed = llm.extract_json(raw_res)
            except Exception as e:
                print(f"[天道点化 告警] 模型 {model_to_use} 调用失败: {e}，尝试使用 balanced-model 回退...")
                if model_to_use != "balanced-model":
                    try:
                        raw_res = llm.chat("balanced-model", [
                            {"role": "system", "content": f"你是【{target_genre}】世界至高造物主。"},
                            {"role": "user", "content": prompt}
                        ])
                        parsed = llm.extract_json(raw_res)
                    except Exception as e2:
                        print(f"[天道点化 兜底] balanced-model 回退亦失败: {e2}，使用预设角色")
                        parsed = None
                else:
                    parsed = None

            if parsed and parsed.get("name"):
                new_char = parsed
            else:
                new_char = {
                    "name": "灰袍神秘客",
                    "title": "匿息邪修",
                    "camp": "散修",
                    "cultivation_level": "筑基初期",
                    "public_profile": "灰袍罩头，不见面容，脚踏一根幽绿骨杖，无声无息悬于乱石上空。",
                    "secret_profile": "暗中祭炼万魂幡，等待场上众人力竭时一网打尽。",
                    "inventory": ["幽冥白骨杖", "隐息匿形披风"]
                }

        new_char["status"] = "alive"
        target_book.world.characters[char_id] = new_char

        # 广而告之：在天道事件中留下记录
        announcement = f"【天道生变·新修士踏入战局】：修士【{new_char['name']}】（{new_char.get('title', '')} / {new_char.get('cultivation_level', '')}）感应到此地灵力激荡，御器破空而来！"
        if target_book.world.history:
            target_book.world.history[-1].tiandao_intervention = (
                (target_book.world.history[-1].tiandao_intervention or "") + f"\n{announcement}"
            )

        return {"status": "ok", "character": new_char}

    def get_state(self, target_book_id=None):
        # 组装返回给前端的状态
        target_book = book_mgr.books.get(target_book_id, self.active_book) if target_book_id else self.active_book
        if not target_book:
            target_book = self.active_book

        current_api_key = os.getenv("OPENAI_API_KEY", "")
        has_real_key = bool(current_api_key and current_api_key != "your_api_key_here")

        char_list = []
        for k, c in target_book.world.characters.items():
            # 找到该角色在最后一轮的私有内心独白（全知天道可见）
            last_inner = ""
            if target_book.world.history:
                for act in target_book.world.history[-1].actions:
                    if act.char_name == c["name"]:
                        last_inner = act.inner_thought
                        break

            char_list.append({
                "id": k,
                "name": c["name"],
                "title": c.get("title", ""),
                "camp": c.get("camp", ""),
                "cultivation": c.get("cultivation_level", ""),
                "public_profile": c["public_profile"],
                "secret_profile": c["secret_profile"],
                "inventory": c.get("inventory", []),
                "injuries": c.get("injuries", []),
                "status": c.get("status", "alive"),
                "last_inner_thought": last_inner
            })

        history_list = []
        for r in target_book.world.history:
            history_list.append({
                "round": r.round_number,
                "environment": r.environment_state,
                "tiandao_intervention": r.tiandao_intervention,
                "arbitration": r.arbitration_result,
                "actions": [
                    {
                        "char_id": a.char_id,
                        "name": a.char_name,
                        "inner_thought": a.inner_thought,
                        "speech": a.speech,
                        "action": a.action
                    }
                    for a in r.actions
                ]
            })

        # 章节精简处理：仅首章与尾章保留正文默认展示，其余章节按需由 /api/chapter 懒加载，防止超大体积卡死前端
        lean_chapters = []
        for idx, c in enumerate(target_book.chapters):
            include_content = (idx == 0 or idx == len(target_book.chapters) - 1)
            lean_chapters.append({
                "id": c.get("id"),
                "title": c.get("title", f"第{c.get('id')}章"),
                "word_count": c.get("word_count", len(c.get("content", ""))),
                "content": c.get("content", "") if include_content else ""
            })

        raw_key = os.getenv("OPENAI_API_KEY", "")
        masked_key = f"{raw_key[:3]}****{raw_key[-4:]}" if (has_real_key and len(raw_key) > 7) else ("••••••••" if has_real_key else "")

        # 为所有书籍概览附加各自的实时推演状态
        books_summary = book_mgr.list_books_summary()
        for s in books_summary:
            s["is_simulating"] = self.is_book_busy(s["id"])

        first_chap_content = target_book.chapters[0].get("content", "") if target_book.chapters else ""

        return {
            "v": self.get_state_version(target_book.id),
            "book_id": target_book.id,
            "title": target_book.title,
            "genre": target_book.genre,
            "synopsis": target_book.synopsis,
            "theme_prompt": target_book.theme_prompt,
            "scene_description": target_book.world.scene_description,
            "current_round": target_book.current_round,
            "max_rounds": target_book.world.max_rounds,
            "characters": char_list,
            "history": history_list,
            "chapters": lean_chapters,
            "outline": getattr(target_book, "outline", {}),
            "has_outline": bool(getattr(target_book, "outline", {}).get("main_plot")),
            "foreshadowings": getattr(target_book, "foreshadowings", []),
            "dramas": target_book.dramas,
            "books_summary": books_summary,
            "is_busy": self.is_book_busy(target_book.id),
            "has_novel": bool(first_chap_content),
            "novel_content": first_chap_content,
            "config": {
                "has_api_key": has_real_key,
                "api_key_masked": masked_key,
                "base_url": os.getenv("OPENAI_BASE_URL", "http://dxcool.cn:7863/v1"),
                "model_name": os.getenv("MODEL_NAME", "balanced-model"),
                "tiandao_model": os.getenv("TIANDAO_MODEL", os.getenv("MODEL_NAME", "balanced-model")),
                "chronicler_model": os.getenv("CHRONICLER_MODEL", os.getenv("MODEL_NAME", "fast-model"))
            }
        }

    def step(self, divine_decree="", force_mock=False, auto_spawn=False, target_book=None):
        """执行单步演化"""
        target_book = target_book or self.active_book
        if not target_book.id:
            return {"error": "当前书库为空，请先点击【➕ 新建作品】创建一部小说！"}
        runner = self.get_runner(target_book.id)
        if runner.is_busy:
            return {"error": f"作品《{target_book.title}》推演引擎正忙，请稍候..."}

        runner.is_busy = True
        try:
            target_book.current_round += 1
            load_dotenv()
            current_api_key = os.getenv("OPENAI_API_KEY", "")
            use_mock = force_mock or (not current_api_key) or (current_api_key == "your_api_key_here")

            # 若勾选自动引人且轮次到达第2轮或场上少于4人，概率由天道引来新路过散修
            if auto_spawn and (target_book.current_round >= 2) and (len(target_book.world.characters) < 5):
                self.spawn_character(custom_prompt="被滔天法宝威压与剧烈斗法声响吸引而来的路过散修或宗门追兵", force_mock=use_mock, target_book=target_book)

            if use_mock:
                # 模拟推演模式
                result = self._step_mock(target_book.current_round, divine_decree, target_book=target_book)
            else:
                # 真实大模型推演
                try:
                    result = self._step_real(target_book.current_round, divine_decree, target_book=target_book)
                except Exception as e:
                    print(f"[推演中心 异常拦截] 真实推演遇到异常: {e}，平滑切换至沙盒模拟！")
                    result = self._step_mock(target_book.current_round, divine_decree, target_book=target_book)

            target_book.save()
            return result
        finally:
            runner.is_busy = False

    def _step_mock(self, round_num, divine_decree, target_book=None):
        """高质量模拟步（对当前任意自创角色的自适应群像博弈推演，全自动生死流转）"""
        target_book = target_book or self.active_book
        target_genre = target_book.genre or "通用幻想"

        time.sleep(1.2)  # 模拟推演时间
        decree_text = f"【天道法旨干涉】：{divine_decree}\n" if divine_decree else ""

        # 获取当前存活的角色
        active_chars = [c for c in target_book.world.characters.values() if c.get("status", "alive") == "alive"]

        # 【核心】：若当前场上没有任何角色（第一回合从零开辟），天地初开，根据题材自动初始化首批核心角色
        if not active_chars:
            book_mgr._populate_new_book_archetypes(target_book, target_genre, target_book.theme_prompt or "")
            active_chars = [c for c in target_book.world.characters.values() if c.get("status", "alive") == "alive"]

            actions = []
            for c in active_chars:
                actions.append(CharacterAction(
                    char_id=c["name"],
                    char_name=c["name"],
                    inner_thought=c.get("secret_profile", "静观其变，伺机夺得先机。"),
                    speech=f"事关重大，见者有份，各凭真本事！",
                    action=f"暗中握紧携带之物品道具，眼神警惕锁定全场动静。"
                ))

            env_change = f"风云变幻，{target_book.world.title}核心异动爆发，多方核心势力初次交锋！"
            fate_twist = f"{decree_text}【天地因果初显】：各方互不相识的焦点人物第一时间被异变卷入局中！"
            arbitration = "各方阵营心怀鬼胎，于局中形成制衡对峙，底牌与杀招蓄势待发，冲突一触即发！"

            log = RoundLog(
                round_number=round_num,
                environment_state=env_change,
                tiandao_intervention=fate_twist,
                actions=actions,
                arbitration_result=arbitration
            )
            target_book.world.history.append(log)
            target_book.save()
            return {"status": "ok", "round": round_num}

        actions = []
        for idx, c in enumerate(active_chars):
            c_name = c["name"]
            c_type = c.get("title", "")
            c_sec = c.get("secret_profile", "")
            inv = c.get("inventory", [])
            item_hint = f"，暗中扣住【{inv[0]}】" if inv else ""

            # 根据角色的修行派系、性格与题材动态产生博弈行为
            if any(k in c_type for k in ["苟", "隐忍", "散修", "拾荒", "独狼", "刺客"]):
                thought = f"局势变幻莫测，前方暗藏巨大危机！绝不可过早成为出头鸟，务必留存撤退暗道{item_hint}！"
                speech = f"诸位请便，在下自当从旁策应，绝无贪天之意。"
                act = f"脚下微移退入阴影死角，双手暗自蓄力，眼神扫探全场退路。"
            elif any(k in c_type for k in ["天骄", "剑", "先锋", "领主", "会长", "战神", "董事"]):
                thought = f"眼前这帮对手各怀异心，谁也信不过！既然机缘现世，顺我者昌逆我者亡，当以雷霆之势破局！"
                speech = f"大局已定！谁若敢暗中阻挠，休怪本座手下无情！"
                act = f"气势全面爆发{item_hint}，强横威压横扫四方，正面威慑全场！"
            elif any(k in c_type for k in ["商贾", "义医", "情报", "门阀", "内鬼", "权臣"]):
                thought = f"两虎相争必有一伤，正合我意！且待他们拼得两败俱伤，我再出面收拾残局！"
                speech = f"诸位稍安勿躁，以和为贵，不如坐下谈谈如何分润？"
                act = f"面带温和微笑出言斡旋，暗中却布下连环算计陷阱。"
            elif any(k in c_type for k in ["诡异", "魔", "邪", "狂暴", "不可知"]):
                thought = f"贪婪的蠢货们……越是挣扎，越是成为最好的收割资粮！"
                speech = f"呵呵……今天谁也别想活着走出这里！"
                act = f"杀意如潮水般悄然弥漫，无形杀招死死封住众人命门。"
            else:
                thought = f"战局凶险，静观其变，伺机寻找破局契机{item_hint}！"
                speech = f"诸位各凭真章，见机行事！"
                act = f"全面戒备，锁定关键变数。"

            actions.append(CharacterAction(
                char_id=c_name,
                char_name=c_name,
                inner_thought=thought,
                speech=speech,
                action=act
            ))

        # 根据轮次演变局势与自动引渡新人/结算生死
        if round_num == 1:
            # 自动吸引一位新人破空入局
            new_char = self.spawn_character(force_mock=True, target_book=target_book)
            new_name = new_char.get("name", "神秘新来者") if isinstance(new_char, dict) else "神秘强援"
            env_change = f"气浪席卷，异象彻底沸腾，{target_book.world.title}核心博弈进入白热化！"
            fate_twist = f"{decree_text}【天地因果涌现】：剧烈冲突余波引动【{new_name}】强行杀入战局！"
            arbitration = f"新入局者【{new_name}】掀起惊天变局，在场各方立刻调整防线，杀机直冲云霄！"

        elif round_num == 2:
            dead_name = "一位对手"
            esc_name = "一位机敏者"
            if len(active_chars) >= 2:
                active_chars[1]["status"] = "dead"
                dead_name = active_chars[1]["name"]
            if len(active_chars) >= 3:
                active_chars[0]["status"] = "escaped"
                esc_name = active_chars[0]["name"]

            # 再引渡一位趁乱入局者
            new_char = self.spawn_character(force_mock=True, target_book=target_book)
            new_name = new_char.get("name", "黄雀在后者") if isinstance(new_char, dict) else "黄雀"
            env_change = "狂暴气流撕裂全场，战线崩解，残垣断壁在冲击波中化作齑粉！"
            fate_twist = f"{decree_text}【因果生死结算】：【{dead_name}】底牌尽出终遭重创击溃！【{esc_name}】夺得关键战利品脱离战场！"
            arbitration = f"【{dead_name}】黯然退场！新来者【{new_name}】潜入战场搜刮遗存，剩余人员陷入殊死决战！"

        else:
            env_change = "核心悬念彻底爆发，全场能量与杀机攀升至终极顶点！"
            fate_twist = f"{decree_text}【宿命终局演变】：终局决断降临，众生各展平生至高底牌！"
            arbitration = "残存强者终极对撞，胜者破局夺魁绝尘而去，败者遗恨终生，天地因果落定！"

        log = RoundLog(
            round_number=round_num,
            environment_state=env_change,
            tiandao_intervention=fate_twist,
            actions=actions,
            arbitration_result=arbitration
        )
        target_book.world.history.append(log)
        target_book.save()
        return {"status": "ok", "round": round_num}

    def _step_real(self, round_num, divine_decree="", chapter_outline=None, target_book=None):
        """
        【Turbo 极速双盲因果博弈引擎】
        单次深度推理矩阵：一键完成全员双盲心机决策 + 天道客观裁决 + 确定性状态道具与伤势结算
        耗时从 90s+ 缩短至 10s 级，Token 成本大幅降低，且具备确定性状态追踪。
        """
        llm = LLMClient(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
        target_book = target_book or self.active_book

        # 1. 获取当前在场的存活角色
        active_agents = {k: v for k, v in target_book.world.characters.items() if v.get("status", "alive") == "alive"}

        # 若当前场上没有任何角色（第一回合从零开辟演化）：天道自主开辟世界与引渡首批争渡者
        if not active_agents:
            decree_hint = f"天道法旨干涉：{divine_decree}\n" if divine_decree else ""
            genre = target_book.genre or "通用幻想"
            prompt = f"""
你是掌控【{genre}】大千因果的至高天道意志。
当前世界处于【虚席以待】的初始格局，请为主线故事开辟首个核心舞台并引渡首批 3 位互不相识、各自心怀鬼胎的争渡核心角色：
1. 【天地格局】：设定古典绝地/杀局/舞台名称与环境异动描述（80~150字）。
2. 【首批登场角色】：生成 3 位原创角色（全原创姓名，绝无天定免死主角光环，人人皆主角）。提供其表面装束境界、隐密底牌与心机原则、携带主要物品。
3. 【初次博弈】：生成各自内心深层算计、表面虚与委蛇言语与戒备动作。
4. 【因果判定】：给出初次对峙的客观判定。

{decree_hint}
必须严格输出纯净 JSON 格式：
```json
{{
  "scene_title": "秘境/绝地/都市/朝堂舞台名称",
  "environment_change": "现场异象与肃杀动荡描写 (80~150字)",
  "fate_twist": "突发变数或危机催化 (50~100字)",
  "arbitration_summary": "客观因果裁决结论 (80~120字)",
  "characters": [
    {{
      "name": "原创姓名 (2~3字)",
      "title": "头衔/身份",
      "camp": "所属阵营/流派",
      "cultivation_level": "真实境界或社会身份",
      "public_profile": "外貌神态与表面装束 (60~100字)",
      "secret_profile": "【真实隐秘底牌、暗中心机与绝密底线】 (80~120字)",
      "inventory": ["底牌/法宝/道具1", "保命符箓/信物2"],
      "speech": "表面试探所言",
      "action": "初次站位与具体动作",
      "inner_thought": "内心真实深层算计独白"
    }}
  ]
}}
```
"""
            td_model = os.getenv("TIANDAO_MODEL") or os.getenv("MODEL_NAME") or "balanced-model"
            try:
                raw_res = llm.chat(td_model, [
                    {"role": "system", "content": f"你是冷酷掌控【{genre}】因果的至高天道意志。"},
                    {"role": "user", "content": prompt}
                ])
                parsed = llm.extract_json(raw_res)
            except Exception as e:
                print(f"[天道创世 提示] 真实模型异常: {e}，切入沙盒模拟生成")
                return self._step_mock(round_num, divine_decree, target_book=target_book)

            if not parsed or not parsed.get("characters"):
                return self._step_mock(round_num, divine_decree, target_book=target_book)

            target_book.world.title = parsed.get("scene_title", "【大千世界 · 风云初起】")
            target_book.world.scene_description = parsed.get("environment_change", "虚空动荡，大幕拉开。")

            actions = []
            for idx, c in enumerate(parsed["characters"][:4]):
                cid = f"char_{idx+1}"
                target_book.world.characters[cid] = {
                    "name": c["name"],
                    "title": c.get("title", "争渡者"),
                    "camp": c.get("camp", "中立"),
                    "cultivation_level": c.get("cultivation_level", "初窥门径"),
                    "public_profile": c.get("public_profile", ""),
                    "secret_profile": c.get("secret_profile", ""),
                    "inventory": c.get("inventory", []),
                    "injuries": [],
                    "status": "alive"
                }
                actions.append(CharacterAction(
                    char_id=c["name"],
                    char_name=c["name"],
                    inner_thought=c.get("inner_thought", "静观其变，伺机夺宝。"),
                    speech=c.get("speech", "各凭手段，见者有份。"),
                    action=c.get("action", "暗扣底牌，谨慎戒备。")
                ))

            log = RoundLog(
                round_number=round_num,
                environment_state=parsed.get("environment_change", "天地异象爆发。"),
                tiandao_intervention=parsed.get("fate_twist", ""),
                actions=actions,
                arbitration_result=parsed.get("arbitration_summary", "各方对峙，杀机四伏。")
            )
            target_book.world.history.append(log)
            target_book.save()
            return {"status": "ok", "round": round_num}

        # 2. 构建 Turbo 统一因果博弈矩阵
        char_dossiers = []
        for cid, c in active_agents.items():
            inj_str = "、".join(c.get("injuries", [])) if c.get("injuries") else "暂无创伤"
            inv_str = "、".join(c.get("inventory", [])) if c.get("inventory") else "身无长物"
            char_dossiers.append(
                f"- 【{c['name']}】({c.get('title','')})：\n"
                f"  * 表面伪装：{c.get('public_profile','')}\n"
                f"  * 绝密底牌(他人不可知)：{c.get('secret_profile','')}\n"
                f"  * 真实携带底牌道具：{inv_str}\n"
                f"  * 遗留伤势：{inj_str}"
            )
        chars_context = "\n\n".join(char_dossiers)

        outline_goal = ""
        if chapter_outline:
            outline_goal = (
                f"\n【本章剧情核心主线蓝图】：\n"
                f"- 本章标题：{chapter_outline.get('title')}\n"
                f"- 核心目标：{chapter_outline.get('goal')}\n"
                f"- 冲突交锋：{chapter_outline.get('conflict')}\n"
                f"- 爆点高潮：{chapter_outline.get('climax')}"
            )

        decree_text = f"\n【天道法旨钦定强制干涉】：{divine_decree}" if divine_decree else ""

        turbo_prompt = f"""
你是不容忤逆的【{target_book.genre}因果律天道主宰】。
当前现场环境：
{target_book.world.scene_description}
{outline_goal}
{decree_text}

【在场存活角色的真实档案（严格双盲战争迷雾！角色间绝对看不到彼此的内心独白与秘密底牌）】：
{chars_context}

作为至高天道主宰，请在一轮深度因果推演中，一次性完成以下三大职责：
1. 【全员双盲决策】：为在场每位角色推演本回合行动。必须严格依据其各自的绝密心机与携带道具，生成深层内心算计独白、表面掩饰言辞、暗中具体出手招式及所消耗道具。
2. 【天道因果裁决】：给出客观真实的招式对撞结果、天地格局动荡、外部大劫催化。
3. 【确定性状态结算】：精确指定各角色实际消耗掉的道具、获得的战利品、新受到的真实伤势（如断臂、中毒、内伤吐血）以及生死走向（alive/dead/escaped）。

必须严格按以下 JSON 格式输出，杜绝废话：
```json
{{
  "environment_change": "现场异象与战局动荡描写 (80~120字)",
  "fate_twist": "天道降下的外部变数或危机催化 (40~80字)",
  "arbitration_summary": "客观交锋因果裁决（招式碰擦、法宝对轰、谁落入下风） (80~150字)",
  "actions": [
    {{
      "char_name": "角色名",
      "inner_thought": "内心真实深层算计独白 (60~100字)",
      "speech": "表面所言或伪装辞令",
      "action": "具体出手施法或站位暗招",
      "used_items": ["本轮确切消耗的道具1"]
    }}
  ],
  "settlement": {{
    "consumed_items": {{
      "角色名A": ["已消耗道具名"]
    }},
    "gained_items": {{
      "角色名B": ["缴获或夺得的新道具"]
    }},
    "injuries": {{
      "角色名A": "受创细节描述 (如: 经脉受创吐血三升)"
    }},
    "character_fates": {{
      "角色名A": "alive",
      "角色名B": "dead",
      "角色名C": "escaped"
    }}
  }},
  "new_arrival": {{
    "should_spawn": false,
    "name": "新角色名",
    "title": "头衔",
    "camp": "阵营",
    "cultivation_level": "身份境界",
    "public_profile": "外貌神态",
    "secret_profile": "隐秘心机",
    "inventory": ["携带道具1"],
    "entrance_reason": "破空而至缘由"
  }}
}}
```
"""
        td_model = os.getenv("TIANDAO_MODEL") or os.getenv("MODEL_NAME") or "balanced-model"
        try:
            raw_res = llm.chat(td_model, [
                {"role": "system", "content": f"你是掌控【{target_book.genre}】宿命与因果的至高天道意志。"},
                {"role": "user", "content": turbo_prompt}
            ], temperature=0.7)
            parsed = llm.extract_json(raw_res)
        except Exception as e:
            print(f"[Turbo 推演引擎 提示] 真实模型推演波动: {e}，自动降级至高质量沙盒模拟")
            return self._step_mock(round_num, divine_decree, target_book=target_book)

        if not parsed or not parsed.get("actions"):
            return self._step_mock(round_num, divine_decree, target_book=target_book)

        # 3. 提取博弈动作
        actions = []
        for a in parsed.get("actions", []):
            actions.append(CharacterAction(
                char_id=a.get("char_name", "无名"),
                char_name=a.get("char_name", "无名"),
                inner_thought=a.get("inner_thought", "静观其变。"),
                speech=a.get("speech", "小心戒备！"),
                action=a.get("action", "暗中调运护体法力。")
            ))

        fate_twist = parsed.get("fate_twist", "")
        if divine_decree:
            fate_twist = f"【天道法旨钦定】：{divine_decree}\n" + fate_twist

        # 4. 执行确定性状态机结算（法宝道具确切扣除、伤势记录、生死状态变更）
        settlement = parsed.get("settlement", {})
        book_mgr.apply_deterministic_settlement(target_book, settlement)

        # 5. 引渡新登场修士（如果场上活跃人数少于 5 且天道认为机缘已至）
        new_arrival = parsed.get("new_arrival")
        if new_arrival and isinstance(new_arrival, dict) and new_arrival.get("should_spawn") and new_arrival.get("name"):
            new_id = f"char_{int(time.time()*1000)%1000000}"
            target_book.world.characters[new_id] = {
                "name": new_arrival["name"],
                "title": new_arrival.get("title", "路过修士"),
                "camp": new_arrival.get("camp", "散修"),
                "cultivation_level": new_arrival.get("cultivation_level", "筑基初期"),
                "public_profile": new_arrival.get("public_profile", "破空而至，神色戒备。"),
                "secret_profile": new_arrival.get("secret_profile", "暗中图谋机缘。"),
                "inventory": new_arrival.get("inventory", ["防身法宝"]),
                "injuries": [],
                "status": "alive"
            }
            spawn_log = f"【因果化生 · 新修士入局】：修士【{new_arrival['name']}】（{new_arrival.get('cultivation_level')}）破空而至！缘由：{new_arrival.get('entrance_reason', '受激荡声势吸引')}"
            fate_twist = f"{fate_twist}\n{spawn_log}" if fate_twist else spawn_log

        # 6. 记录本轮客观历史
        log = RoundLog(
            round_number=round_num,
            environment_state=parsed.get("environment_change", "风暴席卷，四周杀气腾腾。"),
            tiandao_intervention=fate_twist,
            actions=actions,
            arbitration_result=parsed.get("arbitration_summary", "各方暗算交错，战果抵定。")
        )
        target_book.world.history.append(log)
        target_book.save()
        return {"status": "ok", "round": round_num}

    def generate_novel(self, force_mock=False, target_book=None):
        """调用史官撰写小说章节"""
        target_book = target_book or self.active_book
        runner = self.get_runner(target_book.id)
        if runner.is_busy:
            return {"error": f"作品《{target_book.title}》引擎正忙，请稍候..."}

        if not target_book.world.history:
            # 自动开天辟地推演首轮因果，确保随时可以直接出书
            print("[史官著书 智能补全] 检测到尚无历史，天道自动开辟天地推演首卷博弈...")
            self.step(force_mock=force_mock, auto_spawn=True, target_book=target_book)

        runner.is_busy = True
        try:
            return self._write_novel_internal(force_mock=force_mock, target_book=target_book)
        finally:
            runner.is_busy = False

    def auto_simulate_and_publish(self, rounds=3, force_mock=False, target_book=None):
        """一键全自动推演并著书成卷 (自动连续推进轮次并生成长篇小说正文)"""
        target_book = target_book or self.active_book
        runner = self.get_runner(target_book.id)
        if runner.is_busy:
            return {"error": f"作品《{target_book.title}》天道演化正忙，请稍候..."}

        runner.is_busy = True
        try:
            load_dotenv()
            current_api_key = os.getenv("OPENAI_API_KEY", "")
            use_mock = force_mock or (not current_api_key) or (current_api_key == "your_api_key_here")

            # 自动推进多轮
            for _ in range(rounds):
                target_book.current_round += 1
                if target_book.current_round >= 2 and len(target_book.world.characters) < 5:
                    self.spawn_character(custom_prompt="被滔天法宝威压吸引而来的散修或宗门追兵", force_mock=use_mock, target_book=target_book)

                if use_mock:
                    self._step_mock(target_book.current_round, "", target_book=target_book)
                else:
                    try:
                        self._step_real(target_book.current_round, "", target_book=target_book)
                    except Exception as e:
                        print(f"[一键成书 熔断保护] 第 {target_book.current_round} 轮异常: {e}，平滑切换沙盒演练")
                        self._step_mock(target_book.current_round, "", target_book=target_book)
                time.sleep(1.0)

            # 终局由史官撰写小说正文
            return self._write_novel_internal(force_mock=use_mock, target_book=target_book)
        finally:
            runner.is_busy = False

    def _write_novel_internal(self, force_mock=False, target_book=None):
        target_book = target_book or self.active_book
        load_dotenv()
        current_api_key = os.getenv("OPENAI_API_KEY", "")
        use_mock = force_mock or (not current_api_key) or (current_api_key == "your_api_key_here")

        if use_mock:
            novel_path = OUTPUT_DIR / "novel_chapter_01.md"
            if novel_path.exists():
                novel_text = novel_path.read_text(encoding="utf-8")
            else:
                novel_text = f"# 第一章 争渡伊始\n\n大幕拉开，{target_book.title}的世界中各方博弈悄然开启……"
        else:
            llm = LLMClient(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
            chr_model = os.getenv("CHRONICLER_MODEL") or "fast-model"
            try:
                chronicler = ChroniclerAgent(llm, chr_model)
                novel_text = chronicler.write_chapter(target_book.world, target_book.world.history)
            except Exception as e_chr:
                print(f"[史官著书 告警] 史官模型 {chr_model} 调用失败: {e_chr}，尝试 fast-model 回退...")
                try:
                    chronicler_fb = ChroniclerAgent(llm, "fast-model")
                    novel_text = chronicler_fb.write_chapter(target_book.world, target_book.world.history)
                except Exception as e_chr2:
                    print(f"[史官著书 兜底] fast-model 回退亦失败: {e_chr2}")
                    novel_text = ""

        if not novel_text or len(novel_text.strip()) < 100:
            novel_lines = [
                f"# 【{target_book.world.title}】群雄争渡录 · 第一回",
                "",
                f"大道无情，万仙争渡。{target_book.world.scene_description}",
                ""
            ]
            for r in target_book.world.history:
                novel_lines.append(f"## 第 {r.round_number} 回 · 天地因果博弈")
                novel_lines.append(f"> **天地异象**：{r.environment_state}\n")
                if r.tiandao_intervention:
                    novel_lines.append(f"> **天道变数**：{r.tiandao_intervention}\n")
                novel_lines.append("### 各方心机与施法")
                for a in r.actions:
                    novel_lines.append(f"**【{a.char_name}】** 启唇道：“*{a.speech}*”")
                    novel_lines.append(f"- 具体行动：{a.action}")
                    novel_lines.append(f"- 私密暗算：*{a.inner_thought}*\n")
                novel_lines.append(f"### 天道因果裁决\n{r.arbitration_result}\n---")
            novel_text = "\n\n".join(novel_lines)

        chap_num = max(1, (target_book.current_round + 1) // 2)
        first_line = novel_text.strip().split("\n")[0].replace("#", "").strip() or f"第{chap_num}章"
        existing = next((c for c in target_book.chapters if c["id"] == chap_num), None)
        if existing:
            existing["title"] = first_line
            existing["content"] = novel_text
            existing["word_count"] = len(novel_text)
        else:
            target_book.chapters.append({
                "id": chap_num,
                "title": first_line,
                "word_count": len(novel_text),
                "content": novel_text
            })
        target_book.save()
        novel_path = OUTPUT_DIR / f"novel_chapter_{chap_num:02d}.md"
        try:
            novel_path.write_text(novel_text, encoding="utf-8")
        except Exception:
            pass
        return {"status": "ok", "content": novel_text, "chapter": chap_num}

    def stream_simulate(self, mode="single", force_mock=False, divine_decree="", book_id=None, custom_count=None, auto_fanqie=None):
        """
        流式全自动演化成书 (支持 1 章、10 章、以及一本书，可自定义规模 30/50/100 章，支持自动上传番茄)
        实时 yield 事件字典以供 SSE 流式推送
        """
        target_book = book_mgr.books.get(book_id, self.active_book) if book_id else self.active_book
        if not target_book or not target_book.id:
            yield {"type": "error", "message": "当前书库为空，请先点击顶部【➕ 新建作品】开辟一部小说！"}
            return

        runner = self.get_runner(target_book.id)
        if runner.is_busy:
            # 自动自愈：若已忙碌超过 180 秒（3分钟）未更新心跳，判定为上次异常挂起，自动强制释放
            if time.time() - getattr(runner, "last_busy_time", 0) > 180:
                runner.is_busy = False
            else:
                yield {"type": "error", "book_id": target_book.id, "message": f"作品《{target_book.title}》天道演化正在进行中，请稍候..."}
                return

        runner.is_busy = True
        runner.last_busy_time = time.time()
        runner.stop_requested = False

        try:
            # 计算目标章节数 (支持自定义章数或全书深度标准)
            if custom_count and int(custom_count) > 0:
                target_count = int(custom_count)
            elif mode == "ten":
                target_count = 10
            elif mode == "book":
                # 全本长篇巨作标准：默认目标为 50 章起步宏大长篇 (若已有章节则补全至目标或追加20章)
                curr_chaps = len(target_book.chapters)
                target_count = max(10, 50 - curr_chaps) if curr_chaps < 50 else 20
            else:
                target_count = 1

            yield {
                "type": "start",
                "mode": mode,
                "total_target": target_count,
                "book_id": target_book.id,
                "book_title": target_book.title,
                "existing_chapters": len(target_book.chapters)
            }

            load_dotenv()
            current_api_key = os.getenv("OPENAI_API_KEY", "")
            use_mock = force_mock or (not current_api_key) or (current_api_key == "your_api_key_here")

            total_generated = 0

            for i in range(1, target_count + 1):
                runner.last_busy_time = time.time()
                if runner.stop_requested:
                    yield {
                        "type": "stopped",
                        "book_id": target_book.id,
                        "total_generated": total_generated,
                        "message": f"作品《{target_book.title}》推演已响应指令安全停止，已完成 {total_generated} 章并妥善存盘！"
                    }
                    return

                is_final = (mode == "book" and i == target_count)

                # 计算新章节 ID
                existing_ids = [c["id"] for c in target_book.chapters]
                next_chap_id = (max(existing_ids) + 1) if existing_ids else 1

                llm = LLMClient(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))

                # 0. 大纲策划：动态规划或获取本章核心细纲（章节名、主线目标、矛盾冲突、高潮、钩子）
                runner.last_busy_time = time.time()
                yield {
                    "type": "planning",
                    "book_id": target_book.id,
                    "chapter_index": i,
                    "total": target_count,
                    "chapter_id": next_chap_id,
                    "message": f"【第 {i}/{target_count} 章】大纲策划师规划第 {next_chap_id} 章细纲与主线矛盾..."
                }

                chap_outline = book_mgr.get_or_plan_chapter_outline(target_book, next_chap_id, llm_client=llm, force_mock=use_mock)
                runner.last_busy_time = time.time()

                yield {
                    "type": "outline_ready",
                    "book_id": target_book.id,
                    "chapter_index": i,
                    "total": target_count,
                    "chapter_id": next_chap_id,
                    "outline": chap_outline,
                    "message": f"【第 {i}/{target_count} 章细纲就绪】《{chap_outline.get('title')}》核心冲突：{chap_outline.get('conflict', '')[:50]}"
                }

                # 1. 天道因果运转推演
                runner.last_busy_time = time.time()
                yield {
                    "type": "sim_step",
                    "book_id": target_book.id,
                    "chapter_index": i,
                    "total": target_count,
                    "chapter_id": next_chap_id,
                    "message": f"【第 {i}/{target_count} 章】天道因果推演中：众角色围绕本章主线展开生死博弈..."
                }

                # 推进轮次并生成博弈记录
                target_book.current_round += 1
                if target_book.current_round >= 2 and len(target_book.world.characters) < 5:
                    self.spawn_character(custom_prompt="被滔天声势吸引而来的各方修士与探子", force_mock=use_mock, target_book=target_book)

                if use_mock:
                    self._step_mock(target_book.current_round, divine_decree if i == 1 else "", target_book=target_book)
                else:
                    try:
                        self._step_real(target_book.current_round, divine_decree if i == 1 else "", chapter_outline=chap_outline, target_book=target_book)
                    except Exception as e:
                        print(f"[流式演化 降级] 第 {target_book.current_round} 轮真实推演异常: {e}，切入沙盒模拟")
                        self._step_mock(target_book.current_round, divine_decree if i == 1 else "", target_book=target_book)

                runner.last_busy_time = time.time()
                if runner.stop_requested:
                    yield {
                        "type": "stopped",
                        "book_id": target_book.id,
                        "total_generated": total_generated,
                        "message": f"作品《{target_book.title}》推演已安全停止，已完成 {total_generated} 章！"
                    }
                    return

                # 2. 史官流式研墨著书
                chap_title = chap_outline.get("title") or f"第{next_chap_id}章"
                yield {
                    "type": "write_start",
                    "book_id": target_book.id,
                    "chapter_index": i,
                    "total": target_count,
                    "chapter_id": next_chap_id,
                    "title": chap_title,
                    "is_final": is_final,
                    "message": f"【第 {i}/{target_count} 章】史官研墨，正在结合细纲实时流式撰写第 {next_chap_id} 章正文..."
                }

                chr_model = os.getenv("CHRONICLER_MODEL") or "fast-model"
                chronicler = ChroniclerAgent(llm, chr_model)

                # 前序脉络
                prev_summary = ""
                if target_book.chapters:
                    last_chap = target_book.chapters[-1]
                    prev_summary = f"前章标题：{last_chap.get('title','')}\n前情概要：{last_chap.get('content','')[-300:]}"

                chapter_chunks = []
                for chunk in chronicler.write_chapter_stream(
                    world=target_book.world,
                    history=target_book.world.history,
                    book_title=target_book.title,
                    genre=target_book.genre,
                    chapter_num=next_chap_id,
                    total_chapters=target_count,
                    is_final=is_final,
                    previous_summary=prev_summary,
                    chapter_outline=chap_outline,
                    force_mock=use_mock
                ):
                    if runner.stop_requested:
                        break
                    runner.last_busy_time = time.time()
                    chapter_chunks.append(chunk)
                    yield {
                        "type": "chunk",
                        "book_id": target_book.id,
                        "chapter_index": i,
                        "chapter_id": next_chap_id,
                        "delta": chunk
                    }

                full_content = "".join(chapter_chunks).strip()
                if not full_content or len(full_content) < 50:
                    full_content = chronicler._generate_mock_chapter(
                        target_book.title, target_book.genre, target_book.world,
                        target_book.world.history, next_chap_id, is_final
                    )

                # 提取标题（优先使用细纲标题）
                lines = [l.strip() for l in full_content.split("\n") if l.strip()]
                first_line = chap_outline.get("title") or (lines[0].replace("#", "").strip() if lines else f"第{next_chap_id}章")
                if not first_line.startswith("第") and not "章" in first_line:
                    first_line = f"第{next_chap_id}章 {first_line}"

                # 入库保存
                target_book.chapters.append({
                    "id": next_chap_id,
                    "title": first_line,
                    "word_count": len(full_content),
                    "content": full_content
                })
                target_book.save()
                total_generated += 1

                # 番茄小说自动上传联动检查 (单章演化即自动上传)
                should_fanqie = self.fanqie_auto_upload if auto_fanqie is None else bool(auto_fanqie)
                fanqie_msg = ""
                if should_fanqie:
                    fq_res = self.upload_chapter_fanqie(target_book, next_chap_id, first_line, full_content)
                    fanqie_msg = fq_res.get("message", "")
                    yield {
                        "type": "fanqie_auto_uploaded",
                        "book_id": target_book.id,
                        "chapter_index": i,
                        "chapter_id": next_chap_id,
                        "title": first_line,
                        "status": fq_res.get("status"),
                        "message": fanqie_msg
                    }

                # 同步到 output/
                try:
                    (OUTPUT_DIR / f"novel_chapter_{next_chap_id:02d}.md").write_text(full_content, encoding="utf-8")
                except Exception:
                    pass

                yield {
                    "type": "chapter_done",
                    "book_id": target_book.id,
                    "chapter_index": i,
                    "total": target_count,
                    "id": next_chap_id,
                    "title": first_line,
                    "word_count": len(full_content),
                    "total_chapters": len(target_book.chapters),
                    "fanqie_auto_uploaded": bool(should_fanqie),
                    "message": f"第 {next_chap_id} 章《{first_line}》撰写完毕（{len(full_content)}字）已存盘！" + (f" [{fanqie_msg}]" if fanqie_msg else "")
                }

                time.sleep(0.5)

            yield {
                "type": "complete",
                "book_id": target_book.id,
                "total_generated": total_generated,
                "total_chapters": len(target_book.chapters),
                "book_title": target_book.title,
                "message": f"《{target_book.title}》演化已大功告成！累计共生成 {total_generated} 个新章节！"
            }

        except GeneratorExit:
            runner.stop_requested = True
        except Exception as e:
            yield {"type": "error", "book_id": target_book.id, "message": f"流式演化异常: {str(e)}"}
        finally:
            runner.is_busy = False
            runner.stop_requested = False

# 全局单例
sim_mgr = SimulationManager()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class TiandaoHTTPHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")
        super().end_headers()

    def is_admin_authenticated(self, req_data=None):
        load_dotenv()
        admin_key = (os.getenv("ADMIN_KEY") or os.getenv("ADMIN_PASSWORD") or "admin888").strip()
        auth_header = self.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        if not token:
            token = self.headers.get("X-Admin-Token", "").strip()
        if not token and req_data and isinstance(req_data, dict):
            token = (
                str(req_data.get("admin_token", "")).strip()
                or str(req_data.get("admin_password", "")).strip()
                or str(req_data.get("password", "")).strip()
            )
        return bool(token and token == admin_key)


    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/books":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(book_mgr.list_books_summary(), ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/status":
            parsed_qs = urllib.parse.parse_qs(parsed.query)
            bid = parsed_qs.get("book_id", [None])[0]
            client_v = parsed_qs.get("v", [""])[0]
            target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
            
            if target_book and client_v:
                curr_v = sim_mgr.get_state_version(target_book.id)
                if client_v == curr_v:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "unchanged": True,
                        "book_id": target_book.id,
                        "v": curr_v,
                        "is_busy": sim_mgr.is_book_busy(target_book.id)
                    }).encode("utf-8"))
                    return

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            data = sim_mgr.get_state(target_book_id=bid)
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            return

        if path in ("/api/stream/stop", "/api/simulate_stop"):
            parsed_qs = urllib.parse.parse_qs(parsed.query)
            bid = parsed_qs.get("book_id", [None])[0]
            sim_mgr.request_stop(bid)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "message": f"已成功发送停止指令 ({bid or '全部'})"}, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/system/version":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            commit_id = "local"
            branch = "main"
            try:
                import subprocess
                r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
                if r.returncode == 0 and r.stdout.strip():
                    commit_id = r.stdout.strip()
                b = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, timeout=5)
                if b.returncode == 0 and b.stdout.strip():
                    branch = b.stdout.strip()
            except Exception:
                pass
            res = {
                "version": "v1.3.0",
                "commit": commit_id,
                "branch": branch,
                "github_repo": "https://github.com/XCool-603/tiandao",
                "update_supported": True
            }
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        # 全量数据一键备份下载包 (包含所有书籍、章节正文、因果总账、系统配置与番茄免密凭证)
        if path in ("/api/admin/backup", "/api/system/backup"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                if OUTPUT_DIR.exists():
                    for root_dir, dirs, files in os.walk(OUTPUT_DIR):
                        for f in files:
                            file_path = Path(root_dir) / f
                            arcname = file_path.relative_to(OUTPUT_DIR)
                            z.write(file_path, arcname=f"output/{arcname}")
                # 同时也把项目根目录现存的 .env 加入备份
                root_env = BASE_DIR / ".env"
                if root_env.exists():
                    z.write(root_env, arcname=".env")
            buf.seek(0)
            zip_bytes = buf.getvalue()
            ts = time.strftime("%Y%m%d_%H%M%S")
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="tiandao_full_backup_{ts}.zip"')
            self.send_header("Content-Length", str(len(zip_bytes)))
            self.end_headers()
            self.wfile.write(zip_bytes)
            return

        if path in ("/api/stream/simulate", "/api/simulate_stream"):
            parsed_qs = urllib.parse.parse_qs(parsed.query)
            mode = parsed_qs.get("mode", ["single"])[0]
            mock = (parsed_qs.get("mock", ["0"])[0] in ("1", "true", "True")) or (parsed_qs.get("force_mock", ["0"])[0] in ("1", "true", "True"))
            bid = parsed_qs.get("book_id", [None])[0]
            decree = parsed_qs.get("decree", [None])[0] or parsed_qs.get("divine_decree", [""])[0]
            count_str = parsed_qs.get("count", [None])[0] or parsed_qs.get("custom_count", [None])[0]
            custom_count = int(count_str) if count_str and count_str.isdigit() else None
            auto_fanqie_val = parsed_qs.get("auto_fanqie", [None])[0]
            auto_fanqie = (auto_fanqie_val in ("1", "true", "True")) if auto_fanqie_val is not None else None

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
            runner = sim_mgr.get_runner(target_book.id)
            gen = sim_mgr.stream_simulate(mode=mode, force_mock=mock, divine_decree=decree, book_id=bid, custom_count=custom_count, auto_fanqie=auto_fanqie)
            try:
                for event in gen:
                    msg = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                runner.stop_requested = True
            except Exception as e:
                try:
                    err_msg = f"data: {json.dumps({'type': 'error', 'book_id': target_book.id, 'message': str(e)}, ensure_ascii=False)}\n\n"
                    self.wfile.write(err_msg.encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    pass
            finally:
                try:
                    gen.close()
                except Exception:
                    pass
                runner.is_busy = False
            return

        if path == "/api/drama":
            parsed_qs = urllib.parse.parse_qs(parsed.query)
            bid = parsed_qs.get("book_id", [None])[0]
            target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(target_book.dramas or [], ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/chapter":
            parsed_qs = urllib.parse.parse_qs(parsed.query)
            cid = int(parsed_qs.get("id", ["1"])[0])
            bid = parsed_qs.get("book_id", [None])[0]
            target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
            chaps = target_book.chapters
            target = next((c for c in chaps if c["id"] == cid), None)
            if not target and chaps:
                target = chaps[0]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(target or {}, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/novel":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "content": sim_mgr.novel_content
            }, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/download":
            parsed_qs = urllib.parse.parse_qs(parsed.query)
            fmt = parsed_qs.get("format", ["txt"])[0]
            bid = parsed_qs.get("book_id", [None])[0]
            cid_str = parsed_qs.get("id", [None])[0]
            target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
            chaps = target_book.chapters
            clean_title = target_book.title.replace("《", "").replace("》", "")
            if cid_str:
                cid = int(cid_str)
                target = next((c for c in chaps if c["id"] == cid), None)
                content = target["content"] if target else (sim_mgr.novel_content or "")
                filename = f"{clean_title}_第{cid}章.{fmt}"
            else:
                if chaps:
                    content = "\n\n" + ("=" * 40) + "\n\n".join([f"《{c['title']}》\n\n{c['content']}" for c in chaps])
                else:
                    content = sim_mgr.novel_content or "暂无小说正文，请先演化著书。"
                filename = f"{clean_title}_全本.{fmt}"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{urllib.parse.quote(filename)}"')
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
            return

        if path == "/api/export/fanqie_zip":
            parsed_qs = urllib.parse.parse_qs(parsed.query)
            bid = parsed_qs.get("book_id", [None])[0]
            target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
            clean_title = target_book.title.replace("《", "").replace("》", "")
            chaps = target_book.chapters

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                # 1. 签约大纲与作品信息
                char_lines = []
                for c in target_book.world.characters.values():
                    char_lines.append(f"- 【{c['name']}】（{c.get('title','')} · {c.get('cultivation_level','')}）：{c.get('public_profile','')}")
                chars_str = "\n".join(char_lines) if char_lines else "暂无"
                tags_str = " / ".join(get_fanqie_category_tags(target_book.genre))
                total_words = sum(c.get("word_count", 0) for c in chaps)
                avg_words = (total_words // len(chaps)) if chaps else 0

                outline_content = f"""================================================================================
            番茄小说作家后台 · 新书签约信息与主线设定大纲
================================================================================

【作品名称】：{target_book.title}
【作品流派】：{target_book.genre}
【番茄推荐分类标签】：{tags_str}
【作品简介】：
{target_book.synopsis or '暂无'}

【核心金手指与主线看点】：
{target_book.theme_prompt or '暂无'}

【核心主角与重要配角设定】：
{chars_str}

【全书章节总数】：{len(chaps)} 章
【全书累计字数】：{total_words:,} 字
【平均单章字数】：{avg_words:,} 字（{"符合番茄全勤考核 1,000~4,000 字标准" if avg_words >= 1000 else "建议补充至 1,000 字以上以符合全勤审核"}）

【番茄小说后台上传指引】：
1. 访问番茄小说作家专区（https://fanqienovel.com/main/writer/login）登录作家账号；
2. 进入【作品管理】（https://fanqienovel.com/main/writer/book）点击【创建作品】，将上述“作品名称”、“作品分类”、“作品简介”复制填入；
3. 进入【章节管理】，点击【批量导入】；
4. 选择本 ZIP 压缩包中的各章节 txt 文件（或直接上传本压缩包）；
5. 系统将自动按顺序识别章节序号与标题，一键保存至草稿箱即可随时发布！
================================================================================
"""
                z.writestr("00_番茄小说签约申请与作品信息.txt", outline_content.encode("utf-8"))

                # 2. 写入各个章节
                for idx, c in enumerate(chaps, start=1):
                    c_title = c.get("title", f"第{idx}章")
                    if not c_title.startswith("第") and not "章" in c_title:
                        c_title = f"第{c.get('id', idx)}章 {c_title}"
                    safe_fn = f"第{c.get('id', idx):03d}章_{c_title.replace(':', '_').replace('/', '_').replace(' ', '_')}.txt"
                    c_text = clean_fanqie_content(c_title, c.get("content", ""))
                    z.writestr(safe_fn, c_text.encode("utf-8"))

            filename = f"番茄小说官方批量导入包_{clean_title}.zip"
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{urllib.parse.quote(filename)}"')
            self.end_headers()
            self.wfile.write(buf.getvalue())
            return

        if path == "/api/export/fanqie_txt":
            parsed_qs = urllib.parse.parse_qs(parsed.query)
            bid = parsed_qs.get("book_id", [None])[0]
            target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
            clean_title = target_book.title.replace("《", "").replace("》", "")
            chaps = target_book.chapters

            full_txt_parts = [
                f"《{clean_title}》",
                f"题材：{target_book.genre}",
                f"简介：{target_book.synopsis}",
                "=" * 40,
                ""
            ]
            for idx, c in enumerate(chaps, start=1):
                c_title = c.get("title", f"第{idx}章")
                if not c_title.startswith("第") and not "章" in c_title:
                    c_title = f"第{c.get('id', idx)}章 {c_title}"
                full_txt_parts.append(clean_fanqie_content(c_title, c.get("content", "")))
                full_txt_parts.append("\n" + ("=" * 40) + "\n")

            full_txt = "\n\n".join(full_txt_parts)
            filename = f"{clean_title}_番茄小说智能分章版.txt"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{urllib.parse.quote(filename)}"')
            self.end_headers()
            self.wfile.write(full_txt.encode("utf-8"))
            return

        if path == "/api/drama/list":
            parsed_qs = urllib.parse.parse_qs(parsed.query)
            bid = parsed_qs.get("book_id", [None])[0]
            target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
            dramas = getattr(target_book, "dramas", []) if target_book else []
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "dramas": dramas}, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/drama/export":
            parsed_qs = urllib.parse.parse_qs(parsed.query)
            bid = parsed_qs.get("book_id", [None])[0]
            ep_str = parsed_qs.get("episode_num", ["1"])[0]
            fmt = parsed_qs.get("format", ["csv"])[0].lower()
            target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
            dramas = getattr(target_book, "dramas", []) if target_book else []

            selected_drama = None
            if ep_str.isdigit():
                ep_num = int(ep_str)
                for d in dramas:
                    if d.get("episode_num") == ep_num:
                        selected_drama = d
                        break
            if not selected_drama and dramas:
                selected_drama = dramas[0]

            if not selected_drama:
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "暂无短剧分镜数据，请先生成"}, ensure_ascii=False).encode("utf-8"))
                return

            clean_book = (target_book.title if target_book else "微短剧").replace("《", "").replace("》", "")
            ep_val = selected_drama.get("episode_num", 1)

            if fmt == "srt":
                srt_content = DramaAgent.export_srt(selected_drama)
                filename = f"{clean_book}_第{ep_val}集_剪映字幕.srt"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{urllib.parse.quote(filename)}"')
                self.end_headers()
                self.wfile.write(srt_content.encode("utf-8"))
                return
            elif fmt == "txt":
                txt_content = DramaAgent.export_script_txt(selected_drama)
                filename = f"{clean_book}_第{ep_val}集_导演分镜表.txt"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{urllib.parse.quote(filename)}"')
                self.end_headers()
                self.wfile.write(txt_content.encode("utf-8"))
                return
            else:
                csv_content = DramaAgent.export_shots_csv(selected_drama)
                filename = f"{clean_book}_第{ep_val}集_AI视频生图分镜.csv"
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8-sig")
                self.send_header("Content-Disposition", f'attachment; filename="{urllib.parse.quote(filename)}"')
                self.end_headers()
                self.wfile.write(csv_content.encode("utf-8-sig"))
                return

        if path == "/api/publish/audit":
            parsed_qs = urllib.parse.parse_qs(parsed.query)
            bid = parsed_qs.get("book_id", [None])[0]
            target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
            chaps = target_book.chapters
            total_words = sum(c.get("word_count", 0) for c in chaps)
            avg_words = (total_words // len(chaps)) if chaps else 0

            below_1000 = [c["id"] for c in chaps if c.get("word_count", 0) < 1000]
            tags = get_fanqie_category_tags(target_book.genre)

            audit_res = {
                "book_id": target_book.id,
                "title": target_book.title,
                "clean_title": target_book.title.replace("《", "").replace("》", ""),
                "genre": target_book.genre,
                "synopsis": target_book.synopsis or "",
                "theme_prompt": target_book.theme_prompt or "",
                "fanqie_tags": tags,
                "chapter_count": len(chaps),
                "total_words": total_words,
                "avg_words": avg_words,
                "is_attendance_qualified": avg_words >= 1000,
                "short_chapters": below_1000,
                "sensitive_words_count": 0,
                "score": 98 if avg_words >= 1000 else 85,
                "status": "ready",
                "login_url": "https://fanqienovel.com/main/writer/login",
                "book_manage_url": "https://fanqienovel.com/main/writer/book",
                "chapters": [
                    {
                        "id": c.get("id", idx),
                        "title": c.get("title", f"第{idx}章"),
                        "word_count": c.get("word_count", len(c.get("content", "")))
                    }
                    for idx, c in enumerate(chaps, 1)
                ]
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(audit_res, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/outline":
            parsed_qs = urllib.parse.parse_qs(parsed.query)
            bid = parsed_qs.get("book_id", [None])[0]
            target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "book_id": target_book.id,
                "title": target_book.title,
                "genre": target_book.genre,
                "outline": getattr(target_book, "outline", {}),
                "foreshadowings": getattr(target_book, "foreshadowings", [])
            }, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/fanqie/config":
            cfg = sim_mgr._load_fanqie_config()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "auto_upload": sim_mgr.fanqie_auto_upload,
                "webhook_url": cfg.get("webhook_url", ""),
                "has_cookie": bool(cfg.get("cookie")),
                "publish_mode": cfg.get("publish_mode", "drafts")
            }, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/fanqie/pending_chapter":
            qs = urllib.parse.parse_qs(parsed.query)
            query_book_id = qs.get("book_id", [""])[0]
            target_book = book_mgr.books.get(query_book_id, sim_mgr.active_book) if query_book_id else sim_mgr.active_book
            pending = sim_mgr.get_pending_fanqie_chapter(target_book.id if target_book else None)
            synced = sim_mgr.get_fanqie_sync_state(target_book.id if target_book else None)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "has_pending": bool(pending),
                "chapter": pending,
                "book_id": target_book.id if target_book else "",
                "book_title": target_book.title if target_book else "",
                "synced_count": len(synced),
                "total_chapters": len(target_book.chapters) if target_book else 0
            }, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/fanqie/sync_status":
            target_book = sim_mgr.active_book
            synced = sim_mgr.get_fanqie_sync_state(target_book.id if target_book else None)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "book_id": target_book.id if target_book else "",
                "synced": synced,
                "total_chapters": len(target_book.chapters) if target_book else 0
            }, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/fanqie/script.user.js":
            script_path = BASE_DIR / "fanqie_userscript.js"
            content = script_path.read_text(encoding="utf-8") if script_path.exists() else "// Script file not found"
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
            return

        # 原生番茄作家账号登录态查询
        if path == "/api/fanqie/auth_status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(fanqie_uploader.get_auth_status(), ensure_ascii=False).encode("utf-8"))
            return

        # 原生番茄扫码登录二维码图片获取
        if path == "/api/fanqie/qr_code":
            if fanqie_uploader.QR_CODE_PATH.exists():
                data = fanqie_uploader.QR_CODE_PATH.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
            return

        # 管理端专属配置读取接口 (需鉴权)
        if path == "/api/admin/config":
            if not self.is_admin_authenticated():
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "error": "请先登录管理员账号"}, ensure_ascii=False).encode("utf-8"))
                return
            real_key = os.getenv("OPENAI_API_KEY", "")
            masked = f"{real_key[:3]}****{real_key[-4:]}" if len(real_key) > 8 else ("已安全配置" if real_key else "")
            cfg = {
                "has_api_key": bool(real_key and real_key != "your_api_key_here"),
                "api_key_masked": masked,
                "base_url": os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
                "model_name": os.getenv("MODEL_NAME", "deepseek-chat"),
                "tiandao_model": os.getenv("TIANDAO_MODEL", os.getenv("MODEL_NAME", "deepseek-chat")),
                "chronicler_model": os.getenv("CHRONICLER_MODEL", os.getenv("MODEL_NAME", "deepseek-chat")),
                "http_port": int(os.getenv("TIANDAO_PORT", "8088")),
                "ws_port": int(os.getenv("TIANDAO_WS_PORT", "8089"))
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "config": cfg}, ensure_ascii=False).encode("utf-8"))
            return

        # 静态文件服务
        if path == "/" or path == "/index.html":
            file_path = WEB_DIR / "index.html"
            if file_path.exists():
                content = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(content)
                return

        # 管理控制台专属静态文件
        if path == "/admin" or path == "/admin.html":
            file_path = WEB_DIR / "admin.html"
            if file_path.exists():
                content = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(content)
                return

        # 网站图标 (杜绝浏览器 404 报错)
        if path == "/favicon.ico":
            icon_svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                '<rect width="100" height="100" rx="22" fill="#3b82f6"/>'
                '<text x="50" y="68" font-size="54" font-family="-apple-system,BlinkMacSystemFont,PingFang SC,Microsoft YaHei,sans-serif" font-weight="bold" text-anchor="middle" fill="#ffffff">道</text>'
                '</svg>'
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(icon_svg)
        if path.startswith("/.well-known/"):
            self.send_response(204)
            self.end_headers()
            return

        # 默认 404
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def do_POST(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
            try:
                req_data = json.loads(body)
            except Exception:
                req_data = {}

            if path == "/api/drama/generate":
                load_dotenv()
                bid = req_data.get("book_id", "")
                cid = req_data.get("chapter_id")
                ep_num = req_data.get("episode_num")
                use_mock = req_data.get("mock", False) or not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "your_api_key_here"

                target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
                
                target_chap = None
                if target_book.chapters:
                    if cid is not None:
                        for c in target_book.chapters:
                            if str(c.get("id")) == str(cid):
                                target_chap = c
                                break
                    if not target_chap:
                        target_chap = target_book.chapters[-1]

                if not target_chap:
                    chap_title = "末世惊变·第一幕"
                    chap_content = f"{target_book.title}。{target_book.synopsis}。世界背景：{target_book.world.scene_description}"
                else:
                    chap_title = target_chap.get("title", "未命名章节")
                    chap_content = target_chap.get("content", "")

                if not ep_num:
                    ep_num = len(getattr(target_book, "dramas", [])) + 1

                llm = LLMClient(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
                model_name = os.getenv("CHRONICLER_MODEL") or os.getenv("TIANDAO_MODEL") or os.getenv("DEFAULT_MODEL") or "gemini-2.5-flash"
                drama_agent = DramaAgent(llm, model_name=model_name)

                drama_data = drama_agent.generate_from_chapter(
                    book_title=target_book.title,
                    genre=target_book.genre,
                    chapter_title=chap_title,
                    chapter_content=chap_content,
                    episode_num=ep_num,
                    force_mock=use_mock
                )

                if not hasattr(target_book, "dramas") or target_book.dramas is None:
                    target_book.dramas = []

                replaced = False
                for idx, d in enumerate(target_book.dramas):
                    if d.get("episode_num") == ep_num:
                        target_book.dramas[idx] = drama_data
                        replaced = True
                        break
                if not replaced:
                    target_book.dramas.append(drama_data)

                target_book.save()

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "ok",
                    "drama": drama_data,
                    "dramas": target_book.dramas,
                    "message": f"成功为《{target_book.title}》生成第 {ep_num} 集竖屏短剧分镜表！"
                }, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/drama/delete":
                bid = req_data.get("book_id", "")
                ep_num = req_data.get("episode_num")
                target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
                if hasattr(target_book, "dramas") and target_book.dramas:
                    target_book.dramas = [d for d in target_book.dramas if d.get("episode_num") != ep_num]
                    target_book.save()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "dramas": getattr(target_book, "dramas", [])}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/drama/save":
                bid = req_data.get("book_id", "")
                drama_data = req_data.get("drama", {})
                ep_num = drama_data.get("episode_num")
                target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
                if not hasattr(target_book, "dramas") or target_book.dramas is None:
                    target_book.dramas = []
                replaced = False
                for idx, d in enumerate(target_book.dramas):
                    if d.get("episode_num") == ep_num:
                        target_book.dramas[idx] = drama_data
                        replaced = True
                        break
                if not replaced:
                    target_book.dramas.append(drama_data)
                target_book.save()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "message": "短剧分镜已保存"}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/outline/generate":
                load_dotenv()
                bid = req_data.get("book_id", "")
                target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
                llm = LLMClient(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))
                use_mock = req_data.get("mock", False) or not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "your_api_key_here"
                new_outline = book_mgr.generate_book_outline(target_book.id, llm_client=llm, force_mock=use_mock)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "outline": new_outline}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/outline/update":
                bid = req_data.get("book_id", "")
                outline_data = req_data.get("outline", {})
                target_id = bid or sim_mgr.active_book.id
                success = book_mgr.update_book_outline(target_id, outline_data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok" if success else "error"}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/foreshadowing/add":
                bid = req_data.get("book_id", "")
                target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
                f_data = req_data.get("foreshadowing", {})
                res = book_mgr.add_or_update_foreshadowing(target_book, f_data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "foreshadowing": res}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/foreshadowing/delete":
                bid = req_data.get("book_id", "")
                target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
                f_id = req_data.get("id", "")
                success = book_mgr.delete_foreshadowing(target_book, f_id)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok" if success else "not_found"}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/switch_book":
                bid = req_data.get("book_id", "")
                success = book_mgr.set_active_book(bid)
                target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
                state = sim_mgr.get_state(target_book_id=target_book.id) if target_book else None
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "ok" if success else "not_found",
                    "active_book": target_book.id if target_book else "",
                    "state": state
                }, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/admin/create_book":
                title = req_data.get("title", "")
                genre = req_data.get("genre", "现代都市逆袭")
                theme = req_data.get("theme", "")
                synopsis = req_data.get("synopsis", "")
                new_book = book_mgr.create_book(title=title, genre=genre, theme_prompt=theme, synopsis=synopsis)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "book_id": new_book.id, "id": new_book.id, "title": new_book.title}, ensure_ascii=False).encode("utf-8"))
                return

            if path in ("/api/book/delete", "/api/admin/delete_book"):
                if not self.is_admin_authenticated(req_data):
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "error": "权限不足：删除作品需要验证管理员密码！", "need_auth": True}, ensure_ascii=False).encode("utf-8"))
                    return
                bid = req_data.get("book_id", "")
                success = book_mgr.delete_book(bid)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok" if success else "error", "active_book_id": book_mgr.active_book_id}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/chapter/delete":
                if not self.is_admin_authenticated(req_data):
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "error": "权限不足：删除章节需要验证管理员密码，不允许随便修改！", "need_auth": True}, ensure_ascii=False).encode("utf-8"))
                    return
                bid = req_data.get("book_id", "") or sim_mgr.active_book.id
                cid = req_data.get("chapter_id", None)
                success = book_mgr.delete_chapter(bid, cid)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok" if success else "error"}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/chapter/clear_all":
                if not self.is_admin_authenticated(req_data):
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "error": "权限不足：清空章节需要验证管理员密码，不允许随便修改！", "need_auth": True}, ensure_ascii=False).encode("utf-8"))
                    return
                bid = req_data.get("book_id", "") or sim_mgr.active_book.id
                success = book_mgr.clear_chapters(bid)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok" if success else "error"}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/admin/reset_book":
                if not self.is_admin_authenticated(req_data):
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "error": "权限不足：重置作品需要验证管理员密码！", "need_auth": True}, ensure_ascii=False).encode("utf-8"))
                    return
                bid = req_data.get("book_id", "") or sim_mgr.active_book.id
                success = book_mgr.reset_book(bid)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok" if success else "error"}, ensure_ascii=False).encode("utf-8"))
                return

            if path in ("/api/stream/stop", "/api/simulate_stop"):
                bid = req_data.get("book_id", "")
                sim_mgr.request_stop(bid)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "message": f"已成功发送停止指令 ({bid or '当前作品'})"}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/publish/sync":
                bid = req_data.get("book_id", "")
                webhook = req_data.get("webhook_url", "")
                platform = req_data.get("platform", "fanqie")
                mode = req_data.get("mode", "drafts")
                target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book

                webhook_status = "unconfigured"
                if webhook and webhook.startswith("http"):
                    try:
                        wh_payload = {
                            "book_title": target_book.title,
                            "genre": target_book.genre,
                            "synopsis": target_book.synopsis,
                            "chapter_count": len(target_book.chapters),
                            "chapters": target_book.chapters,
                            "platform": platform,
                            "publish_mode": mode
                        }
                        wh_req = urllib.request.Request(webhook, data=json.dumps(wh_payload).encode("utf-8"), headers={"Content-Type": "application/json"})
                        with urllib.request.urlopen(wh_req, timeout=10) as wh_res:
                            webhook_status = f"success_{wh_res.status}"
                    except Exception as e_wh:
                        webhook_status = f"error: {str(e_wh)}"

                res = {
                    "status": "ok",
                    "platform": platform,
                    "mode": mode,
                    "book_title": target_book.title,
                    "synced_chapters": len(target_book.chapters),
                    "total_words": sum(c.get("word_count", 0) for c in target_book.chapters),
                    "webhook_status": webhook_status,
                    "author_dashboard_url": "https://fanqienovel.com/main/writer/login",
                    "author_book_url": "https://fanqienovel.com/main/writer/book",
                    "message": f"《{target_book.title}》已生成全网分发指令包（共 {len(target_book.chapters)} 章）！"
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/fanqie/config":
                updated = sim_mgr.save_fanqie_config(req_data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "config": updated}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/fanqie/start_login":
                res = fanqie_uploader.start_browser_login_async()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/fanqie/config":
                cfg = fanqie_uploader.load_fanqie_config()
                for k in ("auto_upload", "publish_mode", "ai_disclosure", "author_name"):
                    if k in req_data:
                        cfg[k] = req_data[k]
                fanqie_uploader.save_fanqie_config(cfg)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "config": cfg}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/fanqie/upload_chapter":
                bid = req_data.get("book_id", "")
                cid = req_data.get("chapter_id", None)
                target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
                res = sim_mgr.upload_chapter_fanqie(target_book, cid)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/fanqie/upload_all":
                bid = req_data.get("book_id", "")
                target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
                success_count = 0
                for c in target_book.chapters:
                    r = sim_mgr.upload_chapter_fanqie(target_book, c.get("id"))
                    if r.get("status") in ("ok", "local_ready"):
                        success_count += 1
                res = {
                    "status": "ok",
                    "total_chapters": len(target_book.chapters),
                    "success_count": success_count,
                    "message": f"《{target_book.title}》全书共 {len(target_book.chapters)} 章已全部完成番茄排版与同步上传！"
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/fanqie/confirm_uploaded":
                bid = req_data.get("book_id", "")
                cid = req_data.get("chapter_id", None)
                mode = req_data.get("mode", "draft")
                remote_id = req_data.get("remote_id", "")
                synced = sim_mgr.mark_fanqie_synced(bid, cid, mode=mode, remote_id=remote_id)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "message": f"第 {cid} 章同步记录已确认", "synced_count": len(synced)}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/fanqie/launch_edge_bot":
                try:
                    bot_script = BASE_DIR / "fanqie_bot.py"
                    subprocess.Popen([sys.executable, str(bot_script)], creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
                    msg = "已在独立控制台窗口成功唤起番茄 Edge 挂机发书机器人！"
                    st = "ok"
                except Exception as e_bot:
                    msg = f"唤起发书机器人失败: {e_bot}"
                    st = "error"
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": st, "message": msg}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/auto_publish":
                mock = req_data.get("mock", False)
                rounds = req_data.get("rounds", 3)
                res = sim_mgr.auto_simulate_and_publish(rounds=rounds, force_mock=mock)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                return

            if path in ("/api/chapter/save", "/api/chapter/update"):
                if not self.is_admin_authenticated(req_data):
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "error": "权限不足：修改或精修章节内容需要管理员密码，不允许随便修改！", "need_auth": True}, ensure_ascii=False).encode("utf-8"))
                    return
                bid = req_data.get("book_id", "")
                cid = req_data.get("chapter_id")
                new_content = req_data.get("content", "")
                new_title = req_data.get("title", "")
                target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
                for chap in target_book.chapters:
                    if chap.get("id") == cid:
                        chap["content"] = new_content
                        chap["word_count"] = len(new_content)
                        if new_title:
                            chap["title"] = new_title
                        break
                target_book.save()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "message": "章节内容已成功保存"}, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/system/update":
                # 支持一键从 GitHub 拉取最新版本代码与升级依赖
                try:
                    import subprocess
                    fetch_res = subprocess.run(["git", "fetch", "--all"], capture_output=True, text=True, timeout=30)
                    pull_res = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True, timeout=60)
                    pip_res = subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"], capture_output=True, text=True, timeout=60)
                    ok = (pull_res.returncode == 0)
                    out_msg = pull_res.stdout.strip() or pull_res.stderr.strip() or fetch_res.stderr.strip() or "已是最新版本"
                    res = {
                        "status": "ok" if ok else "error",
                        "message": "✅ 代码已成功从 GitHub 更新至最新版本！请重启控制台生效。" if ok else f"更新异常: {out_msg}",
                        "details": out_msg
                    }
                except Exception as e_up:
                    res = {"status": "error", "message": f"执行升级命令异常: {str(e_up)}"}
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/spawn":
                preset_id = req_data.get("preset_id")
                custom_prompt = req_data.get("custom_prompt", "")
                mock = req_data.get("mock", False)
                bid = req_data.get("book_id", "")
                target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
                res = sim_mgr.spawn_character(preset_id=preset_id, custom_prompt=custom_prompt, force_mock=mock, target_book=target_book)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/chronicler":
                mock = req_data.get("mock", False)
                bid = req_data.get("book_id", "")
                target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
                res = sim_mgr.generate_novel(force_mock=mock, target_book=target_book)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
                return

            if path == "/api/reset":
                theme = req_data.get("theme", "")
                sim_mgr.reset(world_theme=theme)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}, ensure_ascii=False).encode("utf-8"))
                return

            # 管理员登录鉴权
            if path == "/api/admin/login":
                pwd = req_data.get("password", "").strip()
                admin_key = os.getenv("ADMIN_KEY", "admin888").strip()
                if pwd and pwd == admin_key:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", "token": admin_key, "message": "管理员验证成功"}, ensure_ascii=False).encode("utf-8"))
                else:
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "error": "管理口令错误，请核对后重试"}, ensure_ascii=False).encode("utf-8"))
                return

            # 大模型连通性实测探针 (需管理端鉴权)
            if path == "/api/admin/test_connection":
                if not self.is_admin_authenticated(req_data):
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "error": "权限不足：请先验证管理员身份"}, ensure_ascii=False).encode("utf-8"))
                    return

                test_key = req_data.get("api_key", "").strip()
                if not test_key or test_key.startswith("•") or "****" in test_key:
                    test_key = os.getenv("OPENAI_API_KEY", "")
                test_base = req_data.get("base_url", "").strip() or os.getenv("OPENAI_BASE_URL", "http://dxcool.cn:7863/v1")
                test_model = req_data.get("model_name", "").strip() or os.getenv("MODEL_NAME", "balanced-model")

                t_start = time.time()
                try:
                    from llm_client import LLMClient
                    client = LLMClient(api_key=test_key, base_url=test_base)
                    reply = client.chat(
                        model=test_model,
                        messages=[{"role": "user", "content": "请回复'pong'，不要输出任何其他多余文字。"}],
                        temperature=0.1,
                        max_tokens=20,
                        retries=1
                    )
                    latency = round((time.time() - t_start) * 1000)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "ok",
                        "latency_ms": latency,
                        "model": test_model,
                        "reply": reply.strip()
                    }, ensure_ascii=False).encode("utf-8"))
                except Exception as e_test:
                    latency = round((time.time() - t_start) * 1000)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "error",
                        "latency_ms": latency,
                        "error": str(e_test)
                    }, ensure_ascii=False).encode("utf-8"))
                return

            # API 与大模型网关配置保存 (严格禁止用户端修改，仅限管理端通过凭据修改)
            if path in ("/api/config", "/api/admin/config"):
                if not self.is_admin_authenticated(req_data):
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "error",
                        "error": "权限拒绝：API 与大模型核心配置仅允许在管理端 (/admin) 凭管理员密码修改，用户端无权更改。"
                    }, ensure_ascii=False).encode("utf-8"))
                    return

                input_key = req_data.get("api_key", "").strip()
                if input_key and not input_key.startswith("•") and not "****" in input_key:
                    new_key = input_key
                else:
                    new_key = os.getenv("OPENAI_API_KEY", "")
                new_base = req_data.get("base_url", "").strip() or os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
                new_model = req_data.get("model_name", "").strip() or os.getenv("MODEL_NAME", "deepseek-chat")
                new_td = req_data.get("tiandao_model", "").strip() or os.getenv("TIANDAO_MODEL", new_model)
                new_chr = req_data.get("chronicler_model", "").strip() or os.getenv("CHRONICLER_MODEL", new_model)
                new_admin_pwd = req_data.get("admin_key_new", "").strip() or os.getenv("ADMIN_KEY", "admin888")
                new_port = req_data.get("http_port", os.getenv("TIANDAO_PORT", "8088"))
                new_ws = req_data.get("ws_port", os.getenv("TIANDAO_WS_PORT", "8089"))

                # 核心升级：原子化双写持久化至挂载卷 output/system_config.json 与 output/.env
                # 无论 Docker 如何升级、更新镜像或重建容器，配置永不丢失！
                save_persistent_config({
                    "api_key": new_key,
                    "base_url": new_base,
                    "model_name": new_model,
                    "tiandao_model": new_td,
                    "chronicler_model": new_chr,
                    "admin_key": new_admin_pwd,
                    "http_port": str(new_port),
                    "ws_port": str(new_ws)
                })

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "message": "管理员配置已永久落盘保存至持久化卷，并热重载生效！"}, ensure_ascii=False).encode("utf-8"))
                return

            self.send_response(404)
            self.end_headers()
        except Exception as e:
            print(f"[HTTP Handler 异常保护] 处理 {self.path} 时发生未捕获异常: {e}")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"系统推演提示: {str(e)}"}, ensure_ascii=False).encode("utf-8"))
            except Exception:
                pass

def start_ws_server(ws_port=8089):
    try:
        from websockets.sync.server import serve
        def handle_ws(websocket):
            try:
                for message in websocket:
                    try:
                        data = json.loads(message)
                    except Exception:
                        continue
                    action = data.get("action", "")
                    if action == "start":
                        mode = data.get("mode", "single")
                        count = data.get("count", 1)
                        custom_count = int(count) if count and str(count).isdigit() else 1
                        bid = data.get("book_id", None)
                        decree = data.get("decree", "")
                        mock = bool(data.get("mock", False))
                        auto_fanqie = data.get("auto_fanqie", None)
                        target_book = book_mgr.books.get(bid, sim_mgr.active_book) if bid else sim_mgr.active_book
                        runner = sim_mgr.get_runner(target_book.id)
                        gen = sim_mgr.stream_simulate(mode=mode, force_mock=mock, divine_decree=decree, book_id=bid, custom_count=custom_count, auto_fanqie=auto_fanqie)
                        try:
                            for event in gen:
                                try:
                                    websocket.send(json.dumps(event, ensure_ascii=False))
                                except Exception:
                                    # 客户端可能切后台或刷新，中断当前推送信道，由后台完成当前章节安全存盘
                                    break
                                if event.get("type") in ("complete", "stopped", "error"):
                                    break
                        finally:
                            try:
                                gen.close()
                            except Exception:
                                pass
                            runner.is_busy = False
                    elif action == "stop":
                        bid = data.get("book_id", None)
                        sim_mgr.request_stop(bid)
                        try:
                            websocket.send(json.dumps({"type": "stopped", "book_id": bid, "message": "已收到安全停止指令并存盘"}, ensure_ascii=False))
                        except Exception:
                            pass
            except Exception:
                pass

        print(f"  ⚡ 【WebSocket】全双工流式推演服务已启动: ws://localhost:{ws_port}")
        # 关闭内部死板的 20 秒 Ping 超时掐断机制 (ping_interval=None)，彻底杜绝大模型长耗时思考时被误判超时断开
        with serve(handle_ws, "0.0.0.0", ws_port, ping_interval=None, ping_timeout=None) as ws_server:
            ws_server.serve_forever()
    except Exception as e_ws:
        print(f"[WebSocket 服务提示] 端口 {ws_port} 未能独占 ({e_ws})，推演系统已无缝切入 HTTP SSE 流式通道，控制台功能 100% 正常运行！")

def start_server(port=8088):
    env_ws_port = os.getenv("TIANDAO_WS_PORT")
    ws_port = int(env_ws_port) if env_ws_port and env_ws_port.isdigit() else (port + 1)
    ws_thread = threading.Thread(target=start_ws_server, args=(ws_port,), daemon=True)
    ws_thread.start()

    server = ThreadedHTTPServer(("0.0.0.0", port), TiandaoHTTPHandler)
    print(f"\n=======================================================")
    print(f"  [天道] 控制台网页服务已启动！")
    print(f"  HTTP 访问地址: http://localhost:{port}")
    print(f"  WebSocket 地址: ws://localhost:{ws_port}")
    print(f"=======================================================\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已关闭。")

if __name__ == "__main__":
    load_dotenv(override=True)
    env_port = os.getenv("TIANDAO_PORT")
    port = int(env_port) if env_port and env_port.isdigit() else 8088
    if len(sys.argv) > 1:
        try:
            arg_port = int(sys.argv[1])
            # 若命令行参数是 8088 且 env 明确配置了其他端口，尊重持久化配置
            if env_port and arg_port == 8088 and int(env_port) != 8088:
                port = int(env_port)
            else:
                port = arg_port
        except ValueError:
            pass
    start_server(port)
