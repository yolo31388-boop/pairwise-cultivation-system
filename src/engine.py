"""角色修炼内功系统"""
from dataclasses import dataclass, field
from enum import Enum
import random
import time as _time


class AcupointType(Enum):
    NORMAL = "normal"
    CORE = "core"
    HIDDEN = "hidden"


# 不同类型穴位的属性加成：核心 > 隐藏 > 普通
ACUPOINT_BONUS = {
    AcupointType.NORMAL: 5,
    AcupointType.CORE: 20,
    AcupointType.HIDDEN: 10,
}

# 修炼资源消耗（每小时）：灵石 + 丹药
CULTIVATION_RESOURCE_COST = {"spirit_stone": 10, "pill": 1}
CULTIVATION_EXP_PER_HOUR = 10

SWITCH_COOLDOWN = 3600.0                 # 心法切换冷却：1小时
SWITCH_INHERIT_RATIO = 0.7               # 切换后修为继承比例
DEVIATION_DEBUFF_RATIO = 0.10            # 走火入魔属性下降 10%
DEVIATION_DEBUFF_DURATION = 24 * 3600.0  # 属性下降持续 24 小时
DEVIATION_EXP_LOSS_RATIO = 0.05          # 走火入魔修炼进度倒退 5%
DAILY_EXP_CAP = 10000                    # 每日修炼经验上限
EXP_SOURCES = ("online", "quest", "item", "dungeon")
FAILURE_MATERIAL_LOSS_RATIO = 0.5        # 突破失败材料损耗比例
FAILURE_RISK_INCREMENT = 0.05            # 突破失败走火入魔风险增量


@dataclass
class Acupoint:
    aid: str
    name: str
    is_core: bool
    prerequisites: list
    required_level: int = 1
    hidden: bool = False
    special_effect: str = ""
    breakthrough_cost: dict = field(default_factory=dict)

    @property
    def atype(self):
        if self.is_core:
            return AcupointType.CORE
        if self.hidden:
            return AcupointType.HIDDEN
        return AcupointType.NORMAL

    @property
    def bonus(self):
        return ACUPOINT_BONUS[self.atype]


@dataclass
class Art:
    art_id: str
    name: str
    art_type: str  # 如 attack / defense / support


