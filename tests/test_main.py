from unittest.mock import patch

import pytest

from src.main import main


@pytest.mark.unit
def test_main_output(capsys):
    """
    Test that main prints the expected output and exits cleanly.
    """
    # Run main for a short time and then simulate Ctrl+C
    with patch('time.sleep') as mock_sleep:
        mock_sleep.side_effect = KeyboardInterrupt()
        # We expect SystemExit(0) to be raised
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
    
    captured = capsys.readouterr()
    assert "Running..." in captured.out
    assert "Shutting down..." in captured.out 