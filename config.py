import os
from pathlib import Path

def load_dotenv(override=True):
    """轻量级读取 .env 文件，无需依赖额外三方库"""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        env_example = Path(__file__).parent / ".env.example"
        if env_example.exists():
            print("[系统提示] 未找到 .env 文件，已从 .env.example 读取默认示例配置。")
            env_path = env_example
        else:
            return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if override or k not in os.environ:
                    os.environ[k] = v

load_dotenv()

# 配置项
API_KEY = os.getenv("OPENAI_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
DEFAULT_MODEL = os.getenv("MODEL_NAME", "deepseek-chat")
TIANDAO_MODEL = os.getenv("TIANDAO_MODEL", DEFAULT_MODEL)
CHRONICLER_MODEL = os.getenv("CHRONICLER_MODEL", DEFAULT_MODEL)

MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "6"))
AUTO_GENERATE_NOVEL = os.getenv("AUTO_GENERATE_NOVEL", "true").lower() in ("true", "1", "yes")

def classify_genre(genre: str, title: str = "", theme: str = "") -> str:
    """
    智能题材分类识别器，精确区分现代都市、古代历史、科幻星际、规则怪谈、奇幻魔法、游戏无限、传统武侠、仙侠修真。
    严格规避【穿/穿越】等泛用网文写作手法导致的误判（穿越现代、穿越重生绝不能误判为古代历史！）。
    """
    g = (genre or "").lower().strip()
    t = (title or "").lower().strip()
    th = (theme or "").lower().strip()
    full_text = f"{g} {t} {th}"

    # 1. 优先判定：现代都市 / 现实商战 / 逆袭神豪 / 年代日常
    # 只要包含现代/都市/商战等特征词，且不包含明确古代王朝帝王词汇，一律判定为现代都市 (urban)
    urban_keywords = [
        "现代", "都市", "神豪", "逆袭", "商战", "职场", "战神", "赘婿", "兵王", "神医",
        "龙王", "文娱", "明星", "校花", "校园", "日常", "直播", "财阀", "娱乐圈", "相亲",
        "买房", "炒股", "高考", "大学", "总裁", "四合院", "年代", "改革开放", "刑警", "警匪",
        "互联网", "首富", "富二代", "乡村", "种田致富", "奶爸", "甜宠", "真千金", "假千金",
        "金融", "创业", "外卖", "保安", "房东", "豪门", "千亿", "败家"
    ]
    ancient_dynasty_words = [
        "大明", "明朝", "朱元璋", "洪武", "崇祯", "大唐", "唐朝", "李世民", "贞观",
        "大宋", "两宋", "宋朝", "赵匡胤", "三国", "曹操", "刘备", "大秦", "秦始皇",
        "清朝", "康熙", "乾隆", "两晋", "战国", "秦汉", "锦衣卫", "奉天殿", "紫禁城",
        "朝堂", "东厂", "西厂", "皇权", "九卿", "知县", "首辅", "巡抚", "尚书"
    ]

    has_urban = any(k in full_text for k in urban_keywords)
    has_ancient = any(k in full_text for k in ancient_dynasty_words)

    # 如果有明确古代王朝，且没有明确“现代/都市”前缀反转，归为历史
    if has_ancient and not any(k in full_text for k in ["现代", "都市", "重回现代", "穿回现代"]):
        return "history"

    if has_urban:
        return "urban"

    # 2. 古代历史 / 庙堂权谋（严防单纯“穿/穿越”触发！必须有真正的历史权谋关键词）
    history_keywords = [
        "历史", "大明", "明朝", "大唐", "唐朝", "大宋", "两宋", "宋朝", "三国", "朝堂",
        "权谋", "两晋", "春秋", "战国", "秦汉", "大秦", "秦朝", "清朝", "康熙", "乾隆",
        "朱元璋", "崇祯", "老朱", "锦衣卫", "奉天殿", "古代", "科举", "皇权", "宗庙",
        "尚书", "中丞", "宰相", "首辅", "巡抚", "知府", "布政使", "东厂", "西厂", "九卿"
    ]
    if any(k in full_text for k in history_keywords):
        return "history"

    # 3. 科幻星际 / 赛博废土 / 机械机甲
    scifi_keywords = ["科幻", "星际", "末世", "赛博", "废土", "机甲", "太空", "战舰", "舰队", "曲率", "高维", "外星", "深空", "避难所", "硬核科幻"]
    if any(k in full_text for k in scifi_keywords):
        return "scifi"

    # 4. 悬疑怪谈 / 规则惊悚 / 克苏鲁
    suspense_keywords = ["悬疑", "惊悚", "诡异", "怪谈", "规则", "克苏鲁", "灵异", "盗墓", "解密", "恐怖", "收容", "对策局", "不可名状"]
    if any(k in full_text for k in suspense_keywords):
        return "suspense"

    # 5. 西方奇幻 / 剑与魔法 / 领主
    fantasy_keywords = ["西幻", "魔法", "奇幻", "领主", "中世纪", "骑士", "巨龙", "剑与魔法", "巫师", "奥术", "精灵", "矮人", "神殿", "教廷"]
    if any(k in full_text for k in fantasy_keywords):
        return "fantasy"

    # 6. 游戏数据 / 无限诸天 / 封弊者
    gaming_keywords = ["游戏", "网游", "电竞", "无限", "系统", "数据流", "玩家", "公会", "副本", "封弊者", "全息", "npc", "神域"]
    if any(k in full_text for k in gaming_keywords):
        return "gaming"

    # 7. 传统武侠 / 快意恩仇
    wuxia_keywords = ["武侠", "江湖", "剑客", "快意", "刀客", "镖局", "华山", "少林", "武林", "名门正派", "金戈铁马"]
    if any(k in full_text for k in wuxia_keywords):
        return "wuxia"

    # 8. 仙侠修真 / 凡人流（包含修仙、修真、洪荒等，或无匹配时默认）
    return "xianxia"
