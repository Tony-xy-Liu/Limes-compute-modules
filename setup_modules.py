import os, sys
from pathlib import Path
import limes_x as lx
from limes_x import ComputeModule

assert len(sys.argv) > 1, f"no installation path given"
ref_dir = Path(sys.argv[1])
os.makedirs(ref_dir, exist_ok=True)

HERE = Path(os.path.dirname(__file__))

modules = []
modules += ComputeModule.LoadSet(HERE.joinpath("logistics"))
modules += ComputeModule.LoadSet(HERE.joinpath("metagenomics"))
modules += ComputeModule.LoadSet(HERE.joinpath("high_throughput_screening"))
modules = [m for m in modules if "dram" not in m.name]
wf = lx.Workflow(modules, ref_dir)
wf.Setup('singularity')
