import json
from typing import List, Dict, Any
from llm_client import LLMClient
from world_state import CharacterAction, WorldState

class TiandaoAgent:
    """
    【天道 Agent (The Heaven's Will / Game Master)】
    统御因果大势，维护凡人流修仙残酷法则，判定动作真伪与战果，适时降下杀机与机缘。
    """

    def __init__(self, llm_client: LLMClient, model_name: str):
        self.llm = llm_client
        self.model = model_name

    def arbitrate(
        self,
        round_num: int,
        world: WorldState,
        actions: List[CharacterAction]
    ) -> Dict[str, Any]:
        """
        天道进行本轮因果裁决：
        1. 判定各角色的攻击、防御、暗算、逃跑是否成功。
        2. 结合凡人流弱肉强食与克制法则，结算伤势与战果。
        3. 降下符合天道剧本的外部大劫或环境突变（推波助澜，激化矛盾）。
        """
        actions_context = ""
        for act in actions:
            actions_context += (
                f"【{act.char_name}】\n"
                f"  - 真实心机/算计 (私密): {act.inner_thought}\n"
                f"  - 表面所言 (公开): \"{act.speech}\"\n"
                f"  - 具体动作/施法: {act.action}\n\n"
            )

        prompt = f"""
你是不容忤逆的【修仙界天道意志】。你掌控因果命数、五行生克与修仙界残酷的自然法则。
本作为【群像凡人修仙大作】：**无钦定主角，人人皆是主角，人人皆争一线长生机！**
风格严谨、冷峻、残酷、重因果算计，禁止无脑降智或凭空光环。

【当前世界环境】：
{world.scene_description}

【天道主线暗线与无主角争渡法则】：
{world.tiandao_master_plot}

【本轮为第 {round_num} / {world.max_rounds} 轮交锋】

【各角色本轮提报之行动】：
{actions_context}

作为至高天道，你必须拥有冷酷绝对、不偏不倚的法官视角，执行以下职责：
1. 【绝对无偏因果判定（杜绝主角光环）】：
   - 任何人都没有免死金牌！无论何人，算计有失同样会中伏重创；若布局精妙同样能暗算得逞；剧毒与伤势发作绝不凭空化解；魔功或杀招霸道同样能夺宝制胜。
   - 裁决各角色动作的真实成效：严格依据境界威压、法宝相克、符箓损耗、站位破绽与心理博弈。
2. 【大劫降临 / 变数注入】：
   - 若场面陷入僵局或言语试探过多，天道以天地异象、妖兽暴走、禁制崩塌等外部劫数强行打破平衡，逼迫角色亮出真实面目与底牌。
3. 【局势演进与生死结算】：
   - 给出本轮战斗与博弈的客观事实判定。根据战况判定角色状态（在场活跃 / 身死道消 / 远遁脱离）。
4. 【大千世界自然引渡（全自动生成新角色）】：
   - 修仙大世界生生不息！因打斗轰鸣、异宝霞光、灵气激荡或血腥煞气，**天道会自然引来其他修士破空杀入！**
   - 只要场上存活人数少于6人，天道必须根据当前战况，**自主生成1位符合环境因果的新修士**（如：闻风而来的结丹老怪、寻宝摸金散修、宗门执法使、魔门护法、路过逃难者等），直接投放下场！

请严格按以下 JSON 格式返回，切勿输出多余废话：
```json
{{
  "environment_change": "本轮过后的环境异象与动荡描写",
  "fate_twist": "天道降下的外部变数或危机催化（如妖兽偷袭、禁制爆裂、毒发）",
  "arbitration_summary": "客观战况因果裁决（详细说明各人招式碰撞结果、伤势变化、底牌消耗）",
  "character_fates": {{
    "角色名A": "alive",
    "角色名B": "dead",
    "角色名C": "escaped"
  }},
  "new_arrival": {{
    "should_spawn": true,
    "name": "新修士姓名 (2~3字)",
    "title": "尊号/头衔",
    "camp": "正道/魔道/散修/商贾",
    "cultivation_level": "境界 (如: 筑基中期 / 结丹初期)",
    "public_profile": "外貌与展露出的法宝威压描写 (60~100字)",
    "secret_profile": "【真实隐秘底牌与暗中心机准则】 (80~120字)",
    "inventory": ["法宝1", "底牌2"],
    "entrance_reason": "因何被吸引破空而来的因果缘由"
  }}
}}
```
"""

        messages = [
            {"role": "system", "content": "你是冷酷主宰一切的传统凡人流修仙天道。"},
            {"role": "user", "content": prompt}
        ]

        raw_res = self.llm.chat(self.model, messages, temperature=0.6)
        parsed = self.llm.extract_json(raw_res)

        if not parsed:
            parsed = {
                "environment_change": "寒潭水波剧烈翻滚，四周禁制灵光狂闪。",
                "fate_twist": "暗流之中，一股庞大的凶兽煞气骤然锁定当场众人！",
                "arbitration_summary": raw_res,
                "is_climax": False
            }

        return parsed
