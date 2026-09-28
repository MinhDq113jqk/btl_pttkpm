"""Keep the published workbook schema matrix aligned with the machine contract."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.services.submission_data_contract import WORKBOOK_CONTRACTS


ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "documents" / "greencity-project" / "DATA_ONBOARDING_CONTRACT.md"
START = "## 3. Tóm tắt 12 workbook"
END = "## 5. Trạng thái quyết định owner và cổng nguồn"


def _cell(value: object) -> str:
    if value is None or value == () or value == "":
        return "—"
    if isinstance(value, (tuple, list)):
        value = ", ".join(str(item) for item in value)
    return str(value).replace("|", r"\|").replace("\n", " ")


def render_schema_matrix() -> str:
    lines = [
        START,
        "",
        "Bảng tóm tắt và ma trận bên dưới được sinh từ `WORKBOOK_CONTRACTS` bằng "
        "`python -m scripts.render_submission_contract --write`. "
        "Dùng `--check` để phát hiện tài liệu lệch contract trước khi đóng gói.",
        "",
        "| Workbook | Version | Sheet | Dòng | Natural key | Target entities | Canonical input còn thiếu |",
        "|---|---|---|---:|---|---|---|",
    ]
    for workbook in WORKBOOK_CONTRACTS:
        lines.append(
            "| " + " | ".join((
                f"`{workbook.file_name}`",
                f"`{workbook.schema_version}`",
                f"`{workbook.data_sheet}` + `{workbook.guide_sheet}`",
                str(workbook.expected_data_rows),
                _cell(tuple(f"`{part}`" for part in workbook.natural_key)),
                _cell(tuple(f"`{part}`" for part in workbook.target_entities)),
                _cell(tuple(f"`{part}`" for part in workbook.canonical_inputs_missing)),
            )) + " |"
        )
    lines.extend((
        "",
        "## 4. Field-level schema matrix",
        "",
        "Header là tên cột và thứ tự canonical. Required là bắt buộc ở preflight; "
        "Reference là khóa resolve/oracle; Decision liên kết quyết định FCS-01/FCS-04/FCS-05.",
        "",
    ))
    for workbook in WORKBOOK_CONTRACTS:
        lines.extend((
            f"### `{workbook.file_name}`",
            "",
            f"- Schema version: `{workbook.schema_version}`",
            f"- Sheets: `{workbook.data_sheet}` (data), `{workbook.guide_sheet}` (guidance)",
            f"- Expected data rows: `{workbook.expected_data_rows}`",
            "- Natural key: " + _cell(tuple(f"`{part}`" for part in workbook.natural_key)),
            "- Target entities: " + _cell(tuple(f"`{part}`" for part in workbook.target_entities)),
            "- Canonical inputs missing: " + _cell(tuple(f"`{part}`" for part in workbook.canonical_inputs_missing)),
            "- Canonical header order: " + _cell(tuple(f"`{field.source_name}`" for field in workbook.fields)),
            "",
            "| Header | Type | Required | Disposition | Target | Reference | Rule | Decision |",
            "|---|---|---|---|---|---|---|---|",
        ))
        for field in workbook.fields:
            rule = field.rule
            if field.enum:
                rule += " Enum: " + ", ".join(field.enum) + "."
            lines.append(
                "| " + " | ".join((
                    f"`{field.source_name}`",
                    f"`{field.value_type}`",
                    "yes" if field.required else "no",
                    f"`{field.disposition}`",
                    _cell(field.target),
                    _cell(field.reference),
                    _cell(rule),
                    f"`{_cell(field.decision_ref)}`",
                )) + " |"
            )
        lines.append("")
    return "\n".join(lines)


def updated_document(original: str) -> str:
    newline = "\r\n" if "\r\n" in original else "\n"
    start = original.index(START)
    end = original.index(END, start)
    generated = render_schema_matrix().replace("\n", newline)
    return original[:start] + generated + newline + original[end:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    original = DOCUMENT.read_bytes().decode("utf-8")
    updated = updated_document(original)
    if args.check:
        status = "PASS" if original == updated else "FAIL"
        print(f"FCS03_CONTRACT_DOC={status}")
        return 0 if status == "PASS" else 1
    DOCUMENT.write_bytes(updated.encode("utf-8"))
    print("FCS03_CONTRACT_DOC=UPDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
