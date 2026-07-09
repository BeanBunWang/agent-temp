from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from local_agent.tools import ToolExecutor


def write_minimal_xlsx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as workbook:
        workbook.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        workbook.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>scene</t></si><si><t>summary</t></si><si><t>客服</t></si><si><t>自动答疑</t></si>
</sst>""",
        )
        workbook.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
    <row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c></row>
  </sheetData>
</worksheet>""",
        )


class ToolExecutorTest(unittest.TestCase):
    def test_write_and_read_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tools = ToolExecutor(Path(tmp))
            write = tools.execute("write_file", {"path": "a/b.txt", "content": "hello"})
            self.assertEqual(write.status, "success")
            read = tools.execute("read_file", {"path": "a/b.txt"})
            self.assertEqual(read.status, "success")
            self.assertIn("hello", read.content)

    def test_path_escape_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tools = ToolExecutor(Path(tmp))
            result = tools.execute("read_file", {"path": "../secret.txt"})
            self.assertEqual(result.status, "denied")

    def test_high_risk_shell_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tools = ToolExecutor(Path(tmp))
            result = tools.execute("run_shell", {"command": "rm -rf ."})
            self.assertEqual(result.status, "denied")

    def test_large_file_result_is_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "large.txt").write_text("x" * 5000, encoding="utf-8")
            tools = ToolExecutor(Path(tmp))
            result = tools.execute("read_file", {"path": "large.txt"})
            self.assertEqual(result.status, "success")
            self.assertTrue(result.structured_data["truncated"])
            self.assertIn("truncated", result.content)

    def test_xlsx_preview_is_textual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "sample.xlsx")
            write_minimal_xlsx(path)
            tools = ToolExecutor(Path(tmp))
            result = tools.execute("read_file", {"path": "sample.xlsx"})
            self.assertEqual(result.status, "success")
            self.assertEqual(result.structured_data["file_type"], "xlsx")
            self.assertIn("Sheet: Sheet1", result.content)
            self.assertIn("scene | summary", result.content)

    def test_allowed_shell_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "x.txt").write_text("hello", encoding="utf-8")
            tools = ToolExecutor(Path(tmp))
            result = tools.execute("run_shell", {"command": "ls ."})
            self.assertEqual(result.status, "success")
            self.assertIn("x.txt", result.content)

    def test_shell_timeout_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tools = ToolExecutor(Path(tmp))
            result = tools.execute("run_shell", {"command": "sleep 2", "timeout": 1})
            self.assertEqual(result.status, "timeout")
            self.assertTrue(result.retryable)


if __name__ == "__main__":
    unittest.main()
