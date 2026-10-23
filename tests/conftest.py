"""Regenerate synthetic-only fixtures for reproducible clean checkout tests."""
from scripts.create_synthetic_pdfs import main as create_samples


def pytest_sessionstart(session):
    create_samples()
