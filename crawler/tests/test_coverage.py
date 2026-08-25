import math
from crawler.discovery.coverage import chao1, saturation


def test_chao1_classic_formula_with_doubletons():
    # observed=10, f1=4 singletons, f2=2 doubletons -> 10 + 16/4 = 14
    assert chao1(10, 4, 2) == 14.0


def test_chao1_bias_corrected_when_no_doubletons():
    # f2==0 -> observed + f1*(f1-1)/2 = 5 + 3*2/2 = 8
    assert chao1(5, 3, 0) == 8.0


def test_chao1_fully_saturated_when_no_singletons():
    # no singletons -> estimate equals observed (nothing new expected)
    assert chao1(10, 0, 0) == 10.0


def test_chao1_zero_observed_is_zero():
    assert chao1(0, 0, 0) == 0.0


def test_saturation_is_ratio_clamped():
    assert math.isclose(saturation(10, 4, 2), 10 / 14)
    assert saturation(10, 0, 0) == 1.0     # nothing left to find
    assert saturation(0, 0, 0) == 1.0      # empty corpus -> treat as saturated
