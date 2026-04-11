#!/usr/bin/env python3
"""Sorta.Fit entry point — python -m sortafit"""
import sys


def main():
    from sortafit.config import load_config
    from sortafit.loop import run_loop

    validate = "--validate" in sys.argv
    config = load_config()
    run_loop(config, validate=validate)


if __name__ == "__main__":
    main()
