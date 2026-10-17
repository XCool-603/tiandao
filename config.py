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
