#!/usr/bin/env python3
"""Broadlink PG3 node server entry point."""

import sys

import udi_interface

from nodes import BroadlinkController, VERSION

LOGGER = udi_interface.LOGGER

if __name__ == "__main__":
    try:
        polyglot = udi_interface.Interface([])
        polyglot.start({"version": VERSION, "requestId": True})
        polyglot.setCustomParamsDoc()
        BroadlinkController(polyglot, "setup", "setup", "Broadlink Hub")
        polyglot.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
