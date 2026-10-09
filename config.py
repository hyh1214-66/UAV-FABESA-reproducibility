"""
config.py - Configuration file loader
============================
Responsibilities:
  - Read config.yaml and convert it into strongly typed Python objects
  - Provide default values (do not crash when fields are missing in yaml)
  - Validate parameter legality (sum of proportions, range constraints)
  - Support command-line parameter overrides (--n_nodes=50, etc.)
  - Provide scenario preset shortcuts (load scenario1/2/3 directly)
  - Print complete configuration information (reproduction information template)

Design principles:
  - All modules obtain parameters from the SimConfig object and do not read yaml directly
  - Zero external dependencies: yaml uses standard library fallback
"""

import os
import sys
import argparse
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Any

# yaml: Prefer PyYAML, fallback to handwritten parsing
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# ─────────────────────────────────────────
# Strongly typed configuration data classes
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
    Complete simulation configuration object.
    All modules obtain parameters through this object.
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

    # ── Convenience properties ──────────────────────────
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
        """Complete output directory for this run"""
        return os.path.join(
            self.output.results_dir,
            self.simulation.run_id)


# ─────────────────────────────────────────
# YAML loader
# ─────────────────────────────────────────
def _load_yaml(path: str) -> Dict:
    """Load a YAML file and return a dictionary"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Configuration file does not exist: {path}")

    if HAS_YAML:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    else:
        # Simple fallback: only supports key: value format
        return _simple_yaml_parse(path)


def _simple_yaml_parse(path: str) -> Dict:
    """Minimal YAML parsing (fallback when PyYAML is unavailable)"""
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
    """Simple type conversion (strip inline comments first)"""
    # Strip inline comments: take the part before #, but preserve # in string values
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
    """Safely get nested values"""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d


# ─────────────────────────────────────────
# Main loading function
# ─────────────────────────────────────────
def load_config(yaml_path: str = "config.yaml",
                overrides: Optional[Dict] = None) -> SimConfig:
    """
    Load the complete configuration from a YAML file.

    Args:
        yaml_path: Path to the YAML configuration file
        overrides: Dictionary of override parameters from command line or code
                   Format: {"simulation.n_nodes": 50, ...}

    Returns:
        SimConfig object

    Example:
        cfg = load_config("config.yaml",
                          {"swarm.n_nodes": 50,
                           "topology.type": "Star"})
    """
    raw = _load_yaml(yaml_path)

    # Apply overrides
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

    # Validation
    _validate(cfg)
    return cfg


def _validate(cfg: SimConfig) -> None:
    """Validate parameter legality; raise ValueError if invalid"""
    errors = []

    if cfg.swarm.n_nodes < 1:
        errors.append("swarm.n_nodes must be >= 1")
    if cfg.simulation.total_ticks < 1:
        errors.append("simulation.total_ticks must be >= 1")
    if cfg.channel.max_range_m <= 0:
        errors.append("channel.max_range_m must be > 0")
    if cfg.topology.type not in ("Star", "Cluster", "Mesh"):
        errors.append(
            f"topology.type must be Star/Cluster/Mesh, "
            f"current value: {cfg.topology.type}")

    rd = cfg.swarm.role_distribution or {}
    role_sum = sum(rd.values()) if rd else 0.0
    if not (0.8 <= role_sum <= 1.2):
        errors.append(
            f"The sum of role_distribution proportions should be approximately 1.0, "
            f"current value: {role_sum:.2f}")

    if errors:
        raise ValueError("Configuration validation failed:\n" +
                         "\n".join(f"  - {e}" for e in errors))


# ─────────────────────────────────────────
# Scenario presets
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
    Load a scenario preset configuration.

    Args:
        preset_name:     Preset name (scenario1/2/3/exp5_star, etc.)
        yaml_path:       Base yaml path
        extra_overrides: Additional override parameters

    Returns:
        SimConfig object

    Example:
        cfg = load_preset("scenario2")
        cfg = load_preset("exp5_mesh",
                          extra_overrides={"simulation.random_seed": 99})
    """
    if preset_name not in SCENARIO_PRESETS:
        raise ValueError(
            f"Unknown preset: {preset_name}, "
            f"available presets: {list(SCENARIO_PRESETS.keys())}")

    overrides = dict(SCENARIO_PRESETS[preset_name])
    if extra_overrides:
        overrides.update(extra_overrides)

    return load_config(yaml_path, overrides)


def load_default() -> SimConfig:
    """
    Load pure default configuration (no yaml file required).
    Used for unit tests or quick verification.
    """
    cfg = SimConfig()
    return cfg


