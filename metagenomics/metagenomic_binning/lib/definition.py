import os
from pathlib import Path
from limes_x import ModuleBuilder, Item, JobContext, JobResult

# split this...

SAMPLE      = Item('sample')
READS       = Item('metagenomic raw reads')
READ_TYPE   = Item('metagenomic read type')
ASM         = Item('metagenomic assembly')

BIN         = Item('metagenomic bin')
MWR_WS      = Item('metawrap binning work')
MWR_REFINE_WS = Item('metawrap refine work')
CHECKM      = Item('metagnomic bins checkm results')

CONTAINER   = 'metawrap.sif'
CHECKM_DB   = 'checkm_data_2015_01_16'
CHECKM_SRC  = 'checkm_src'

def example_procedure(context: JobContext) -> JobResult:
    COMPLETION, CONTAMINATION = 50, 5
    make_fail = lambda msg: JobResult(
        code = 1,
        error_message = msg,
    )

    params = context.params
    ref = params.reference_folder
    binds = [
        f"{ref}/{CHECKM_SRC}:/usr/local/lib/python2.7/site-packages/checkm",
        f"{ref}/{CHECKM_DB}:/checkm_db",
        f"./:/ws",
    ]

    reads = context.manifest[READS]
    if isinstance(reads, Path): reads = [reads]

    rtype = context.manifest[READ_TYPE]
    assert isinstance(rtype, str), f"invalid read type: {rtype}"
    _, read_type = rtype.split(':')

    name = context.manifest[SAMPLE]
    assert isinstance(name, str), f"name wasn't a str: {name}"

    asm = context.manifest[ASM]
    assert isinstance(asm, Path), f"assembly wasn't a path: {name}"

    special_read_type = { # switch
        "interleaved": lambda: "--interleaved",
        "single_end": lambda: "--single-end",
        "long_read": lambda: "--single-end",
    }.get(read_type, lambda: "")()
    container = params.reference_folder.joinpath(CONTAINER)

    #################################################################################
    # bin

    metawrap_out = context.output_folder.joinpath(f'{name}_metawrap')
    code = context.shell(f"""\
        singularity exec -B {",".join(binds)} {container} \
        metaWRAP binning -t {params.threads} -m {params.mem_gb} --maxbin2 --metabat2 --concoct {special_read_type} \
            -a /ws/{asm} \
            -o /ws/{metawrap_out} \
            {" ".join(str(r) for r in reads)}
    """)
    if code != 0: return make_fail("metawrap binning failed")
    
    #################################################################################
    # refine

    refine_out = context.output_folder.joinpath(f'{name}_metawrap_refine')
    refined_bins = refine_out.joinpath(f'metawrap_{COMPLETION}_{CONTAMINATION}_bins')
    bin_folders = [f for f in os.listdir(metawrap_out) if '_bins' in f and len(os.listdir(f'{metawrap_out}/{f}'))>0]
    ABC = 'ABC'
    if len(bin_folders)>1:
        code = context.shell(f"""\
            singularity exec -B {",".join(binds)} {container} \
            metaWRAP bin_refinement -t {params.threads} -m {params.mem_gb} --quick \
                -c {COMPLETION} -x {CONTAMINATION} \
                {" ".join([f'-{ABC[i]} /ws/{metawrap_out}/{f}' for i, f in enumerate(bin_folders)])} \
                -o /ws/{refine_out}
        """)
    elif len(bin_folders)==1:
        code = context.shell(f"""\
            mkdir -p {refine_out}
            cp -R {metawrap_out}/{bin_folders[0]} {refined_bins}
        """)
    else:
        return make_fail("metawrap binning produced no bins")
    if code != 0: return make_fail("metawrap bin refinement failed")

    original_bins = os.listdir(refined_bins)
    renamed_bins = [f'{name}_bin{i:02}.fa' for i, _ in enumerate(original_bins)]
    renamed_bin_paths = [context.output_folder.joinpath(b) for b in renamed_bins]
    with open(refine_out.joinpath('bin_rename_mapping.tsv'), 'w') as f:
        for ori, new in zip(original_bins, renamed_bins):
            f.write(f'{ori}\t{new}\n')
    NL = '\n'
    context.shell(f"""\
        {NL.join(f"cp {refined_bins.joinpath(o)} {n}" for o, n in zip(original_bins, renamed_bin_paths))}
    """)

    #################################################################################
    # checkm

    checkm_out = context.output_folder.joinpath(f'{name}_checkm_on_bins')
    context.shell(f"""\
        singularity exec -B {",".join(binds)} {CONTAINER} \
            checkm lineage_wf -t {params.threads} -x fa \
            /ws/{refine_out}/metawrap_{COMPLETION}_{CONTAMINATION}_bins/ \
            /ws/{checkm_out}
    """)
    if not os.path.exists(checkm_out):
        context.shell(f"""\
            mkdir -p {checkm_out}
            touch {checkm_out}/CHECKM_FAILED
        """)

    return JobResult(
        exit_code = 0,
        manifest = {
            BIN: renamed_bin_paths,
            MWR_WS: metawrap_out,
            MWR_REFINE_WS: refine_out,
        },
    )

MODULE = ModuleBuilder()\
    .SetProcedure(example_procedure)\
    .AddInput(SAMPLE,       groupby=SAMPLE)\
    .AddInput(READS,        groupby=SAMPLE)\
    .AddInput(READ_TYPE,    groupby=SAMPLE)\
    .AddInput(ASM,          groupby=SAMPLE)\
    .PromiseOutput(BIN)\
    .PromiseOutput(CHECKM)\
    .PromiseOutput(MWR_WS)\
    .PromiseOutput(MWR_REFINE_WS)\
    .Requires({CONTAINER})\
    .Requires({CHECKM_DB})\
    .Requires({CHECKM_SRC})\
    .SuggestedResources(threads=2, memory_gb=48)\
    .SetHome(__file__)\
    .Build()
