"""Verify that the DeepSeek mode never falls back to a different engine."""
from unittest.mock import patch

import pytest

from src.pilot import DeepSeekOCR2


def test_no_cuda_fails_explicitly():
    with patch('torch.cuda.is_available', return_value=False):
        with pytest.raises(RuntimeError, match='no CUDA GPU available'):
            DeepSeekOCR2()
