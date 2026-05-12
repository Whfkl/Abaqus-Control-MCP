# Abaqus MCP + Skills Integration

## Available MCP Tools

This project provides an MCP bridge to control a live Abaqus/CAE session. The following tools can be called via the MCP server:

- `abaqus_execute_python(code)` — Execute arbitrary Python code inside the connected Abaqus kernel
- `abaqus_ping()` — Check if the Abaqus-side agent is reachable
- `abaqus_get_model_info()` — Get detailed model/part/step/boundary condition info
- `abaqus_list_jobs()` — List all analysis jobs
- `abaqus_submit_job(job_name)` — Submit and wait for an analysis job
- `abaqus_get_odb_info(odb_path)` — Open an ODB and return metadata
- `abaqus_get_field_output(odb_path, step_name, ...)` — Extract field output from ODB
- `abaqus_get_history_output(odb_path, step_name, ...)` — Extract history output from ODB
- `abaqus_capture_viewport(viewport_name, format)` — Capture viewport image

## Abaqus Python Script Style Guide

When generating Abaqus Python scripts to execute via `abaqus_execute_python`, follow these conventions:

1. Use `from abaqus import *` and `from abaqusConstants import *` for readability
2. To return results to the caller, set a variable named `result` with a dict (this will be serialized and returned as JSON)
3. Use `mdb` for the model database and `session` for the viewport/session objects
4. Wrap code in try/except and return error details in the `result` dict

Example pattern:
```python
from abaqus import *
from abaqusConstants import *
try:
    model = mdb.models['Model-1']
    # ... your analysis commands ...
    result = {'success': True, 'message': 'Done'}
except Exception as e:
    import traceback
    result = {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}
```

## External Abaqus Skills Library

An external Abaqus skills library is available at:
https://github.com/jasonanewcoder/abaqus_skills

This library contains two categories of reference materials:

### 1. Abaqus Script Control Skills (Python)
Located in the `abaqus_scriptcontrol_skills/` subtree:
- `general/SKILL.md` + `reference/modeling.md`, `material.md`, `step.md`, `bc_load.md`, `mesh.md`, `job.md`
- `static/SKILL.md` + `reference/linear.md`, `nonlinear.md`
- `fatigue/SKILL.md`
- `xfem/SKILL.md`
- `thermal/SKILL.md`
- `composite/SKILL.md`

Each SKILL.md contains code snippets; each reference/ contains detailed API documentation and best practices.

### 2. Abaqus Subroutine Skills (Fortran)
Located in the `abaqus_subroutine_skills/` subtree:
- `SKILL.md` — overview and quick reference
- `reference/material/umat_elastic.md`, `umat_plasticity.md`, `vumat_elastic.md`
- `reference/load/dload_moving.md`
- `reference/boundary/disp_control.md`
- `reference/field/usdfld_spatial.md`
- `reference/initial/sigini_stress.md`
- `reference/thermal/hetval_heat.md`
- `reference/friction/fric_contact.md`
- `reference/element/uel_spring.md`
- `official_examples/` — Abaqus official example Fortran codes

## Workflow: How to Use Both Together

1. **User describes analysis goal in natural language**
2. **Refer to the Abaqus Skills Library** for appropriate code templates and best practices
3. **Generate the Python script** following the skills templates
4. **Execute the script in Abaqus** via `abaqus_execute_python()`
5. **Submit the analysis job** via `abaqus_submit_job()`
6. **Extract results** via `abaqus_get_field_output()` or `abaqus_get_history_output()`
7. **Report back to the user** with the results

Example workflow for a static analysis:
1. Get modeling code from general/SKILL.md (modeling reference)
2. Get material definitions from general/reference/material.md
3. Get static analysis settings from static/SKILL.md
4. Generate the complete Python script
5. Call abaqus_execute_python(code) to run it
6. Call abaqus_submit_job('Job-1') to analyze
7. Call abaqus_get_field_output('Job-1.odb', output_variable='S') to get stress results
