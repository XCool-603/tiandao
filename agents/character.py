import json
from typing import Dict, Any, List
from llm_client import LLMClient
from world_state import CharacterAction

class CharacterAgent:
    """
    【修仙角色 Agent (Actor)】
    受严格的【战争迷雾】约束，无法探知他人内心与秘密底牌；
    依据自身性格、利益诉求与生死危机，生成内心算计、公开话语与动作。
    """

    def __init__(self, char_id: str, char_data: Dict[str, Any], llm_client: LLMClient, model_name: str):
        self.char_id = char_id
        self.name = char_data["name"]
        self.title = char_data.get("title", "")
        self.camp = char_data.get("camp", "")
        self.public_profile = char_data["public_profile"]
        self.secret_profile = char_data["secret_profile"]
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
            if other["name"] != self.name:
                others_desc += f"- 【{other['name']}】({other.get('title', '')})：{other['public_profile']}\n"

        prompt = f"""
你是【{self.name}】（{self.title}）。
这是【群像争渡修仙大世界】：**没有谁是天定主角，在你的故事里，你就是自己唯一的生命主角！**
弱肉强食、大道无情、稍有不慎便身死道消、沦为炉鼎或枯骨。你必须竭尽全力夺得一线生机与大道机缘。

【你的真实隐秘底牌与心性准则（绝对绝密，唯你自知）】：
{self.secret_profile}
【当前携带主要法宝/物品】：{', '.join(self.inventory)}
【你的真实修为】：{self.cultivation}

【你眼前的环境与大阵禁制】：
{scene_desc}

【在场其他求道者（你只能看到其表面伪装，看不到其内心与真实底牌）】：
{others_desc}

【前序局势公开演化简要】：
{public_history_summary if public_history_summary else "众人初至寒潭，夺宝大战一触即发。"}

【天道/天地最新异动】：
{latest_tiandao_event if latest_tiandao_event else "寒气弥漫，暗藏杀机。"}

【你现在的私人执念与回忆】：
{('; '.join(self.private_memories[-3:])) if self.private_memories else "为己争命，夺得大道机缘。"}

【决策指令】：
你绝非任何人的衬托垫脚石！请以你自身利益与大道执念为第一核心，做出本回合的最优博弈决策。
若能杀人夺宝则决不手软；若势头不对则果断遁逃；若能结盟利用则虚与委蛇。

必须返回严格 JSON 格式：
```json
{{
  "inner_thought": "你的内心深层算计、推演、杀机或顾虑（字数80~150字，以你自己为核心的长生谋划）",
  "speech": "你对在场之人公开说出的话语（虚与委蛇、试探挑拨，若选择冷眼旁观则写'沉默'）",
  "action": "你的具体肢体动作、站位转移、法术掐诀、暗中符箓扣动或偷袭准备（符合凡人流战斗的真实细节感）"
}}
```
"""

        messages = [
            {"role": "system", "content": f"你正在扮演求道者【{self.name}】。你就是自己人生唯一的主角，道心坚定，精于算计，绝不当任何人的垫脚石。"},
            {"role": "user", "content": prompt}
        ]

        raw_res = self.llm.chat(self.model, messages, temperature=0.7)
        parsed = self.llm.extract_json(raw_res)

        if not parsed:
            parsed = {
                "inner_thought": "局势诡谲，此地不可久留，先且静观其变，暗扣神行符以备不测。",
                "speech": "顾师兄所言极是，师弟修为低微，愿听凭差遣。",
                "action": "脚步微微向后挪动三寸，隐于石壁阴影之中，右手在宽大袖袍内捏紧了一张匿灵符。"
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
