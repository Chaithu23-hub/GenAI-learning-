from fastapi.testclient import TestClient

from legal_rag.interfaces.http.app import create_app
from tests.fakes.documents import FakePDFTextExtractor


def test_empty_extracted_pdf_is_rejected_before_any_corpus_write(container):
    container.pdf_extractor = FakePDFTextExtractor(text=" \n\t ")
    original_files = set(container.settings.docs_dir.iterdir())
    original_index = container.vector_store.get_all()
    app = create_app(container.settings)
    app.state.container = container
    response = TestClient(app).post(
        "/api/upload",
        headers={"X-API-Key": "test-admin-key"},
        files={"files": ("blank.pdf", b"synthetic pdf bytes", "application/pdf")},
    )
    assert set(container.settings.docs_dir.iterdir()) == original_files
    assert container.vector_store.get_all() == original_index
    assert response.status_code == 422
