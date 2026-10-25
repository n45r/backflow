"""Shared configuration: event split, paths, output step."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CQ_DATA = RAW / "cq-analysis" / "data"
TEMPLATE = RAW / "cq-analysis" / "swmm_model_template.inp"
EXPERIMENTS = RAW / "meta_v2" / "experiment_list.csv"
SITE_JSON = ROOT / "site" / "site.json"
PARAMS_JSON = ROOT / "site" / "params.json"
RUNS = ROOT / "runs"
EVALUATION = ROOT / "evaluation"

SPLIT = {"calibrate": 32, "holdout": 20, "dry": 21}
DT_S = 10

GAUGE_SOURCES = {"s3": "s3_h_us_maxbotix", "s6": "s6_h_us_maxbotix"}
INFLOW_SOURCE = "p1_q_mid_endress_logi"
# Events whose processed inflow file misses part of the rise; use the cq-analysis all_ series.
INFLOW_USE_ALL = {20}

WET_M = 0.005
WET_SUSTAIN_S = 30
