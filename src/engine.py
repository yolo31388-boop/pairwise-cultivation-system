"""角色修炼内功系统"""
from dataclasses import dataclass, field
import random
import time as _time

# 穴位类型
TIER_NORMAL = "normal"
TIER_CORE = "core"
TIER_HIDDEN = "hidden"

# 穴位属性加成
TIER_BONUS = {TIER_NORMAL: 5, TIER_CORE: 20, TIER_HIDDEN: 50}

# 走火入魔
DEVIATION_DEBUFF_DURATION = 24 * 3600   # 属性下降持续24小时
DEVIATION_DEBUFF_FACTOR = 0.10          # 属性下降10%
DEVIATION_PROGRESS_LOSS = 0.05          # 修炼进度倒退5%

# 心法切换
ART_SWITCH_COOLDOWN = 3600              # 切换冷却1小时
ART_EXP_INHERIT_RATIO = 0.7             # 切换后修为继承70%

# 修炼资源消耗（每单位时间）
COST_PER_TIME = {"灵石": 2, "丹药": 1}

# 修炼经验每日上限
DAILY_EXP_CAP = 10000

# 突破失败
BREAKTHROUGH_MATERIAL_LOSS = 0.5        # 失败损耗50%材料
BREAKTHROUGH_FAIL_RISK_INCREASE = 0.1   # 失败增加走火入魔风险


@dataclass
class Acupoint:
    aid: str
    name: str
    is_core: bool
    prerequisites: list
    required_level: int = 1
    tier: str = ""
    special_effect: str = ""

    def __post_init__(self):
        if not self.tier:
            self.tier = TIER_CORE if self.is_core else TIER_NORMAL

    @property
    def bonus(self):
        return TIER_BONUS[self.tier]


@dataclass
class CultivationArt:
    art_id: str
    name: str
    art_type: str          # 同类型互斥，如 attack/defense/support
    exp: float = 0.0


