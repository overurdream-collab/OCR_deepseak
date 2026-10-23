"""Verify the real-model path never silently falls back to CPU OCR."""
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

from src.pilot import DeepSeekOCR2


def test_no_cuda_fails_explicitly_without_installing_torch():
    """CPU CI should not need a gigabyte-scale PyTorch installation."""
    fake_torch = ModuleType("torch")
    fake_torch.cuda = SimpleNamespace(is_available=lambda: False)
    with patch.dict(sys.modules, {"torch": fake_torch}):
        with pytest.raises(RuntimeError, match="no CUDA GPU available"):
            DeepSeekOCR2()


def test_missing_torch_reports_setup_requirement():
    """Missing optional GPU dependencies should be reported, not masked."""
    with patch.dict(sys.modules, {"torch": None}):
        with pytest.raises(RuntimeError, match="PyTorch not installed"):
            DeepSeekOCR2()
