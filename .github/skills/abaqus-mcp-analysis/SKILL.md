---
name: abaqus-mcp-analysis
description: "Use when: generating Abaqus Python scripts to run via MCP; performing finite element modeling, analysis, job submission, or post-processing through Abaqus MCP bridge; extracting ODB results; referencing abaqus_skills library templates"
---

# Abaqus MCP Analysis Skill

## Overview

This skill combines AI-powered Abaqus analysis code generation with the **Abaqus-Control-MCP** bridge and the **abaqus_skills** knowledge library. It enables natural-language-driven FEA workflows.

## Architecture

```
You (User) → Copilot Agent → abaqus_execute_python() → MCP Server → TCP → Abaqus/CAE GUI Plugin → Abaqus Kernel
```

## External Skills Library

The **abaqus_skills** library (https://github.com/jasonanewcoder/abaqus_skills) contains two modules:

### 1. Script Control Skills (Python)
Organized as Claude Code Skills:

| Module | Path | Contents |
|--------|------|----------|
| **General** | `abaqus_scriptcontrol_skills/general/` | Modeling, materials, steps, BCs, mesh, job submission |
| **Static** | `abaqus_scriptcontrol_skills/static/` | Linear & nonlinear static analysis |
| **Fatigue** | `abaqus_scriptcontrol_skills/fatigue/` | High-cycle fatigue (S-N curve) |
| **XFEM** | `abaqus_scriptcontrol_skills/xfem/` | Crack initiation & propagation |
| **Thermal** | `abaqus_scriptcontrol_skills/thermal/` | Steady/transient heat transfer, thermal stress |
| **Composite** | `abaqus_scriptcontrol_skills/composite/` | Laminate definition, failure criteria |

Each module has:
- `SKILL.md` — Overview, function list, code snippets
- `reference/*.md` — Detailed API docs, templates, best practices

### 2. Subroutine Skills (Fortran)
Located in `abaqus_subroutine_skills/`:
- **SKILL.md** — Overview of UMAT, VUMAT, DLOAD, USDFLD, etc.
- **reference/** — Detailed templates with theory and code
- **official_examples/** — Ready-to-compile Fortran codes

## Available MCP Tools

| Tool | Purpose |
|------|---------|
| `abaqus_ping()` | Check connection to Abaqus |
| `abaqus_execute_python(code)` | Execute arbitrary Python in Abaqus kernel |
| `abaqus_get_model_info()` | Get model parts, materials, steps, BCs |
| `abaqus_list_jobs()` | List all defined jobs |
| `abaqus_submit_job(name)` | Submit job and wait for completion |
| `abaqus_get_odb_info(path)` | Open ODB, return step/frame/variable metadata |
| `abaqus_get_field_output(path, ...)` | Extract field output (stress, strain, U, etc.) |
| `abaqus_get_history_output(path, ...)` | Extract history output (time-history curves) |
| `abaqus_capture_viewport(name, fmt)` | Capture viewport image as base64 |

## Code Generation Patterns

### Pattern 1: Full Analysis Workflow

```python
from abaqus import *
from abaqusConstants import *
try:
    # === 1. MODEL ===
    model = mdb.models['Model-1']
    
    # === 2. PART === (from general/SKILL.md modeling)
    sketch = model.ConstrainedSketch(name='__profile__', sheetSize=200.0)
    sketch.rectangle(point1=(0.0, 0.0), point2=(10.0, 10.0))
    part = model.Part(name='Plate', dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=1.0)
    del model.sketches['__profile__']
    
    # === 3. MATERIAL === (from general/reference/material.md)
    material = model.Material(name='Steel')
    material.Elastic(table=((210e3, 0.3),))
    
    # === 4. SECTION ===
    section = model.HomogeneousSolidSection(name='Section', material='Steel')
    part.SectionAssignment(region=(part.cells,), sectionName='Section')
    
    # === 5. ASSEMBLY ===
    assembly = model.rootAssembly
    assembly.Instance(name='Plate-1', part=part, dependent=ON)
    
    # === 6. STEP === (from static/reference/linear.md)
    model.StaticStep(name='Load-Step', previous='Initial', nlgeom=OFF)
    
    # === 7. BC & LOAD === (from general/reference/bc_load.md)
    instance = assembly.instances['Plate-1']
    # ... apply BCs and loads ...
    
    # === 8. MESH === (from general/reference/mesh.md)
    # ... mesh generation ...
    
    # === 9. JOB ===
    job = mdb.Job(name='Analysis', model='Model-1')
    job.submit()
    job.waitForCompletion()
    
    result = {'success': True, 'odb': 'Analysis.odb', 'status': str(job.status)}
except Exception as e:
    import traceback
    result = {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}
```

### Pattern 2: Return Data to Caller

Set the `result` variable to return any data structure:

```python
result = {
    'stress_max': 350.2,
    'displacement_max': 0.045,
    'elements': 1200,
    'nodes': 5600
}
```

### Pattern 3: Post-processing ODB

```python
# After odb is opened with abaqus_get_odb_info:
# Extract stress field
field_result = await abaqus_get_field_output(
    odb_path='Analysis.odb',
    step_name='Load-Step',
    output_variable='S',
    frame_index=-1
)
```

## Workflow

1. **Understand** the user's FEA goal (geometry, materials, loads, desired outputs)
2. **Reference** the abaqus_skills library for appropriate code templates
3. **Generate** a complete Python script following the patterns above
4. **Execute** via `abaqus_execute_python(code)`
5. **Submit** job via `abaqus_submit_job(name)`
6. **Extract** results via `abaqus_get_field_output()`
7. **Report** findings to the user
