#!/usr/bin/env python3

"""
AWS Query Tool - Entry point for backward compatibility.

This script maintains backward compatibility by importing and calling
the main function from the modular src/awsquery package.
"""

import sys
import os

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Import the main function from the modular structure
from awsquery.cli import main


if __name__ == "__main__":
    main()
