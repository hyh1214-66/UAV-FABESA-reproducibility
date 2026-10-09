"""
config.py - 配置文件加载器
============================
负责：
  - 读取 config.yaml，转换为强类型 Python 对象
  - 提供默认值（yaml缺字段时不崩溃）
  - 校验参数合法性（比例之和、范围约束）
  - 支持命令行参数覆盖（--n_nodes=50 等）
  - 提供场景预设快捷方式（scenario1/2/3直接加载）
  - 打印完整配置信息（复现信息模板）

设计原则：
  - 所有模块从 SimConfig 对象取参数，不直接读yaml
  - 零外部依赖：yaml用标准库fallback
"""

import os
import sys
import argparse
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Any

# yaml：优先使用PyYAML，fallback到手写解析
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# ─────────────────────────────────────────
# 强类型配置数据类
# ─────────────────────────────────────────
@dataclass
class SimulationConfig:
    run_id: str             = "default"
    total_ticks: int        = 40
    tick_duration_s: float  = 1.0
    random_seed: int        = 42
    warmup_ticks: int       = 5
    verbose: bool           = False
    save_snapshot_interval: int = 10


@dataclass
class SwarmConfig:
    n_nodes: int            = 30
    map_width_m: float      = 600.0
    map_height_m: float     = 600.0
    role_distribution: Dict[str, float] = field(default_factory=lambda: {
        "COMMANDER": 0.10,
        "SCOUT":     0.50,
        "STRIKE":    0.30,
        "CARRIER":   0.10,
    })
    battery_init_min: float = 60.0
    battery_init_max: float = 100.0


@dataclass
class GCSConfig:
    gcs_id: str             = "GCS"
    position_x_m: float     = 0.0
    position_y_m: float     = 0.0
    timeout_ticks: int      = 5
    schedule_interval: int  = 5


@dataclass
class MobilityConfig:
    max_speed_mps: float    = 15.0
    min_speed_mps: float    = 5.0
    turn_rate_rad: float    = 0.3
    heading_noise: float    = 0.1


@dataclass
class ChannelConfig:
    tx_power_dbm: float     = 20.0
    frequency_ghz: float    = 2.4
    path_loss_exponent: float = 2.2
    ref_distance_m: float   = 1.0
    noise_power_dbm: float  = -90.0
    shadowing_std_db: float = 2.0
    max_range_m: float      = 400.0
    min_rssi_dbm: float     = -85.0
    max_plr: float          = 0.8
    processing_delay_ms: float = 1.0


@dataclass
class TopologyConfig:
    type: str               = "Mesh"    # Star / Cluster / Mesh
    update_every_tick: bool = True


@dataclass
class TrafficConfig:
    msgs_per_tick: int      = 3
    msg_type_distribution: Dict[str, float] = field(
        default_factory=lambda: {
            "RECON": 0.30, "CMD": 0.20,
            "SYNC":  0.20, "COORD": 0.15,
            "STATUS": 0.15,
        })


@dataclass
class ABEConfig:
    scheme: str                  = "CP"
    enable_opt1_hash_cache: bool = True
    enable_opt2_precompute: bool = True
    enable_opt3_gt_grouping: bool = True
    enable_policy_optimizer: bool = True
    n_encrypt_per_msg: int       = 1


@dataclass
class OutputConfig:
    results_dir: str        = "UAV_Results"
    figures_dir: str        = "UAV_Figures"
    logger_flush_interval: int = 50
    export_node_snapshots: bool = True
    export_link_records: bool   = True


@dataclass
class SimConfig:
    """
    完整仿真配置对象。
    所有模块通过此对象获取参数。
    """
    simulation: SimulationConfig = field(
        default_factory=SimulationConfig)
    swarm:      SwarmConfig      = field(
        default_factory=SwarmConfig)
    gcs:        GCSConfig        = field(
        default_factory=GCSConfig)
    mobility:   MobilityConfig   = field(
        default_factory=MobilityConfig)
    channel:    ChannelConfig    = field(
        default_factory=ChannelConfig)
    topology:   TopologyConfig   = field(
        default_factory=TopologyConfig)
    traffic:    TrafficConfig    = field(
        default_factory=TrafficConfig)
    abe:        ABEConfig        = field(
        default_factory=ABEConfig)
    output:     OutputConfig     = field(
        default_factory=OutputConfig)

    # ── 便捷属性 ──────────────────────────
    @property
    def run_id(self) -> str:
        return self.simulation.run_id

    @property
    def n_nodes(self) -> int:
        return self.swarm.n_nodes

    @property
    def total_ticks(self) -> int:
        return self.simulation.total_ticks

    @property
    def random_seed(self) -> int:
        return self.simulation.random_seed

    @property
    def topology_type(self) -> str:
        return self.topology.type

    @property
    def output_dir(self) -> str:
        """本次运行的完整输出目录"""
        return os.path.join(
            self.output.results_dir,
            self.simulation.run_id)


