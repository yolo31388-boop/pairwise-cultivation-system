"""修炼系统测试：覆盖九个走火入魔级bug的修复"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.engine import (
    Acupoint, AcupointType, Art, CultivationSystem,
    CULTIVATION_RESOURCE_COST, DAILY_EXP_CAP,
    DEVIATION_DEBUFF_DURATION, DEVIATION_EXP_LOSS_RATIO,
    SWITCH_COOLDOWN, SWITCH_INHERIT_RATIO,
)


def make_system():
    cs = CultivationSystem()
    cs.resources = {"spirit_stone": 1000, "pill": 100}
    return cs


class TestCultivateResources:
    def test_cultivate_consumes_time_and_resources(self):
        cs = make_system()
        assert cs.cultivate(2) is True
        assert cs.resources["spirit_stone"] == 1000 - 2 * CULTIVATION_RESOURCE_COST["spirit_stone"]
        assert cs.resources["pill"] == 100 - 2 * CULTIVATION_RESOURCE_COST["pill"]
        assert cs.cultivation_exp > 0

    def test_cultivate_pauses_without_resources(self):
        cs = make_system()
        cs.resources = {"spirit_stone": 0, "pill": 0}
        assert cs.cultivate(2) is False
        assert cs.cultivation_exp == 0


class TestBreakthrough:
    def test_breakthrough_checks_level_and_prerequisites(self):
        cs = make_system()
        cs.base_success_rate = 1.0
        cs.acupoints = {
            "a1": Acupoint("a1", "关元", False, [], required_level=1),
            "a2": Acupoint("a2", "气海", False, ["a1"], required_level=10),
        }
        cs.player_level = 1
        assert cs.breakthrough("a2") is False  # 前置未通且等级不足
        assert cs.breakthrough("a1") is True
        assert cs.breakthrough("a2") is False  # 前置已通但等级不足
        cs.player_level = 10
        assert cs.breakthrough("a2") is True

    def test_breakthrough_failure_costs_materials_and_adds_risk(self):
        cs = make_system()
        cs.base_success_rate = 0.0  # 必定失败
        cs.acupoints = {
            "a1": Acupoint("a1", "关元", False, [], required_level=1,
                           breakthrough_cost={"spirit_stone": 100}),
        }
        before = cs.resources["spirit_stone"]
        risk_before = cs.deviation_risk
        assert cs.breakthrough("a1") is False
        lost = before - cs.resources["spirit_stone"]
        assert 0 < lost < 100  # 材料有损耗但非全额
        assert cs.deviation_risk > risk_before


class TestAcupointTypes:
    def test_core_normal_hidden_bonus_and_special_effect(self):
        cs = make_system()
        cs.acupoints = {
            "n1": Acupoint("n1", "普通穴", False, []),
            "c1": Acupoint("c1", "核心穴", True, [], special_effect="暴击率+5%"),
            "h1": Acupoint("h1", "隐藏穴", False, [], hidden=True),
        }
        cs.activated = {"n1", "c1", "h1"}
        core, normal, hidden = (cs.acupoints[k] for k in ("c1", "n1", "h1"))
        assert core.atype is AcupointType.CORE
        assert hidden.atype is AcupointType.HIDDEN
        assert normal.atype is AcupointType.NORMAL
        assert core.bonus > hidden.bonus > normal.bonus
        assert "暴击率+5%" in cs.special_effects()
        assert cs.total_bonus() == core.bonus + hidden.bonus + normal.bonus


class TestQiDeviation:
    def test_probability_scales_with_speed_mental_and_duration(self):
        cs = make_system()
        base = cs.qi_deviation_probability()
        cs.cultivation_speed = 3.0
        assert cs.qi_deviation_probability() > base  # 修炼过快
        cs.cultivation_speed = 1.0
        cs.mental_state = 10
        assert cs.qi_deviation_probability() > base  # 心境值低
        cs.mental_state = 100
        cs.continuous_time = 24
        assert cs.qi_deviation_probability() > base  # 连续修炼过久

    def test_deviation_debuffs_attributes_and_rolls_back_exp(self):
        cs = make_system()
        cs.cultivation_exp = 1000
        result = cs.apply_qi_deviation(now=1000.0)
        assert cs.cultivation_exp == int(1000 * (1 - DEVIATION_EXP_LOSS_RATIO))
        assert result["exp_lost"] == 1000 - cs.cultivation_exp
        assert cs.attribute_multiplier(now=1000.0) == 0.9
        assert cs.attribute_multiplier(now=1000.0 + DEVIATION_DEBUFF_DURATION + 1) == 1.0


class TestSwitchArt:
    def test_switch_has_cooldown_and_inherits_exp(self):
        cs = make_system()
        cs.active_art = "fire"
        cs.last_switch_time = 0.0
        cs.cultivation_exp = 1000
        assert cs.switch_art("water", now=SWITCH_COOLDOWN / 2) is False  # 冷却中
        assert cs.active_art == "fire"
        assert cs.cultivation_exp == 1000
        assert cs.switch_art("water", now=SWITCH_COOLDOWN + 1) is True
        assert cs.active_art == "water"
        assert cs.cultivation_exp == int(1000 * SWITCH_INHERIT_RATIO)


class TestArtMutex:
    def test_same_type_arts_are_mutually_exclusive(self):
        cs = make_system()
        cs.arts = {
            "fire1": Art("fire1", "烈火功", "attack"),
            "fire2": Art("fire2", "炎阳诀", "attack"),
            "shield": Art("shield", "铁布衫", "defense"),
        }
        cs.active_art = "fire1"
        assert cs.can_cultivate_art("fire2") is False  # 同类型互斥
        assert cs.can_cultivate_art("shield") is True  # 不同类型可切换
        assert cs.can_cultivate_multiple() is False


class TestExpSources:
    def test_multiple_sources_and_daily_cap(self):
        cs = make_system()
        assert cs.gain_exp("online", 100, now=0.0) == 100
        assert cs.gain_exp("quest", 200, now=0.0) == 200
        assert cs.gain_exp("item", 300, now=0.0) == 300
        assert cs.gain_exp("dungeon", 400, now=0.0) == 400
        assert cs.cultivation_exp == 1000
        assert cs.gain_exp("quest", DAILY_EXP_CAP, now=0.0) == DAILY_EXP_CAP - 1000  # 触及上限
        assert cs.gain_exp("quest", 100, now=0.0) == 0  # 超出上限不再获得
        assert cs.gain_exp("quest", 100, now=90000.0) == 100  # 次日重置
        assert cs.gain_exp("hack", 100, now=90000.0) == 0  # 非法来源
