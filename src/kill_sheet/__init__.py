"""Kill Sheet: surface-stack well-control kill sheet calculations.

Training and cross-check aid only. The rig's approved kill sheet and the
well-site supervisor govern. Verify every input.
"""

from .core import (
    BARITE_PPG,
    EXAMPLE_CASE,
    G,
    InputError,
    classify_influx,
    compute,
    influx_fill,
    kmw_round_up,
    to_imperial,
)
from .parse import parse_text

__all__ = [
    "BARITE_PPG", "EXAMPLE_CASE", "G", "InputError", "classify_influx", "compute", "influx_fill",
    "kmw_round_up", "parse_text", "to_imperial",
]
__version__ = "0.1.0"
