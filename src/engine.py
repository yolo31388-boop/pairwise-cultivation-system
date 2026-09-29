"""角色修炼内功 - 带9个bug"""
from dataclasses import dataclass, field
import random

@dataclass
class Acupoint:
    aid: str
    name: str
    is_core: bool
    prerequisites: list

class CultivationSystem:
    def __init__(self):
        self.acupoints: dict[str, Acupoint] = {}
        self.activated = set()
        self.player_level = 1
        self.mental_state = 100  # 心境值
        self.cultivation_exp = 0

    def cultivate(self, time, resources):
        # bug1: 只看时间
        self.cultivation_exp += time * 10
        return True

    def breakthrough(self, aid):
        ap = self.acupoints[aid]
        # bug2: 不看等级
        for pre in ap.prerequisites:
            if pre not in self.activated:
                return False
        # bug9: 失败无惩罚
        if random.random() < 0.5:
            self.activated.add(aid)
            return True
        return False

    def get_qi_deviation(self):
        # bug4: 随机
        return random.random() < 0.1

    def apply_qi_deviation(self):
        # bug5: 只扣血
        return {"hp": -100}

    def switch_art(self, art_id):
        # bug6: 无冷却
        return True

    def can_cultivate_multiple(self):
        # bug7: 可同时修炼
        return True

    def get_exp(self, online_time):
        # bug8: 只看在线
        return online_time * 5
