#!/usr/bin/env python3
"""Broadlink PG3 node server entry point."""

import sys

import udi_interface

from nodes import BroadlinkController, VERSION

LOGGER = udi_interface.LOGGER

if __name__ == "__main__":
    try:
        LOGGER.info("=" * 80)
        LOGGER.info("Starting Broadlink PG3 Node Server v%s", VERSION)
        LOGGER.info("=" * 80)
        
        polyglot = udi_interface.Interface([])
        LOGGER.info("Creating polyglot interface")
        
        polyglot.start({"version": VERSION, "requestId": True})
        LOGGER.info("Polyglot interface started")
        
        polyglot.setCustomParamsDoc()
        LOGGER.info("Setting custom params documentation")
        
        LOGGER.info("Constructing BroadlinkController node")
        BroadlinkController(polyglot, "setup", "setup", "Broadlink Setup")
        LOGGER.info("BroadlinkController constructed successfully")
        
        LOGGER.info("Entering polyglot runForever() loop")
        polyglot.runForever()
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("Shutdown signal received")
        sys.exit(0)