class CultivationSystem:
    def __init__(self):
        self.acupoints: dict[str, Acupoint] = {}
        self.activated = set()
        self.player_level = 1
        self.mental_state = 100  # 心境值
        self.cultivation_exp = 0
        self.resources = {"spirit_stone": 0, "pill": 0}
        self.cultivation_speed = 1.0   # 修炼速度倍率
        self.continuous_time = 0.0     # 连续修炼时长
        self.deviation_risk = 0.0      # 突破失败累积的走火入魔风险
        self.debuff_until = 0.0        # 走火入魔属性下降截止时间
        self.arts: dict[str, Art] = {}
        self.active_art = None
        self.last_switch_time = None
        self.daily_exp = 0
        self.daily_exp_day = None
        self.base_success_rate = 0.6
        self.rng = random.Random()

    def _now(self, now):
        return _time.time() if now is None else now

    # 修复bug1：修炼同时消耗时间与资源（灵石/丹药），资源不足则暂停
    def cultivate(self, duration, resources=None):
        pool = self.resources if resources is None else resources
        affordable = duration
        for name, per_hour in CULTIVATION_RESOURCE_COST.items():
            affordable = min(affordable, pool.get(name, 0) / per_hour)
        if affordable <= 0:
            return False
        for name, per_hour in CULTIVATION_RESOURCE_COST.items():
            pool[name] = pool.get(name, 0) - per_hour * affordable
        self.cultivation_exp += int(affordable * CULTIVATION_EXP_PER_HOUR * self.cultivation_speed)
        self.continuous_time += affordable
        return affordable >= duration  # 资源只够部分时长时返回 False 表示暂停

    def rest(self):
        self.continuous_time = 0.0

    # 修复bug2/bug9：突破同时检查前置穴位链与角色等级；
    # 失败损耗一半材料且增加走火入魔风险
    def breakthrough(self, aid, now=None):
        ap = self.acupoints.get(aid)
        if ap is None:
            return False
        if self.player_level < ap.required_level:
            return False
        for pre in ap.prerequisites:
            if pre not in self.activated:
                return False
        for name, amount in ap.breakthrough_cost.items():
            if self.resources.get(name, 0) < amount:
                return False
        if self.rng.random() < self.base_success_rate:
            for name, amount in ap.breakthrough_cost.items():
                self.resources[name] -= amount
            self.activated.add(aid)
            return True
        for name, amount in ap.breakthrough_cost.items():
            self.resources[name] -= int(amount * FAILURE_MATERIAL_LOSS_RATIO)
        self.deviation_risk += FAILURE_RISK_INCREMENT
        return False

    # 修复bug3：核心/普通/隐藏穴位加成不同，核心穴位附带特殊效果
    def total_bonus(self, now=None):
        base = sum(self.acupoints[aid].bonus for aid in self.activated)
        return base * self.attribute_multiplier(now)

    def special_effects(self):
        return [
            self.acupoints[aid].special_effect
            for aid in self.activated
            if self.acupoints[aid].atype is AcupointType.CORE
            and self.acupoints[aid].special_effect
        ]

    def attribute_multiplier(self, now=None):
        if self._now(now) < self.debuff_until:
            return 1.0 - DEVIATION_DEBUFF_RATIO
        return 1.0

    # 修复bug4：走火入魔概率受修炼速度、心境值、连续修炼时长影响
    def qi_deviation_probability(self):
        prob = 0.01
        prob += max(0.0, self.cultivation_speed - 1.0) * 0.1      # 修炼过快
        prob += max(0, 50 - self.mental_state) / 50 * 0.2         # 心境值低
        prob += min(self.continuous_time / 24.0, 1.0) * 0.1       # 连续修炼过久
        prob += self.deviation_risk                               # 突破失败累积
        return min(prob, 0.95)

    def get_qi_deviation(self):
        return self.rng.random() < self.qi_deviation_probability()

    # 修复bug5：走火入魔后属性下降（24小时-10%）且修炼进度倒退5%
    def apply_qi_deviation(self, now=None):
        now = self._now(now)
        exp_lost = int(self.cultivation_exp * DEVIATION_EXP_LOSS_RATIO)
        self.cultivation_exp -= exp_lost
        self.debuff_until = now + DEVIATION_DEBUFF_DURATION
        self.continuous_time = 0.0
        return {
            "attribute_multiplier": 1.0 - DEVIATION_DEBUFF_RATIO,
            "debuff_until": self.debuff_until,
            "exp_lost": exp_lost,
        }

    # 修复bug6：心法切换有1小时冷却，切换后修为按比例继承
    def switch_art(self, art_id, now=None):
        now = self._now(now)
        if (self.active_art is not None and self.last_switch_time is not None
                and now - self.last_switch_time < SWITCH_COOLDOWN):
            return False
        if self.active_art is not None:
            self.cultivation_exp = int(self.cultivation_exp * SWITCH_INHERIT_RATIO)
        self.active_art = art_id
        self.last_switch_time = now
        return True

    # 修复bug7：同类型心法互斥，只能修炼一本
    def can_cultivate_art(self, art_id):
        art = self.arts.get(art_id)
        if art is None:
            return False
        if self.active_art is None or self.active_art == art_id:
            return True
        active = self.arts.get(self.active_art)
        return active is None or active.art_type != art.art_type

    def can_cultivate_multiple(self):
        return False

    # 修复bug8：经验来源多元化（在线/任务/道具/副本），有每日上限
    def gain_exp(self, source, amount, now=None):
        if source not in EXP_SOURCES or amount <= 0:
            return 0
        day = int(self._now(now) // 86400)
        if day != self.daily_exp_day:
            self.daily_exp_day = day
            self.daily_exp = 0
        gained = min(amount, max(0, DAILY_EXP_CAP - self.daily_exp))
        self.daily_exp += gained
        self.cultivation_exp += gained
        return gained

    def get_exp(self, online_time):
        return self.gain_exp("online", int(online_time * 5))