class CultivationSystem:
    def __init__(self, now=None):
        self.acupoints: dict[str, Acupoint] = {}
        self.activated = set()
        self.player_level = 1
        self.mental_state = 100  # 心境值
        self.cultivation_exp = 0.0
        # 资源
        self.resources = {"灵石": 0, "丹药": 0}
        self.paused = False
        # 心法
        self.arts: dict[str, CultivationArt] = {}
        self.active_art_id = None
        self.last_switch_time = None
        # 走火入魔相关
        self.continuous_cultivation_time = 0.0
        self.extra_deviation_risk = 0.0
        self.deviation_debuff_until = 0.0
        # 每日经验
        self.exp_today = 0
        self._exp_day = None
        self._now = now if now is not None else _time.time()

    # ---------- 内部工具 ----------

    def _clock(self):
        return self._now

    def advance_time(self, seconds):
        """推进内部时钟（测试/离线结算用）。"""
        self._now += seconds

    def _reset_daily_exp_if_needed(self):
        day = int(self._clock() // 86400)
        if day != self._exp_day:
            self._exp_day = day
            self.exp_today = 0

    def _gain_exp(self, amount):
        self._reset_daily_exp_if_needed()
        room = max(0, DAILY_EXP_CAP - self.exp_today)
        gained = min(amount, room)
        self.exp_today += gained
        self.cultivation_exp += gained
        if self.active_art_id and self.active_art_id in self.arts:
            self.arts[self.active_art_id].exp += gained
        return gained

    # ---------- bug1: 修炼同时消耗时间+资源，不足则暂停 ----------

    def cultivate(self, time, resources=None):
        cost = {k: v * time for k, v in COST_PER_TIME.items()}
        for k, v in cost.items():
            if self.resources.get(k, 0) < v:
                self.paused = True   # 资源不足，暂停修炼
                return False
        for k, v in cost.items():
            self.resources[k] -= v
        self.paused = False
        self.continuous_cultivation_time += time
        self._gain_exp(time * 10)
        return True

    # ---------- bug2/bug3/bug9: 穴位突破 ----------

    def breakthrough(self, aid, materials=None, rng=random):
        ap = self.acupoints[aid]
        # bug2: 同时检查前置穴位链和角色等级
        if self.player_level < ap.required_level:
            return False
        for pre in ap.prerequisites:
            if pre not in self.activated:
                return False
        if rng.random() < 0.5:
            self.activated.add(aid)
            return True
        # bug9: 失败损耗材料并增加走火入魔风险
        if materials:
            for k, v in materials.items():
                lost = int(v * BREAKTHROUGH_MATERIAL_LOSS)
                self.resources[k] = self.resources.get(k, 0) - lost
        self.extra_deviation_risk += BREAKTHROUGH_FAIL_RISK_INCREASE
        return False

    # ---------- bug3: 穴位分核心/普通/隐藏，加成不同 ----------

    def get_attribute_bonus(self):
        bonus = sum(self.acupoints[a].bonus for a in self.activated
                    if a in self.acupoints)
        if self.is_deviation_debuffed():
            bonus *= (1 - DEVIATION_DEBUFF_FACTOR)
        return bonus

    def get_special_effects(self):
        return [self.acupoints[a].special_effect for a in self.activated
                if a in self.acupoints and self.acupoints[a].special_effect]

    # ---------- bug4: 走火入魔概率受速度/心境/连续时长影响 ----------

    def deviation_probability(self):
        prob = 0.01
        # 连续修炼越久风险越高（每小时+2%）
        prob += 0.02 * (self.continuous_cultivation_time / 3600.0)
        # 心境值越低风险越高
        prob += max(0.0, (100 - self.mental_state)) * 0.002
        # 突破失败等积累的额外风险
        prob += self.extra_deviation_risk
        return min(prob, 0.95)

    def get_qi_deviation(self, rng=random):
        return rng.random() < self.deviation_probability()

    # ---------- bug5: 走火入魔后属性下降+进度倒退 ----------

    def apply_qi_deviation(self):
        self.deviation_debuff_until = self._clock() + DEVIATION_DEBUFF_DURATION
        self.cultivation_exp *= (1 - DEVIATION_PROGRESS_LOSS)
        if self.active_art_id and self.active_art_id in self.arts:
            art = self.arts[self.active_art_id]
            art.exp *= (1 - DEVIATION_PROGRESS_LOSS)
        self.continuous_cultivation_time = 0
        self.extra_deviation_risk = 0.0
        return {
            "hp": -100,
            "attribute_debuff": DEVIATION_DEBUFF_FACTOR,
            "debuff_duration": DEVIATION_DEBUFF_DURATION,
            "progress_loss": DEVIATION_PROGRESS_LOSS,
        }

    def is_deviation_debuffed(self):
        return self._clock() < self.deviation_debuff_until

    # ---------- bug6: 心法切换冷却+修为按比例继承 ----------

    def switch_art(self, art_id):
        now = self._clock()
        if (self.last_switch_time is not None
                and now - self.last_switch_time < ART_SWITCH_COOLDOWN):
            return False
        old = self.arts.get(self.active_art_id) if self.active_art_id else None
        new = self.arts.get(art_id)
        if new is None:
            return False
        # bug7: 同类型心法互斥由 activate_art 保证；切换时修为按比例继承
        if old is not None and old.art_id != art_id:
            new.exp += old.exp * ART_EXP_INHERIT_RATIO
            old.exp = 0.0
        self.active_art_id = art_id
        self.last_switch_time = now
        return True

    # ---------- bug7: 同类型心法互斥 ----------

    def learn_art(self, art: CultivationArt):
        for existing in self.arts.values():
            if existing.art_type == art.art_type and existing.art_id != art.art_id:
                return False  # 同类型只能修炼一本
        self.arts[art.art_id] = art
        if self.active_art_id is None:
            self.active_art_id = art.art_id
        return True

    def can_cultivate_multiple(self):
        return False

    # ---------- bug8: 经验来源多元化+每日上限 ----------

    def get_exp(self, online_time, quest_exp=0, item_exp=0, dungeon_exp=0):
        total = online_time * 5 + quest_exp + item_exp + dungeon_exp
        return self._gain_exp(total)
