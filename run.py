#!/usr/bin/env python
"""Convenience launcher so you can `py run.py` instead of `py -m glide`."""

from glide.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
