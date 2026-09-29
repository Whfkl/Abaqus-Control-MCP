"""Regression checks that do not require an Abaqus installation."""

import ast
import asyncio
import base64
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import Client
from abaqus_mcp_bridge import server

TOOL_NAMES = ["ping", "run_python", "set_workdir", "monitor_job_status", "inspect_odb", "capture_viewport"]


PLUGIN_PATH = Path(__file__).resolve().parents[1] / "abaqus_mcp_bridge" / "gui_plugin.py"


def kernel_wrapper():
    """Load only the pure wrapper generator; abaqusGui is unavailable here."""
    source = ast.parse(PLUGIN_PATH.read_text(encoding="utf-8"))
    function = next(
        node for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name == "_kernel_wrapper"
    )
    scope = {"base64": base64}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(PLUGIN_PATH), "exec"), scope)
    return scope["_kernel_wrapper"]


class KernelExecutionTests(unittest.TestCase):
    def test_result_is_per_call_and_deep_error_line_is_reported(self):
        wrapper = kernel_wrapper()
        kernel_scope = {"mdb": object(), "session": object()}
        with tempfile.TemporaryDirectory() as folder:
            def execute(code, name):
                path = Path(folder) / name
                exec(wrapper(code, str(path)), kernel_scope)
                return json.loads(path.read_text(encoding="utf-8"))["result"]

            self.assertEqual(execute("result = 123", "first.json")["return_value"], 123)
            self.assertIsNone(execute("value = 456", "second.json")["return_value"])
            self.assertEqual(execute("value", "third.json")["return_value"], 456)
            error = execute("def broken():\n    raise ValueError('bad')\nbroken()", "error.json")
            self.assertFalse(error["ok"])
            self.assertEqual(error["error_line"], 2)
            self.assertIn("ValueError: bad", error["traceback"])
            self.assertNotIn("During handling of the above exception", error["traceback"])
            self.assertTrue(any(frame["line"] == 2 for frame in error["frames"]))

    def test_nonserializable_result_does_not_poison_next_call(self):
        wrapper = kernel_wrapper()
        kernel_scope = {"mdb": object(), "session": object()}
        with tempfile.TemporaryDirectory() as folder:
            def execute(code, name):
                path = Path(folder) / name
                exec(wrapper(code, str(path), name), kernel_scope)
                return json.loads(path.read_text(encoding="utf-8"))["result"]

            first = execute("class Bad:\n    def __repr__(self): raise RuntimeError('repr failed')\nresult = Bad()", "one")
            second = execute("print('second only')", "two")
            self.assertEqual(first["executionId"], "one")
            self.assertIn("repr failed", first["return_value"]["repr"])
            self.assertEqual(second["executionId"], "two")
            self.assertIsNone(second["return_value"])
            self.assertEqual(second["stdout"], "second only\n")

    def test_function_defined_in_prior_call_reports_its_own_source(self):
        wrapper = kernel_wrapper()
        kernel_scope = {"mdb": object(), "session": object()}
        with tempfile.TemporaryDirectory() as folder:
            def execute(code, name):
                path = Path(folder) / name
                exec(wrapper(code, str(path), name), kernel_scope)
                return json.loads(path.read_text(encoding="utf-8"))["result"]

            execute("def build():\n    raise ValueError('inside build')", "definition")
            failure = execute("print(build())", "invocation")
            self.assertFalse(failure["ok"])
            self.assertEqual(failure["primary_frame"], {"file": "<abaqus-mcp:definition>", "line": 2, "function": "build"})
            self.assertIn("raise ValueError('inside build')", failure["code_excerpt"])

    def test_external_script_uses_its_actual_failure_line_and_local_keys(self):
        wrapper = kernel_wrapper()
        kernel_scope = {"mdb": object(), "session": object()}
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "build_model.py"
            script.write_text("def build():\n    parts = {'ConcreteCylinder': 1}\n    return parts['ConcreteCylindr']\nbuild()\n", encoding="utf-8")
            response = Path(folder) / "response.json"
            code = "exec(compile(open(%r, encoding='utf-8').read(), %r, 'exec'), globals())" % (str(script), str(script))
            exec(wrapper(code, str(response), "external"), kernel_scope)
            failure = json.loads(response.read_text(encoding="utf-8"))["result"]
            self.assertFalse(failure["ok"])
            self.assertEqual(failure["primary_frame"], {"file": str(script), "line": 3, "function": "build"})
            self.assertEqual(failure["code_line"], "return parts['ConcreteCylindr']")
            self.assertEqual(failure["recovery"]["possible_keys"], ["ConcreteCylinder"])
            self.assertNotIn("available_keys_sample", failure["recovery"])

            library_script = Path(folder) / "postprocess.py"
            library_script.write_text("import json\njson.dumps(object())\n", encoding="utf-8")
            library_response = Path(folder) / "library.json"
            library_code = "exec(compile(open(%r).read(), %r, 'exec'), globals())" % (str(library_script), str(library_script))
            exec(wrapper(library_code, str(library_response), "library"), kernel_scope)
            library_failure = json.loads(library_response.read_text(encoding="utf-8"))["result"]
            self.assertEqual(library_failure["primary_frame"]["file"], str(library_script))
            self.assertEqual(library_failure["primary_frame"]["line"], 2)

            syntax_script = Path(folder) / "syntax.py"
            syntax_script.write_text("def broken(:\n    pass\n", encoding="utf-8")
            syntax_response = Path(folder) / "syntax.json"
            syntax_code = "exec(compile(open(%r).read(), %r, 'exec'), globals())" % (str(syntax_script), str(syntax_script))
            exec(wrapper(syntax_code, str(syntax_response), "syntax"), kernel_scope)
            syntax_failure = json.loads(syntax_response.read_text(encoding="utf-8"))["result"]
            self.assertEqual(syntax_failure["primary_frame"]["file"], str(syntax_script))
            self.assertEqual(syntax_failure["primary_frame"]["line"], 1)

    def test_typo_hints_cover_methods_names_and_builtin_keywords(self):
        wrapper = kernel_wrapper()
        kernel_scope = {"mdb": object(), "session": object()}
        with tempfile.TemporaryDirectory() as folder:
            def execute(code, name):
                path = Path(folder) / name
                exec(wrapper(code, str(path), name), kernel_scope)
                return json.loads(path.read_text(encoding="utf-8"))["result"]

            method = execute("class Part:\n    def generateMesh(self): pass\npart = Part()\npart.genrateMesh()", "method")
            self.assertIn("generateMesh", method["recovery"]["possible_members"])
            name = execute("pritn('hello')", "name")
            self.assertIn("print", name["recovery"]["possible_names"])
            keyword = execute("sorted([2, 1], revers=True)", "keyword")
            self.assertIn("reverse", keyword["recovery"]["possible_keywords"])

    def test_plugin_log_is_off_by_default_and_bounded_in_debug_mode(self):
        source = ast.parse(PLUGIN_PATH.read_text(encoding="utf-8"))
        functions = [node for node in source.body
                     if isinstance(node, ast.FunctionDef) and node.name in ("_log", "_clear_old_log")]
        with tempfile.TemporaryDirectory() as folder:
            log_path = Path(folder) / "abaqus_mcp_gui_plugin.log"
            log_path.write_text("old log", encoding="utf-8")
            scope = {"os": os, "time": time, "threading": threading, "LOG_PATH": str(log_path),
                     "_DEBUG_LOG": False, "_LOG_LIMIT": 20, "_LOG_LOCK": threading.Lock()}
            exec(compile(ast.Module(body=functions, type_ignores=[]), str(PLUGIN_PATH), "exec"), scope)
            scope["_clear_old_log"]()
            scope["_log"]("no default log")
            self.assertFalse(log_path.exists())
            scope["_DEBUG_LOG"] = True
            scope["_log"]("first entry")
            scope["_log"]("second entry")
            self.assertTrue(log_path.exists())
            self.assertTrue(Path(str(log_path) + ".1").exists())


