#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-11-12
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from typing import TYPE_CHECKING

from clu import Command
from clu.parsers.click import command_parser

from jaeger.core.actor import JaegerActor


jaeger_parser = command_parser

JaegerCommandType = Command[JaegerActor]


from .can import *
from .debug import *
from .disable import *
from .pollers import *
from .positioner import *
from .talk import *
from .testing import *
from .version import *
