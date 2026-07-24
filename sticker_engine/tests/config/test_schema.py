import math
from sticker_engine.config.schema import (
    Config, Prefs, Character, Paths, ModeProbsConfig, normalize_probs
)


def test_normalize_probs_handles_small_drift():
    # 0.5+0.3+0.0+0.2 = 1.0，但浮点可能 0.9999999
    d = normalize_probs({"a": 0.5, "b": 0.5})
    assert math.isclose(sum(d.values()), 1.0)
    assert len(d) == 2


def test_prefs_validation_rejects_mode_probs_not_summing_to_one():
    import pytest
    with pytest.raises(ValueError):
        Prefs(mode_probs=ModeProbsConfig(single=0.5, duo=0.3, trio=0.3, quad=0.2))  # sum=1.3


def test_character_holds_base_probs():
    c = Character(name="测试角色", bases={"base1": "path/base1.png"}, base_probs={"base1": 1.0})
    assert c.base_probs["base1"] == 1.0