class ServerTests(unittest.TestCase):
    def test_six_original_tools_are_exposed(self):
        tools = asyncio.run(server.mcp.list_tools())
        self.assertEqual([tool.name for tool in tools], TOOL_NAMES)
        self.assertEqual(tools[0].input_schema["properties"], {})
        self.assertEqual(list(tools[1].input_schema["properties"]), ["code"])

    def test_execution_error_is_structured_tool_error(self):
        class FakeBridge:
            def execute(self, code):
                return {
                    "requestId": "request-1",
                    "ok": False,
                    "core_error": "ValueError: bad",
                    "error_type": "builtins.ValueError",
                    "error_line": 2,
                    "code_excerpt": "  1 | pass\n>> 2 | raise ValueError('bad')",
                    "recovery": {"call_target": "ValueError"},
                    "stdout": "before failure\n",
                    "traceback": "long redundant traceback" * 200,
                }

        with patch.object(server, "_bridge", return_value=FakeBridge()):
            result = asyncio.run(server.run_python("raise ValueError('bad')"))
        self.assertTrue(result.is_error)
        self.assertEqual(result.structured_content["executionId"], "request-1")
        self.assertEqual(result.structured_content["error"]["at"]["line"], 2)
        self.assertIn("raise ValueError", result.structured_content["error"]["at"]["code"])
        self.assertEqual(result.structured_content["error"]["suggestions"]["call_target"], "ValueError")
        self.assertNotIn("requestId", result.structured_content)
        self.assertNotIn("traceback", result.structured_content["error"])
        self.assertLess(len(result.content[0].text), 500)
        self.assertEqual(json.loads(result.content[0].text), result.structured_content)

    def test_mcp_client_discovers_and_calls_both_tools(self):
        class FakeBridge:
            def ping(self):
                return {"requestId": "ping-1", "pid": 42}

            def execute(self, code):
                return {"requestId": "run-1", "ok": True, "return_value": 7}

        async def check():
            with patch.object(server, "_bridge", return_value=FakeBridge()):
                async with Client(server.mcp) as client:
                    self.assertEqual(client.server_info.version, "2.0.0")
                    self.assertEqual(client.protocol_version, "2026-07-28")
                    listed = await client.list_tools()
                    self.assertEqual([tool.name for tool in listed.tools], TOOL_NAMES)
                    ping_result = await client.call_tool("ping")
                    run_result = await client.call_tool("run_python", {"code": "3 + 4"})
                    self.assertTrue(ping_result.structured_content["ok"])
                    self.assertEqual(run_result.structured_content["value"], 7)
                    self.assertEqual(run_result.structured_content["executionId"], "run-1")

        asyncio.run(check())

    def test_capture_uses_image_content_without_base64_in_metadata(self):
        class FakeBridge:
            def execute(self, code):
                return {"executionId": "capture-1", "ok": True, "return_value": {
                    "viewport": "Viewport: 1", "format": "png", "width": 1, "height": 1,
                    "sizeBytes": 3, "savedPath": "", "imageBase64": base64.b64encode(b"png").decode("ascii")}}

        with patch.object(server, "_bridge", return_value=FakeBridge()):
            response = asyncio.run(server.capture_viewport())
        self.assertFalse(response.is_error)
        self.assertEqual(response.structured_content["executionId"], "capture-1")
        self.assertNotIn("imageBase64", response.structured_content)
        self.assertEqual(response.content[1].type, "image")


