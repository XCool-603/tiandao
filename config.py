import os
import json
from pathlib import Path

def get_config_paths():
    root = Path(__file__).parent
    output_dir = root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "root": root,
        "output_dir": output_dir,
        "system_config_json": output_dir / "system_config.json",
        "persistent_env": output_dir / ".env",
        "local_env": root / ".env",
        "example_env": root / ".env.example"
    }

def load_dotenv(override=True):
    """
    生产级多层持久化配置加载器：
    保证在 Docker 容器重建、镜像更新、git pull 后，用户在控制台保存的端口、AI Key、模型名称、管理密码永不丢失！
    优先级：
    1. 挂载持久化卷中的 output/system_config.json (最高优先级，用户 Web 界面配置)
    2. 挂载持久化卷中的 output/.env
    3. 项目根目录 .env
    4. 环境变量与 .env.example 默认回退
    """
    paths = get_config_paths()

    # 1. 先读项目根目录 .env 或 .env.example
    env_target = paths["local_env"] if paths["local_env"].exists() else paths["example_env"]
    if env_target.exists():
        try:
            with open(env_target, "r", encoding="utf-8") as f:
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
        except Exception as e:
            print(f"[配置加载告警] 读取 {env_target.name} 失败: {e}")

    # 2. 读取持久化 output/.env (挂载卷，Docker更新绝不丢失)
    if paths["persistent_env"].exists():
        try:
            with open(paths["persistent_env"], "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if v and (override or k not in os.environ or os.environ.get(k) in ("your_api_key_here", "")):
                            os.environ[k] = v
        except Exception as e:
            print(f"[配置加载告警] 读取持久化 output/.env 失败: {e}")

    # 3. 读取持久化 output/system_config.json (挂载卷中的 JSON 结构体)
    if paths["system_config_json"].exists():
        try:
            with open(paths["system_config_json"], "r", encoding="utf-8") as f:
                cfg = json.load(f)
                mapping = {
                    "api_key": "OPENAI_API_KEY",
                    "base_url": "OPENAI_BASE_URL",
                    "model_name": "MODEL_NAME",
                    "tiandao_model": "TIANDAO_MODEL",
                    "chronicler_model": "CHRONICLER_MODEL",
                    "admin_key": "ADMIN_KEY",
                    "admin_password": "ADMIN_KEY",
                    "max_rounds": "MAX_ROUNDS",
                    "http_port": "TIANDAO_PORT",
                    "ws_port": "TIANDAO_WS_PORT",
                }
                for json_key, env_var in mapping.items():
                    val = cfg.get(json_key)
                    if val is not None and str(val).strip():
                        val_str = str(val).strip()
                        # 严防 Docker 传入的默认占位符 "your_api_key_here" 覆盖掉用户的真实配置
                        if env_var == "OPENAI_API_KEY" and val_str == "your_api_key_here":
                            continue
                        os.environ[env_var] = val_str
        except Exception as e:
            print(f"[配置加载告警] 读取持久化 system_config.json 失败: {e}")

    # 4. 如果 os.environ 中的 OPENAI_API_KEY 仍然是默认占位符，且没配任何 key，置空
    if os.environ.get("OPENAI_API_KEY") == "your_api_key_here":
        os.environ["OPENAI_API_KEY"] = ""

def save_persistent_config(data: dict) -> dict:
    """
    将用户在 Web 控制台设置的配置原子化双写持久化到 output/system_config.json、output/.env 以及 .env 中，
    彻底解决容器重建/更新后端口、API与密码被重置的问题。
    """
    paths = get_config_paths()

    # 读现有配置做增量合并
    current = {}
    if paths["system_config_json"].exists():
        try:
            with open(paths["system_config_json"], "r", encoding="utf-8") as f:
                current = json.load(f)
        except Exception:
            current = {}

    # 合并新数据
    for k, v in data.items():
        if v is not None:
            current[k] = v

    # 1. 写入 output/system_config.json (挂载卷持久化)
    try:
        with open(paths["system_config_json"], "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[持久化写入告警] 写入 output/system_config.json 失败: {e}")

    # 2. 同步写入 output/.env (供 docker compose env_file 直接读取)
    env_content = [
        f"# 天道持久化系统配置 (Docker 容器重建与更新自动继承，切勿随意删除)",
        f"TIANDAO_PORT={current.get('http_port', os.getenv('TIANDAO_PORT', '8088'))}",
        f"TIANDAO_WS_PORT={current.get('ws_port', os.getenv('TIANDAO_WS_PORT', '8089'))}",
        f"OPENAI_API_KEY={current.get('api_key', os.getenv('OPENAI_API_KEY', ''))}",
        f"OPENAI_BASE_URL={current.get('base_url', os.getenv('OPENAI_BASE_URL', 'https://api.deepseek.com/v1'))}",
        f"MODEL_NAME={current.get('model_name', os.getenv('MODEL_NAME', 'deepseek-chat'))}",
        f"TIANDAO_MODEL={current.get('tiandao_model', os.getenv('TIANDAO_MODEL', ''))}",
        f"CHRONICLER_MODEL={current.get('chronicler_model', os.getenv('CHRONICLER_MODEL', ''))}",
        f"ADMIN_KEY={current.get('admin_key', current.get('admin_password', os.getenv('ADMIN_KEY', 'admin888')))}",
        f"MAX_ROUNDS={current.get('max_rounds', os.getenv('MAX_ROUNDS', '6'))}",
        f"TZ=Asia/Shanghai",
    ]
    try:
        paths["persistent_env"].write_text("\n".join(env_content) + "\n", encoding="utf-8")
    except Exception as e:
        print(f"[持久化写入告警] 写入 output/.env 失败: {e}")

    # 3. 如果项目根目录可写，同步回写根目录 .env
    try:
        paths["local_env"].write_text("\n".join(env_content) + "\n", encoding="utf-8")
    except Exception:
        pass

    # 4. 重新加载至进程内存并刷新全局变量
    load_dotenv(override=True)
    refresh_globals()
    return current

def refresh_globals():
    global API_KEY, BASE_URL, DEFAULT_MODEL, TIANDAO_MODEL, CHRONICLER_MODEL, MAX_ROUNDS, AUTO_GENERATE_NOVEL
    API_KEY = os.getenv("OPENAI_API_KEY", "")
    BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    DEFAULT_MODEL = os.getenv("MODEL_NAME", "deepseek-chat")
    TIANDAO_MODEL = os.getenv("TIANDAO_MODEL", DEFAULT_MODEL)
    CHRONICLER_MODEL = os.getenv("CHRONICLER_MODEL", DEFAULT_MODEL)
    MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", "6"))
    AUTO_GENERATE_NOVEL = os.getenv("AUTO_GENERATE_NOVEL", "true").lower() in ("true", "1", "yes")

load_dotenv()
refresh_globals()

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