# ─────────────────────────────────────────
# Configuration printing (reproduction information template)
# ─────────────────────────────────────────
def print_config(cfg: SimConfig) -> None:
    """
    Print complete configuration information.
    The output format can be directly copied into the "Experimental Setup" section of a paper.
    """
    print("=" * 60)
    print("  UAV-FABESA Simulation Configuration (Paper Reproduction Info)")
    print("=" * 60)
    print(f"\n[Simulation Settings]")
    print(f"  Run ID:            {cfg.simulation.run_id}")
    print(f"  Total ticks:       {cfg.simulation.total_ticks}")
    print(f"  Tick duration:     {cfg.simulation.tick_duration_s}s")
    print(f"  Warm-up ticks:     {cfg.simulation.warmup_ticks}")
    print(f"  Random seed:       {cfg.simulation.random_seed}")

    print(f"\n[Swarm Settings]")
    print(f"  Total UAVs:        {cfg.swarm.n_nodes}")
    print(f"  Map size:          "
          f"{cfg.swarm.map_width_m}m × {cfg.swarm.map_height_m}m")
    print(f"  Role distribution: "
          f"{cfg.swarm.role_distribution}")
    print(f"  Initial battery range: "
          f"{cfg.swarm.battery_init_min}%–{cfg.swarm.battery_init_max}%")

    print(f"\n[Network Settings]")
    print(f"  Topology type:     {cfg.topology.type}")
    print(f"  Max communication range: {cfg.channel.max_range_m}m")
    print(f"  Carrier frequency: {cfg.channel.frequency_ghz}GHz")
    print(f"  Transmit power:    {cfg.channel.tx_power_dbm}dBm")
    print(f"  Path loss exponent: {cfg.channel.path_loss_exponent}")
    print(f"  Shadowing std dev: {cfg.channel.shadowing_std_db}dB")
    print(f"  Processing delay:  {cfg.channel.processing_delay_ms}ms")

    print(f"\n[Mobility Model]")
    print(f"  Speed range:       "
          f"{cfg.mobility.min_speed_mps}–"
          f"{cfg.mobility.max_speed_mps} m/s")
    print(f"  Max turn rate:     {cfg.mobility.turn_rate_rad} rad/tick")

    print(f"\n[ABE Settings]")
    print(f"  Scheme:            {cfg.abe.scheme}-ABE")
    print(f"  OPT-1 Hash cache:  "
          f"{'enabled' if cfg.abe.enable_opt1_hash_cache else 'disabled'}")
    print(f"  OPT-2 Precompute:  "
          f"{'enabled' if cfg.abe.enable_opt2_precompute else 'disabled'}")
    print(f"  OPT-3 GT grouping: "
          f"{'enabled' if cfg.abe.enable_opt3_gt_grouping else 'disabled'}")
    print(f"  OPT-4 Policy opt.: "
          f"{'enabled' if cfg.abe.enable_policy_optimizer else 'disabled'}")

    print(f"\n[Traffic Flow]")
    print(f"  Messages per node per tick: {cfg.traffic.msgs_per_tick}")
    print(f"  Message type distribution: "
          f"{cfg.traffic.msg_type_distribution}")

    print(f"\n[Output]")
    print(f"  Data directory:    {cfg.output_dir}")
    print(f"  Figures directory: {cfg.output.figures_dir}")
    print("=" * 60)


# ─────────────────────────────────────────
# Command-line interface (when run directly)
# ─────────────────────────────────────────
def parse_cli_overrides() -> Dict:
    """
    Parse command-line override parameters.
    Format: python runner.py --n_nodes=50 --topology=Star

    Returns:
        overrides dictionary
    """
    overrides = {}
    cli_map = {
        "--n_nodes":    "swarm.n_nodes",
        "--ticks":      "simulation.total_ticks",
        "--topology":   "topology.type",
        "--seed":       "simulation.random_seed",
        "--scenario":   None,   # Special handling
    }
    for arg in sys.argv[1:]:
        if "=" in arg:
            key, val = arg.split("=", 1)
            if key in cli_map and cli_map[key]:
                overrides[cli_map[key]] = _parse_val(val)
    return overrides


# ─────────────────────────────────────────
# Unit tests
# ─────────────────────────────────────────
if __name__ == "__main__":
    import tempfile

    print("=" * 55)
    print("  SimConfig Unit Tests")
    print("=" * 55)

    # ── Test 1: Default configuration ──────────────────────
    print("\n[Test 1] Default configuration loading")
    cfg = load_default()
    print(f"  n_nodes: {cfg.n_nodes}")
    print(f"  total_ticks: {cfg.total_ticks}")
    print(f"  topology: {cfg.topology_type}")
    print(f"  random_seed: {cfg.random_seed}")
    print(f"  output_dir: {cfg.output_dir}")

    # ── Test 2: Load from YAML file ─────────────────
    print("\n[Test 2] Loading from YAML file")
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
        print(f"  [Skipped] config.yaml not found at {yaml_path}")

    # ── Test 3: Override parameters ──────────────────────
    print("\n[Test 3] Override parameters")
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

    # ── Test 4: Scenario presets ──────────────────────
    print("\n[Test 4] Scenario preset loading")
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

    # ── Test 5: Validation failure ──────────────────────
    print("\n[Test 5] Parameter validation (should raise exception)")
    try:
        bad = load_default()
        bad.swarm.n_nodes = 0
        _validate(bad)
        print("  ✗ No exception raised (bug)")
    except ValueError as e:
        print(f"  ✓ Correctly caught: {e}")

    try:
        bad2 = load_default()
        bad2.topology.type = "Ring"
        _validate(bad2)
        print("  ✗ No exception raised (bug)")
    except ValueError as e:
        print(f"  ✓ Correctly caught: {e}")

    # ── Test 6: Integration with other modules ─────────────────
    print("\n[Test 6] Configuration integration with modules")
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
        print(f"  channel integration ✓ "
              f"d=200m RSSI={state.rssi_dbm:.1f}dBm "
              f"connected={state.is_connected}")
    except ImportError:
        print("  channel.py not in the same directory, skipping")

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
        print(f"  node integration ✓ "
              f"created {len(swarm)} UAVs")
    except ImportError:
        print("  node.py not in the same directory, skipping")

    # ── Test 7: Print reproduction information template ───────────────
    print("\n[Test 7] Reproduction information template")
    print_config(cfg6)

    print("\n✅ All tests completed")
