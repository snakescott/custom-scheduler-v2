import time
from unittest.mock import patch
from src.main import main

def test_main_output(capsys):
    """
    Test that main prints the expected output.
    """
    # Run main for a short time and then simulate Ctrl+C
    with patch('time.sleep') as mock_sleep:
        mock_sleep.side_effect = KeyboardInterrupt()
        main()
    
    captured = capsys.readouterr()
    assert "Running..." in captured.out
    assert "Shutting down..." in captured.out 