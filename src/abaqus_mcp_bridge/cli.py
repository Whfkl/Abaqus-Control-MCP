"""Small human-facing CLI helpers for bridge diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import sys

from .client import AbaqusBridgeClient

CANTILEVER_DEMO_CODE = r'''
import os

from abaqus import mdb, session
from abaqusConstants import *
import mesh
import regionToolset

workdir = 'd:/temp'
os.makedirs(workdir, exist_ok=True)
os.chdir(workdir)

model_name = 'MCP_Cantilever_Demo'
part_name = 'Beam_1000x100x100'

if model_name in mdb.models:
    del mdb.models[model_name]

model = mdb.Model(name=model_name)
sketch = model.ConstrainedSketch(name='beam_profile', sheetSize=200.0)
sketch.rectangle(point1=(0.0, 0.0), point2=(100.0, 100.0))
part = model.Part(name=part_name, dimensionality=THREE_D, type=DEFORMABLE_BODY)
part.BaseSolidExtrude(sketch=sketch, depth=1000.0)
del model.sketches['beam_profile']

material = model.Material(name='Steel_demo')
material.Elastic(table=((210000.0, 0.3),))
model.HomogeneousSolidSection(name='Steel_section', material='Steel_demo', thickness=None)
part.SectionAssignment(
    region=regionToolset.Region(cells=part.cells[:]),
    sectionName='Steel_section',
)

assembly = model.rootAssembly
assembly.DatumCsysByDefault(CARTESIAN)
assembly.Instance(name='Beam-1', part=part, dependent=ON)
instance = assembly.instances['Beam-1']

model.StaticStep(name='Tip_Load_Step', previous='Initial', description='MCP generated demo step')
fixed_face = instance.faces.findAt(((0.0, 50.0, 50.0),))
load_face = instance.faces.findAt(((1000.0, 50.0, 50.0),))
model.EncastreBC(
    name='Fixed_Left_End',
    createStepName='Initial',
    region=regionToolset.Region(faces=fixed_face),
)
assembly.Surface(name='Tip_Load_Surface', side1Faces=load_face)
model.Pressure(
    name='Tip_Pressure',
    createStepName='Tip_Load_Step',
    region=assembly.surfaces['Tip_Load_Surface'],
    magnitude=1.0,
)

part.seedPart(size=25.0, deviationFactor=0.1, minSizeFactor=0.1)
part.setElementType(
    regions=(part.cells[:],),
    elemTypes=(mesh.ElemType(elemCode=C3D8R, elemLibrary=STANDARD),),
)
part.generateMesh()

job_name = 'MCP_Cantilever_Demo_Job'
if job_name in mdb.jobs:
    del mdb.jobs[job_name]
mdb.Job(name=job_name, model=model_name, description='Created through Abaqus MCP bridge')

vp = session.viewports[session.currentViewportName]
vp.setValues(displayedObject=assembly)
vp.view.fitView()

result = {
    'model': model_name,
    'part': part_name,
    'job': job_name,
    'workdir': workdir,
    'nodes': len(part.nodes),
    'elements': len(part.elements),
    'models_now': list(mdb.models.keys()),
}
'''


def check_main() -> None:
    parser = argparse.ArgumentParser(
        description="Check the Abaqus MCP socket agent without starting an MCP stdio session."
    )
    parser.add_argument("--host", default=os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ABAQUS_MCP_PORT", "48152")))
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("ABAQUS_MCP_TIMEOUT", "10")),
    )
    parser.add_argument(
        "--code",
        default="import sys\nresult = {'python': sys.version.split()[0], 'ok': True}",
        help="Python code to execute in the Abaqus-side agent.",
    )
    args = parser.parse_args()

    client = AbaqusBridgeClient(host=args.host, port=args.port, timeout=args.timeout)
    try:
        ping = client.ping()
        execution = client.execute(args.code)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("Abaqus MCP agent is reachable.")
    print("Ping:")
    print(json.dumps(ping, ensure_ascii=False, indent=2))
    print("Execution:")
    print(json.dumps(execution, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    check_main()


def demo_cantilever_main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a small cantilever beam model in the connected Abaqus/CAE session."
    )
    parser.add_argument("--host", default=os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ABAQUS_MCP_PORT", "48152")))
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("ABAQUS_MCP_TIMEOUT", "60")),
    )
    args = parser.parse_args()

    client = AbaqusBridgeClient(host=args.host, port=args.port, timeout=args.timeout)
    try:
        result = client.execute(CANTILEVER_DEMO_CODE)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("Created MCP_Cantilever_Demo in Abaqus.")
    print(json.dumps(result, ensure_ascii=False, indent=2))
