import json
from typing import Dict, Any, List
from llm_client import LLMClient
from world_state import CharacterAction

class CharacterAgent:
    """
    【角色 Agent (Actor)】
    受严格的【战争迷雾】约束，无法探知他人内心与秘密底牌；
    依据自身性格、利益诉求、真实技能道具与生死危机，生成内心算计、公开话语与动作。
    绝无降智或预设剧情杀，人人皆为自己而战。
    """

    def __init__(self, char_id: str, char_data: Dict[str, Any], llm_client: LLMClient, model_name: str):
        self.char_id = char_id
        self.name = char_data["name"]
        self.title = char_data.get("title", "")
        self.camp = char_data.get("camp", "")
        self.public_profile = char_data.get("public_profile", "")
        self.secret_profile = char_data.get("secret_profile", "")
        self.cultivation = char_data.get("cultivation_level", "")
        self.inventory = char_data.get("inventory", [])
        
        self.llm = llm_client
        self.model = model_name
        self.private_memories: List[str] = []

    def act(
        self,
        round_num: int,
        scene_desc: str,
        public_history_summary: str,
        latest_tiandao_event: str,
        other_characters_public: List[Dict[str, str]]
    ) -> CharacterAction:
        """
        基于当前公开局势与个人私密底牌，做出本回合决策。
        """
        others_desc = ""
        for other in other_characters_public:
            if other.get("name") != self.name:
                others_desc += f"- 【{other.get('name')}】({other.get('title', '')})：{other.get('public_profile', '')}\n"

        inv_str = ", ".join(self.inventory) if self.inventory else "暂无随身器物"
        status_label = f"【当前身份/境界/位阶】：{self.cultivation}" if self.cultivation else ""

        prompt = f"""
你是【{self.name}】（{self.title}，阵营：{self.camp or '独立'}）。
在你的世界与视野里：**没有谁是天定主角，你就是自己生命中唯一的主角！**
局势复杂险恶，稍有不慎便遭暗算重创甚至身败名裂。你必须竭尽全力夺得一线生机与战略优势。

【你的真实隐秘底牌与心性准则（绝对绝密，唯你自知）】：
{self.secret_profile}
【当前携带主要道具/装备/底牌】：{inv_str}
{status_label}

【你眼前的环境】：
{scene_desc}

【在场其他登场人物（你只能看到其表面伪装，看不到其内心与真实底牌）】：
{others_desc if others_desc else "周围暂无其他显露形迹之人。"}

【前序局势公开演化简要】：
{public_history_summary if public_history_summary else "各方势力齐聚现场，因果冲突一触即发。"}

【天地/局势最新异动】：
{latest_tiandao_event if latest_tiandao_event else "暗潮涌动，变数隐现。"}

【你现在的私人执念与回忆】：
{('; '.join(self.private_memories[-3:])) if self.private_memories else "为己争先，掌控自己的命运。"}

【决策指令】：
你绝非任何人的衬托垫脚石！请以你自身利益、安危与执念为第一核心，做出本回合的最优博弈决策。
若有机会夺取主动则果断出击；若势头凶险则果断规避退守；若需虚与委蛇则表面周旋暗度陈仓。

必须返回严格 JSON 格式：
```json
{{
  "inner_thought": "你的内心深层算计、推演、杀机或顾虑（字数60~120字，以你自己为核心的深层谋划）",
  "speech": "你对在场之人公开说出的话语（虚与委蛇、试探挑拨，若选择冷眼旁观则写'沉默'）",
  "action": "你的具体肢体动作、站位转移、暗中扣动物品或招式准备（符合真实博弈细节感）"
}}
```
"""

        messages = [
            {"role": "system", "content": f"你正在扮演【{self.name}】。你就是自己人生唯一的主角，立场坚定，精于算计，绝不当任何人的牺牲品。"},
            {"role": "user", "content": prompt}
        ]

        raw_res = self.llm.chat(self.model, messages, temperature=0.7)
        parsed = self.llm.extract_json(raw_res)

        if not parsed:
            first_item = self.inventory[0] if self.inventory else "随身底牌"
            parsed = {
                "inner_thought": f"局势复杂难测，各方皆心怀鬼胎。{self.name}绝不可轻信他人，必须静观其变，暗扣{first_item}以备不测。",
                "speech": "诸位稍安勿躁，眼下胜负未分，何必急于亮出所有底牌？",
                "action": f"脚步向后挪开半步拉开防守空当，右手暗扣{first_item}，警惕扫视全场破绽。"
            }

        # 记录私人记忆
        self.private_memories.append(f"第{round_num}轮算计：{parsed.get('inner_thought', '')[:40]}...")

        return CharacterAction(
            char_id=self.char_id,
            char_name=self.name,
            inner_thought=parsed.get("inner_thought", ""),
            speech=parsed.get("speech", ""),
            action=parsed.get("action", "")
        )
