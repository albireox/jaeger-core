#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2025-04-16
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import logging
import os
import pathlib
import warnings

from typing import TYPE_CHECKING

from sdsstools import Configuration, get_logger, get_package_version, read_yaml_file
from sdsstools.configuration import __ENVVARS__

from .exceptions import JaegerUserWarning


if TYPE_CHECKING:
    from .actor import JaegerActor


NAME = "jaeger-core"

__version__ = get_package_version(path=__file__, package_name=NAME)


log = get_logger("jaeger", log_level=logging.WARNING, use_rich_handler=True)
can_log = get_logger("jaeger_can", log_level=logging.ERROR, capture_warnings=False)


base_config_file = pathlib.Path(__file__).parent / "config" / "config.yaml"
user_config_file = os.path.join(os.path.expanduser("~"), ".jaeger.yaml")

if os.path.exists(user_config_file):
    config = Configuration(config=user_config_file, base_config=base_config_file)
else:
    config = Configuration(base_config=base_config_file)


# If we are not in debug mode, remove some possible warnings.
if config["debug"] is False:
    warnings.filterwarnings(
        "ignore",
        message=".+was never awaited.+",
        category=RuntimeWarning,
    )


warnings.simplefilter("always", category=JaegerUserWarning)


def start_file_loggers(start_log=True, start_can=True):
    if "files" in config and "log_dir" in config["files"]:
        log_dir = config["files"]["log_dir"]
    else:
        log_dir = "~/.jaeger"

    if start_log and log.fh is None:
        log.start_file_logger(os.path.join(log_dir, "jaeger.log"))

    if start_can and can_log.fh is None:
        can_log.start_file_logger(os.path.join(log_dir, "can.log"))


actor_instance: JaegerActor | None = None


from .actor import *
from .can import *
from .exceptions import *
from .fps import *
from .maskbits import *
from .positioner import *
