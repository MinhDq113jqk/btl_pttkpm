"""The handoff document must match the machine-readable submission schema."""

import pytest

from app.services.submission_data_contract import WORKBOOK_CONTRACTS, contract_fingerprint
from scripts.render_submission_contract import DOCUMENT, START, END, updated_document


@pytest.mark.skipif(not DOCUMENT.is_file(), reason='Optional handoff document is absent from this checkout')
def test_submission_contract_documentation_is_generated_from_current_schema():
    document = DOCUMENT.read_bytes().decode("utf-8")
    assert document == updated_document(document)
    assert f"`{contract_fingerprint()}`" in document
    assert len(WORKBOOK_CONTRACTS) == 12


def test_submission_contract_renderer_preserves_context_and_current_workbook_schema():
    template = '# Workbook contract\n\n' + START + '\nOld matrix\n\n' + END + '\nOwner decisions\n'
    document = updated_document(template)
    assert document == updated_document(document)
    assert document.startswith('# Workbook contract\n\n')
    assert document.endswith(END + '\nOwner decisions\n')
    assert 'Old matrix' not in document
    assert len(WORKBOOK_CONTRACTS) == 12
    for workbook in WORKBOOK_CONTRACTS:
        assert f'### `{workbook.file_name}`' in document
        for field in workbook.fields:
            assert f'| `{field.source_name}` | `{field.value_type}` |' in document
