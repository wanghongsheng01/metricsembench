from msb.baselines.naive_surface import NaiveSurfaceBaseline
from msb.baselines.dict_default import DictDefaultBaseline
from msb.baselines.always_refuse import AlwaysRefuseBaseline
from msb.baselines.always_clarify import AlwaysClarifyBaseline

BASELINES = {
    "naive_surface": NaiveSurfaceBaseline,
    "dict_default": DictDefaultBaseline,
    "always_refuse": AlwaysRefuseBaseline,
    "always_clarify": AlwaysClarifyBaseline,
}
