#!/usr/bin/env python3
"""Centralized logging setup for all VSNES components."""
import logging
import os

LOG_DIR = '/tmp/log'
LOG_FILE = os.path.join(LOG_DIR, 'snes.log')


def setup_logging():
	# Configure the root logger once per process; later calls are no-ops.
	if logging.getLogger().handlers:
		return
	os.makedirs(LOG_DIR, exist_ok=True)
	logging.basicConfig(
		level=logging.INFO,
		format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
		handlers=[
			logging.FileHandler(LOG_FILE),
			logging.StreamHandler()
		]
	)
