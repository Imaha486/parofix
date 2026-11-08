#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parofix 起動スクリプト:  python parofix.py <command> ..."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parofix.cli import main
if __name__ == "__main__":
    sys.exit(main())