# ─────────────────────────────────────────
# YAML 加载器
# ─────────────────────────────────────────
def _load_yaml(path: str) -> Dict:
    """加载YAML文件，返回字典"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在: {path}")

    if HAS_YAML:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    else:
        # 简易fallback：只支持 key: value 格式
        return _simple_yaml_parse(path)


def _simple_yaml_parse(path: str) -> Dict:
    """极简YAML解析（无PyYAML时的fallback）"""
    result = {}
    current_section = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            if line and not line.startswith(" ") and ":" in line:
                key = line.split(":")[0].strip()
                val = line.split(":", 1)[1].strip()
                if val == "" or val is None:
                    current_section = key
                    result[key] = {}
                else:
                    result[key] = _parse_val(val)
                    current_section = None
            elif current_section and line.startswith("  "):
                stripped = line.strip()
                if ":" in stripped and not stripped.startswith("#"):
                    k, v = stripped.split(":", 1)
                    result[current_section][k.strip()] = \
                        _parse_val(v.strip())
    return result


def _parse_val(v: str) -> Any:
    """简单类型转换（先截断行内注释）"""
    # 截断行内注释：取 # 之前的部分，但保留字符串值中的 #
    if "#" in v:
        v = v.split("#")[0].strip()
    v = v.strip()
    if not v:
        return None
    if v.lower() == "true":  return True
    if v.lower() == "false": return False
    if v.lower() in ("null", "none", "~"): return None
    try: return int(v)
    except ValueError: pass
    try: return float(v)
    except ValueError: pass
    return v.strip('"\'')


def _get(d: Dict, *keys, default=None) -> Any:
    """安全嵌套取值"""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d


# ─────────────────────────────────────────
# 主加载函数
# ─────────────────────────────────────────
def load_config(yaml_path: str = "config.yaml",
                overrides: Optional[Dict] = None) -> SimConfig:
    """
    从YAML文件加载完整配置。

    Args:
        yaml_path: YAML配置文件路径
        overrides: 命令行或代码中的覆盖参数字典
                   格式：{"simulation.n_nodes": 50, ...}

    Returns:
        SimConfig 对象

    Example:
        cfg = load_config("config.yaml",
                          {"swarm.n_nodes": 50,
                           "topology.type": "Star"})
    """
    raw = _load_yaml(yaml_path)

    # 应用覆盖
    if overrides:
        for dot_key, val in overrides.items():
            parts = dot_key.split(".")
            d = raw
            for p in parts[:-1]:
                d = d.setdefault(p, {})
            d[parts[-1]] = val

    cfg = SimConfig()

    # ── simulation ─────────────────────────
    s = raw.get("simulation", {})
    cfg.simulation = SimulationConfig(
        run_id=_get(s, "run_id", default="default"),
        total_ticks=int(_get(s, "total_ticks", default=40)),
        tick_duration_s=float(_get(s, "tick_duration_s", default=1.0)),
        random_seed=int(_get(s, "random_seed", default=42)),
        warmup_ticks=int(_get(s, "warmup_ticks", default=5)),
        verbose=bool(_get(s, "verbose", default=False)),
        save_snapshot_interval=int(_get(
            s, "save_snapshot_interval", default=10)),
    )

    # ── swarm ──────────────────────────────
    sw = raw.get("swarm", {})
    role_dist = sw.get("role_distribution", None)
    if not isinstance(role_dist, dict) or not role_dist:
        role_dist = {
            "COMMANDER": 0.10, "SCOUT": 0.50,
            "STRIKE": 0.30, "CARRIER": 0.10}
    cfg.swarm = SwarmConfig(
        n_nodes=int(_get(sw, "n_nodes", default=30)),
        map_width_m=float(_get(sw, "map_width_m", default=600.0)),
        map_height_m=float(_get(sw, "map_height_m", default=600.0)),
        role_distribution=role_dist,
        battery_init_min=float(_get(sw, "battery_init_min", default=60.0)),
        battery_init_max=float(_get(sw, "battery_init_max", default=100.0)),
    )

    # ── gcs ────────────────────────────────
    g = raw.get("gcs", {})
    cfg.gcs = GCSConfig(
        gcs_id=str(_get(g, "gcs_id", default="GCS")),
        position_x_m=float(_get(g, "position_x_m", default=0.0)),
        position_y_m=float(_get(g, "position_y_m", default=0.0)),
        timeout_ticks=int(_get(g, "timeout_ticks", default=5)),
        schedule_interval=int(_get(g, "schedule_interval", default=5)),
    )

    # ── mobility ───────────────────────────
    m = raw.get("mobility", {})
    cfg.mobility = MobilityConfig(
        max_speed_mps=float(_get(m, "max_speed_mps", default=15.0)),
        min_speed_mps=float(_get(m, "min_speed_mps", default=5.0)),
        turn_rate_rad=float(_get(m, "turn_rate_rad", default=0.3)),
        heading_noise=float(_get(m, "heading_noise", default=0.1)),
    )

    # ── channel ────────────────────────────
    c = raw.get("channel", {})
    cfg.channel = ChannelConfig(
        tx_power_dbm=float(_get(c, "tx_power_dbm", default=20.0)),
        frequency_ghz=float(_get(c, "frequency_ghz", default=2.4)),
        path_loss_exponent=float(_get(
            c, "path_loss_exponent", default=2.2)),
        ref_distance_m=float(_get(c, "ref_distance_m", default=1.0)),
        noise_power_dbm=float(_get(c, "noise_power_dbm", default=-90.0)),
        shadowing_std_db=float(_get(c, "shadowing_std_db", default=2.0)),
        max_range_m=float(_get(c, "max_range_m", default=400.0)),
        min_rssi_dbm=float(_get(c, "min_rssi_dbm", default=-85.0)),
        max_plr=float(_get(c, "max_plr", default=0.8)),
        processing_delay_ms=float(_get(
            c, "processing_delay_ms", default=1.0)),
    )

    # ── topology ───────────────────────────
    t = raw.get("topology", {})
    cfg.topology = TopologyConfig(
        type=str(_get(t, "type", default="Mesh")),
        update_every_tick=bool(_get(
            t, "update_every_tick", default=True)),
    )

    # ── traffic ────────────────────────────
    tr = raw.get("traffic", {})
    msg_dist = tr.get("msg_type_distribution", None)
    if not isinstance(msg_dist, dict) or not msg_dist:
        msg_dist = {
            "RECON": 0.30, "CMD": 0.20, "SYNC": 0.20,
            "COORD": 0.15, "STATUS": 0.15}
    cfg.traffic = TrafficConfig(
        msgs_per_tick=int(_get(tr, "msgs_per_tick", default=3)),
        msg_type_distribution=msg_dist,
    )

    # ── abe ────────────────────────────────
    a = raw.get("abe", {})
    cfg.abe = ABEConfig(
        scheme=str(_get(a, "scheme", default="CP")),
        enable_opt1_hash_cache=bool(_get(
            a, "enable_opt1_hash_cache", default=True)),
        enable_opt2_precompute=bool(_get(
            a, "enable_opt2_precompute", default=True)),
        enable_opt3_gt_grouping=bool(_get(
            a, "enable_opt3_gt_grouping", default=True)),
        enable_policy_optimizer=bool(_get(
            a, "enable_policy_optimizer", default=True)),
        n_encrypt_per_msg=int(_get(
            a, "n_encrypt_per_msg", default=1)),
    )

    # ── output ─────────────────────────────
    o = raw.get("output", {})
    cfg.output = OutputConfig(
        results_dir=str(_get(o, "results_dir", default="UAV_Results")),
        figures_dir=str(_get(o, "figures_dir", default="UAV_Figures")),
        logger_flush_interval=int(_get(
            o, "logger_flush_interval", default=50)),
        export_node_snapshots=bool(_get(
            o, "export_node_snapshots", default=True)),
        export_link_records=bool(_get(
            o, "export_link_records", default=True)),
    )

    # 校验
    _validate(cfg)
    return cfg


def _validate(cfg: SimConfig) -> None:
    """参数合法性校验，不合法则抛出 ValueError"""
    errors = []

    if cfg.swarm.n_nodes < 1:
        errors.append("swarm.n_nodes 必须 >= 1")
    if cfg.simulation.total_ticks < 1:
        errors.append("simulation.total_ticks 必须 >= 1")
    if cfg.channel.max_range_m <= 0:
        errors.append("channel.max_range_m 必须 > 0")
    if cfg.topology.type not in ("Star", "Cluster", "Mesh"):
        errors.append(
            f"topology.type 必须为 Star/Cluster/Mesh，"
            f"当前值: {cfg.topology.type}")

    rd = cfg.swarm.role_distribution or {}
    role_sum = sum(rd.values()) if rd else 0.0
    if not (0.8 <= role_sum <= 1.2):
        errors.append(
            f"role_distribution 比例之和应约为1.0，"
            f"当前值: {role_sum:.2f}")

    if errors:
        raise ValueError("配置校验失败:\n" +
                         "\n".join(f"  - {e}" for e in errors))


# ─────────────────────────────────────────
# 场景预设
# ─────────────────────────────────────────
SCENARIO_PRESETS = {
    "scenario1": {
        "simulation.run_id":     "scenario1_recon",
        "simulation.total_ticks": 30,
        "swarm.n_nodes":         10,
        "topology.type":         "Mesh",
        "channel.max_range_m":   400.0,
    },
    "scenario2": {
        "simulation.run_id":     "scenario2_formation",
        "simulation.total_ticks": 40,
        "swarm.n_nodes":         30,
        "topology.type":         "Cluster",
        "channel.max_range_m":   400.0,
    },
    "scenario3": {
        "simulation.run_id":     "scenario3_dynamic",
        "simulation.total_ticks": 50,
        "swarm.n_nodes":         50,
        "topology.type":         "Star",
        "channel.max_range_m":   500.0,
    },
    "exp5_star": {
        "simulation.run_id":     "exp5_star",
        "simulation.total_ticks": 40,
        "swarm.n_nodes":         30,
        "topology.type":         "Star",
    },
    "exp5_cluster": {
        "simulation.run_id":     "exp5_cluster",
        "simulation.total_ticks": 40,
        "swarm.n_nodes":         30,
        "topology.type":         "Cluster",
    },
    "exp5_mesh": {
        "simulation.run_id":     "exp5_mesh",
        "simulation.total_ticks": 40,
        "swarm.n_nodes":         30,
        "topology.type":         "Mesh",
    },
}


def load_preset(preset_name: str,
                yaml_path: str = "config.yaml",
                extra_overrides: Optional[Dict] = None) -> SimConfig:
    """
    加载场景预设配置。

    Args:
        preset_name:     预设名称（scenario1/2/3/exp5_star等）
        yaml_path:       基础yaml路径
        extra_overrides: 额外覆盖参数

    Returns:
        SimConfig 对象

    Example:
        cfg = load_preset("scenario2")
        cfg = load_preset("exp5_mesh",
                          extra_overrides={"simulation.random_seed": 99})
    """
    if preset_name not in SCENARIO_PRESETS:
        raise ValueError(
            f"未知预设: {preset_name}，"
            f"可用预设: {list(SCENARIO_PRESETS.keys())}")

    overrides = dict(SCENARIO_PRESETS[preset_name])
    if extra_overrides:
        overrides.update(extra_overrides)

    return load_config(yaml_path, overrides)


def load_default() -> SimConfig:
    """
    加载纯默认配置（无需yaml文件）。
    单元测试或快速验证时使用。
    """
    cfg = SimConfig()
    return cfg


# ─────────────────────────────────────────
# 配置打印（复现信息模板）
# ─────────────────────────────────────────
def print_config(cfg: SimConfig) -> None:
    """
    打印完整配置信息。
    输出格式可直接复制进论文"实验设置"章节。
    """
    print("=" * 60)
    print("  UAV-FABESA 仿真配置（论文复现信息）")
    print("=" * 60)
    print(f"\n[仿真设置]")
    print(f"  Run ID:            {cfg.simulation.run_id}")
    print(f"  总tick数:          {cfg.simulation.total_ticks}")
    print(f"  每tick时长:        {cfg.simulation.tick_duration_s}s")
    print(f"  预热tick:          {cfg.simulation.warmup_ticks}")
    print(f"  随机种子:          {cfg.simulation.random_seed}")

    print(f"\n[集群设置]")
    print(f"  UAV总数:           {cfg.swarm.n_nodes}")
    print(f"  地图尺寸:          "
          f"{cfg.swarm.map_width_m}m × {cfg.swarm.map_height_m}m")
    print(f"  角色分布:          "
          f"{cfg.swarm.role_distribution}")
    print(f"  初始电量范围:      "
          f"{cfg.swarm.battery_init_min}%–{cfg.swarm.battery_init_max}%")

    print(f"\n[网络设置]")
    print(f"  拓扑类型:          {cfg.topology.type}")
    print(f"  最大通信距离:      {cfg.channel.max_range_m}m")
    print(f"  载波频率:          {cfg.channel.frequency_ghz}GHz")
    print(f"  发射功率:          {cfg.channel.tx_power_dbm}dBm")
    print(f"  路径损耗指数:      {cfg.channel.path_loss_exponent}")
    print(f"  阴影衰落标准差:    {cfg.channel.shadowing_std_db}dB")
    print(f"  处理时延:          {cfg.channel.processing_delay_ms}ms")

    print(f"\n[移动模型]")
    print(f"  速度范围:          "
          f"{cfg.mobility.min_speed_mps}–"
          f"{cfg.mobility.max_speed_mps} m/s")
    print(f"  最大转向速率:      {cfg.mobility.turn_rate_rad} rad/tick")

    print(f"\n[ABE设置]")
    print(f"  方案:              {cfg.abe.scheme}-ABE")
    print(f"  OPT-1 哈希缓存:   "
          f"{'开启' if cfg.abe.enable_opt1_hash_cache else '关闭'}")
    print(f"  OPT-2 预计算:     "
          f"{'开启' if cfg.abe.enable_opt2_precompute else '关闭'}")
    print(f"  OPT-3 GT分组:     "
          f"{'开启' if cfg.abe.enable_opt3_gt_grouping else '关闭'}")
    print(f"  OPT-4 策略优化:   "
          f"{'开启' if cfg.abe.enable_policy_optimizer else '关闭'}")

    print(f"\n[消息流]")
    print(f"  每tick每节点消息数: {cfg.traffic.msgs_per_tick}")
    print(f"  消息类型分布:      "
          f"{cfg.traffic.msg_type_distribution}")

    print(f"\n[输出]")
    print(f"  数据目录:          {cfg.output_dir}")
    print(f"  图表目录:          {cfg.output.figures_dir}")
    print("=" * 60)


# ─────────────────────────────────────────
# 命令行接口（直接运行时）
# ─────────────────────────────────────────
def parse_cli_overrides() -> Dict:
    """
    解析命令行覆盖参数。
    格式：python runner.py --n_nodes=50 --topology=Star

    Returns:
        overrides字典
    """
    overrides = {}
    cli_map = {
        "--n_nodes":    "swarm.n_nodes",
        "--ticks":      "simulation.total_ticks",
        "--topology":   "topology.type",
        "--seed":       "simulation.random_seed",
        "--scenario":   None,   # 特殊处理
    }
    for arg in sys.argv[1:]:
        if "=" in arg:
            key, val = arg.split("=", 1)
            if key in cli_map and cli_map[key]:
                overrides[cli_map[key]] = _parse_val(val)
    return overrides


# ─────────────────────────────────────────
# 单元测试
# ─────────────────────────────────────────
if __name__ == "__main__":
    import tempfile

    print("=" * 55)
    print("  SimConfig 单元测试")
    print("=" * 55)

    # ── 测试1：默认配置 ──────────────────────
    print("\n[测试1] 默认配置加载")
    cfg = load_default()
    print(f"  n_nodes: {cfg.n_nodes}")
    print(f"  total_ticks: {cfg.total_ticks}")
    print(f"  topology: {cfg.topology_type}")
    print(f"  random_seed: {cfg.random_seed}")
    print(f"  output_dir: {cfg.output_dir}")

    # ── 测试2：从YAML文件加载 ─────────────────
    print("\n[测试2] 从YAML文件加载")
    yaml_path = os.path.join(
        os.path.dirname(__file__), "config.yaml")
    if os.path.exists(yaml_path):
        cfg2 = load_config(yaml_path)
        print(f"  run_id: {cfg2.run_id}")
        print(f"  n_nodes: {cfg2.n_nodes}")
        print(f"  topology: {cfg2.topology_type}")
        print(f"  max_range_m: {cfg2.channel.max_range_m}")
        print(f"  OPT-1: {cfg2.abe.enable_opt1_hash_cache}")
    else:
        print(f"  [跳过] config.yaml不在 {yaml_path}")

    # ── 测试3：覆盖参数 ──────────────────────
    print("\n[测试3] 覆盖参数")
    overrides = {
        "swarm.n_nodes": 50,
        "topology.type": "Star",
        "simulation.random_seed": 99,
    }
    cfg3 = load_config(yaml_path, overrides) \
        if os.path.exists(yaml_path) \
        else load_default()
    for k, v in overrides.items():
        cfg3_val = {
            "swarm.n_nodes": cfg3.n_nodes,
            "topology.type": cfg3.topology_type,
            "simulation.random_seed": cfg3.random_seed,
        }[k]
        status = "✓" if str(cfg3_val) == str(v) else "✗"
        print(f"  {k}={v} → {cfg3_val} {status}")

    # ── 测试4：场景预设 ──────────────────────
    print("\n[测试4] 场景预设加载")
    for preset in ["scenario1", "scenario2", "scenario3"]:
        p = load_preset(preset, yaml_path) \
            if os.path.exists(yaml_path) \
            else load_preset(preset,
                             yaml_path="/dev/null"
                             if os.path.exists("/dev/null")
                             else yaml_path)
        print(f"  {preset}: n={p.n_nodes}, "
              f"ticks={p.total_ticks}, "
              f"topo={p.topology_type}, "
              f"id={p.run_id}")

    # ── 测试5：校验失败 ──────────────────────
    print("\n[测试5] 参数校验（应抛出异常）")
    try:
        bad = load_default()
        bad.swarm.n_nodes = 0
        _validate(bad)
        print("  ✗ 未抛出异常（bug）")
    except ValueError as e:
        print(f"  ✓ 正确捕获: {e}")

    try:
        bad2 = load_default()
        bad2.topology.type = "Ring"
        _validate(bad2)
        print("  ✗ 未抛出异常（bug）")
    except ValueError as e:
        print(f"  ✓ 正确捕获: {e}")

    # ── 测试6：与其他模块对接 ─────────────────
    print("\n[测试6] 配置对接各模块")
    cfg6 = load_default()

    # channel.py
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from channel import (WirelessChannel,
                             ChannelConfig as ChCfg)
        ch_cfg = ChCfg(
            tx_power_dbm=cfg6.channel.tx_power_dbm,
            frequency_ghz=cfg6.channel.frequency_ghz,
            path_loss_exponent=cfg6.channel.path_loss_exponent,
            max_range_m=cfg6.channel.max_range_m,
            shadowing_std_db=0.0,
            random_seed=cfg6.random_seed,
        )
        ch = WirelessChannel(ch_cfg)
        state = ch.evaluate("A",(0,0),"B",(200,0))
        print(f"  channel对接 ✓ "
              f"d=200m RSSI={state.rssi_dbm:.1f}dBm "
              f"connected={state.is_connected}")
    except ImportError:
        print("  channel.py不在同目录，跳过")

    # node.py
    try:
        from node import (create_uav_swarm,
                          MobilityConfig as MobCfg,
                          UAVRole)
        import random as _r
        _r.seed(cfg6.random_seed)
        role_map = {
            "COMMANDER": UAVRole.COMMANDER,
            "SCOUT":     UAVRole.SCOUT,
            "STRIKE":    UAVRole.STRIKE,
            "CARRIER":   UAVRole.CARRIER,
        }
        swarm = create_uav_swarm(
            n=cfg6.n_nodes,
            map_width=cfg6.swarm.map_width_m,
            map_height=cfg6.swarm.map_height_m,
            random_seed=cfg6.random_seed,
        )
        print(f"  node对接 ✓ "
              f"创建{len(swarm)}架UAV")
    except ImportError:
        print("  node.py不在同目录，跳过")

    # ── 测试7：打印复现信息模板 ───────────────
    print("\n[测试7] 复现信息模板")
    print_config(cfg6)

    print("\n✅ 所有测试完成")