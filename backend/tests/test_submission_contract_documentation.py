"""The handoff document must match the machine-readable submission schema."""

from app.services.submission_data_contract import WORKBOOK_CONTRACTS, contract_fingerprint
from scripts.render_submission_contract import DOCUMENT, updated_document


def test_submission_contract_documentation_is_generated_from_current_schema():
    document = DOCUMENT.read_bytes().decode("utf-8")
    assert document == updated_document(document)
    assert f"`{contract_fingerprint()}`" in document
    assert len(WORKBOOK_CONTRACTS) == 12