class JobStateTests(unittest.TestCase):
    def test_old_completion_marker_does_not_override_running_cae_job(self):
        class Job:
            status = "RUNNING"

        fake_abaqus = types.ModuleType("abaqus")
        fake_abaqus.mdb = types.SimpleNamespace(jobs={"Probe": Job()})
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                Path("Probe.log").write_text("Abaqus JOB Probe COMPLETED\n", encoding="utf-8")
                Path("Probe.sta").write_text("1  16  1  0  0\nTHE ANALYSIS HAS COMPLETED SUCCESSFULLY\n", encoding="utf-8")
                Path("Probe.dat").write_text("0 ERROR MESSAGES\n0 WARNING MESSAGES\n", encoding="utf-8")
                Path("Probe.lck").write_text("active", encoding="utf-8")
                scope = {}
                with patch.dict(sys.modules, {"abaqus": fake_abaqus}):
                    exec(server._code(server._JOB_CODE, job_name="Probe", terminate=False, since=None), scope)
                result = scope["result"]
                self.assertEqual(result["state"], "UNKNOWN")
                self.assertFalse(result["terminal"])
                self.assertEqual(result["errors"], [])
                self.assertEqual(result["warnings"], [])
            finally:
                os.chdir(previous)

    def test_kill_request_requires_terminal_evidence(self):
        class Job:
            status = "RUNNING"

            def kill(self):
                self.status = "TERMINATED"

        fake_abaqus = types.ModuleType("abaqus")
        fake_abaqus.mdb = types.SimpleNamespace(jobs={"Probe": Job()})
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                Path("Probe.lck").write_text("still running", encoding="utf-8")
                scope = {}
                with patch.dict(sys.modules, {"abaqus": fake_abaqus}):
                    exec(server._code(server._JOB_CODE, job_name="Probe", terminate=True, since=None), scope)
                result = scope["result"]
                self.assertTrue(result["termination"]["requested"])
                self.assertFalse(result["termination"]["confirmed"])
                self.assertEqual(result["state"], "UNKNOWN")
            finally:
                os.chdir(previous)

    def test_file_only_completion_needs_a_run_start_time(self):
        fake_abaqus = types.ModuleType("abaqus")
        fake_abaqus.mdb = types.SimpleNamespace(jobs={})
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                Path("Probe.log").write_text("Abaqus JOB Probe COMPLETED\n", encoding="utf-8")
                with patch.dict(sys.modules, {"abaqus": fake_abaqus}):
                    unknown = {}
                    exec(server._code(server._JOB_CODE, job_name="Probe", terminate=False, since=None), unknown)
                    known = {}
                    exec(server._code(server._JOB_CODE, job_name="Probe", terminate=False, since=1.0), known)
                self.assertEqual(unknown["result"]["state"], "UNKNOWN")
                self.assertEqual(unknown["result"]["fileState"], "COMPLETED")
                self.assertEqual(known["result"]["state"], "COMPLETED")
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
