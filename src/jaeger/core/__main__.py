#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2019-11-12
# @Filename: cli.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import warnings
from copy import deepcopy
from functools import wraps

import click
from click_default_group import DefaultGroup
from sdsstools.daemonizer import DaemonGroup

from jaeger.core import can_log, config, log
from jaeger.core.exceptions import (
    JaegerError,
    JaegerUserWarning,
    TrajectoryError,
)
from jaeger.core.fps import FPS, LOCK_FILE
from jaeger.core.positioner import Positioner
from jaeger.core.positioner.commands.calibration import calibrate_positioners
from jaeger.core.positioner.commands.goto import goto as goto_
from jaeger.core.testing import VirtualFPS


__FPS__ = None


def shutdown(sign):
    """Shuts down the FPS and stops the positioners in case of a signal interrupt."""

    if __FPS__ is not None:
        __FPS__.send_command("SEND_TRAJECTORY_ABORT", positioner_ids=None, now=True)
        log.error(f"stopping positioners and cancelling due to {sign.name}")
        sys.exit(0)
    else:
        log.error(f"cannot shutdown FPS before {sign.name}")
        sys.exit(1)


def cli_coro(f):
    """Decorator function that allows defining coroutines with click."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
        for ss in signals:
            loop.add_signal_handler(ss, shutdown, ss)
        return loop.run_until_complete(f(*args, **kwargs))

    return wrapper


class FPSWrapper(object):
    """A helper to store FPS initialisation parameters."""

    def __init__(
        self,
        profile,
        initialise=True,
        npositioners=10,
    ):
        self.profile = profile
        if self.profile in ["test", "virtual"]:
            self.profile = "virtual"

        self.initialise = initialise

        self.vpositioners = []
        self.npositioners = npositioners

        self.fps = None

    async def __aenter__(self):
        global __FPS__

        # If profile is test we start a VirtualFPS first so that it can respond
        # to the FPS class.
        if self.profile == "virtual":
            self.fps = VirtualFPS()
            for pid in range(self.npositioners):
                self.fps.add_virtual_positioner(pid + 1)
        else:
            self.fps = FPS(can=self.profile)

        __FPS__ = self.fps

        if self.initialise:
            await self.fps.initialise()

        return self.fps

    async def __aexit__(self, *excinfo):
        try:
            if self.fps is None:
                return
            await self.fps.shutdown()
        except JaegerError as err:
            warnings.warn(f"Failed shutting down FPS: {err}", JaegerUserWarning)


pass_fps = click.make_pass_decorator(FPSWrapper, ensure=True)


@click.group(cls=DefaultGroup, default="actor", default_if_no_args=True)
@click.option(
    "-c",
    "--config",
    "config_file",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the user configuration file.",
)
@click.option(
    "-p",
    "--profile",
    type=str,
    help="The bus interface profile.",
)
@click.option(
    "--virtual",
    is_flag=True,
    help="Runs a virtual FPS with virtual positioners. Same as --profile=virtual.",
)
@click.option(
    "-n",
    "--npositioners",
    type=int,
    default=10,
    help="How many virtual positioners must be connected to the virtual FPS.",
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Debug mode. Use additional v for more details.",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    help="Disable all console logging.",
)
@click.option(
    "--no-lock",
    is_flag=True,
    help="Do not use the lock file, or ignore it if present.",
)
@click.pass_context
def jaeger(
    ctx,
    config_file,
    profile,
    verbose,
    quiet,
    virtual,
    npositioners,
    no_lock,
):
    """CLI for the SDSS-V focal plane system.

    If called without subcommand starts the actor.

    """

    if verbose > 0 and quiet:
        raise click.UsageError("--quiet and --verbose are mutually exclusive.")

    if config_file:
        config.load(config_file)

    if no_lock:
        config["fps"]["use_lock"] = False

    if profile is None:
        profile = config["profiles.default"]

    actor_config = config.get("actor", {})

    if verbose == 1:
        log.sh.setLevel(logging.INFO)
        actor_config["verbose"] = logging.INFO
    elif verbose == 2:
        log.sh.setLevel(logging.DEBUG)
        actor_config["verbose"] = logging.DEBUG
    elif verbose >= 3:
        log.sh.setLevel(logging.DEBUG)
        can_log.sh.setLevel(logging.DEBUG)
        actor_config["verbose"] = logging.DEBUG

    if quiet:
        log.handlers.remove(log.sh)
        warnings.simplefilter("ignore")
        actor_config["verbose"] = 100

    if virtual is True:
        profile = "virtual"

    ctx.obj = FPSWrapper(profile, npositioners=npositioners)


LOG_FILE = os.path.join(
    os.environ.get("ACTOR_DAEMON_LOG_DIR", "$HOME/.jaeger"),
    "logs/jaeger.log",
)


@jaeger.group(
    cls=DaemonGroup,
    prog="jaeger_actor",
    workdir=os.getcwd(),
    log_file=LOG_FILE,
)
@pass_fps
@cli_coro
async def actor(fps_maker):
    """Runs the actor."""

    try:
        from jaeger.core.actor import JaegerActor
    except ImportError:
        raise ImportError("CLU needs to be installed to run jaeger as an actor.")

    config_copy = deepcopy(config)
    if "actor" not in config_copy:
        raise RuntimeError("Configuration file does not contain an actor section.")

    config_copy["actor"].pop("status", None)

    # Do not initialise FPS so that we can define the actor instance first.
    fps_maker.initialise = False

    async with fps_maker as fps:
        actor_: JaegerActor = JaegerActor.from_config(config_copy, fps)

        await fps.initialise()

        await actor_.start()
        await actor_.run_forever()

        await actor_.stop()


@jaeger.command()
@click.argument("positioner-id", nargs=1, type=int)
@click.option(
    "--motors/--no-motors",
    is_flag=True,
    default=True,
    help="Run the motor calibration.",
)
@click.option(
    "--datums/--no-datums",
    is_flag=True,
    default=True,
    help="Run the datum calibration.",
)
@click.option(
    "--cogging/--no-cogging",
    is_flag=True,
    default=True,
    help="Run the cogging calibration (can take a long time).",
)
@pass_fps
@cli_coro
async def calibrate(fps_maker, positioner_id, motors, datums, cogging):
    """Runs a full calibration on a positioner."""

    fps_maker.initialise = False
    fps_maker.danger = True

    async with fps_maker as fps:
        await fps.initialise(start_pollers=False)
        await calibrate_positioners(
            fps,
            "both",
            positioner_id,
            motors=motors,
            datums=datums,
            cogging=cogging,
        )


@jaeger.command()
@click.argument("POSITIONER-IDS", type=int, nargs=-1)
@click.argument("ALPHA", type=click.FloatRange(-10.0, 370.0))
@click.argument("BETA", type=click.FloatRange(-10.0, 370.0))
@click.option(
    "-r",
    "--relative",
    is_flag=True,
    help="Whether this is a relative move",
)
@click.option(
    "-s",
    "--speed",
    type=click.FloatRange(100.0, 4000.0),
    help="The speed for both alpha and beta arms, in RPS on the input.",
)
@click.option(
    "-a",
    "--all",
    is_flag=True,
    default=False,
    help="Applies to all valid positioners.",
)
@click.option(
    "-f",
    "--force",
    is_flag=True,
    default=False,
    help="Forces a move to happen.",
)
@pass_fps
@cli_coro
async def goto(
    fps_maker,
    positioner_ids: tuple[int, ...] | list[int],
    alpha: float,
    beta: float,
    speed: float | None,
    all: bool = False,
    force: bool = False,
    relative: bool = False,
):
    """Sends positioners to a given (alpha, beta) position."""

    async with fps_maker as fps:
        if all:
            if not force:
                raise JaegerError("Use --force to move all positioners at once.")
            positioner_ids = list(fps.positioners.keys())
        else:
            positioner_ids = list(positioner_ids)

        if not relative:
            if alpha < 0 or beta < 0:
                raise JaegerError("Negative angles only allowed in relative mode.")

        new_positions = {}
        for pid in positioner_ids:
            new_positions[pid] = (alpha, beta)

        try:
            await goto_(
                fps,
                new_positions,
                speed=speed,
                relative=relative,
            )
        except (JaegerError, TrajectoryError) as err:
            raise JaegerError(f"Goto command failed: {err}")


@jaeger.command(name="set-positions")
@click.argument("positioner_id", metavar="POSITIONER", type=int)
@click.argument("alpha", metavar="ALPHA", type=float)
@click.argument("beta", metavar="BETA", type=float)
@pass_fps
@cli_coro
async def set_positions(fps_maker, positioner_id, alpha, beta):
    """Sets the position of the alpha and beta arms."""

    if alpha < 0 or alpha >= 360:
        raise click.UsageError("alpha must be in the range [0, 360)")

    if beta < 0 or beta >= 360:
        raise click.UsageError("beta must be in the range [0, 360)")

    async with fps_maker as fps:
        positioner = fps.positioners[positioner_id]

        result = await positioner.set_position(alpha, beta)

        if not result:
            log.error("failed to set positions.")
            return

        log.info(f"positioner {positioner_id} set to {(alpha, beta)}.")


@jaeger.command()
@click.argument("positioner_id", metavar="POSITIONER", type=int)
@click.option(
    "--axis",
    type=click.Choice(["alpha", "beta"], case_sensitive=True),
    help="The axis to home. If not set, homes both axes at the same time.",
)
@pass_fps
@cli_coro
async def home(fps_maker: FPSWrapper, positioner_id: int, axis: str | None = None):
    """Home a single positioner, sending a GO_TO_DATUMS command."""

    alpha: bool = axis == "alpha" or axis is None
    beta: bool = axis == "beta" or axis is None

    async with fps_maker as fps:
        if positioner_id not in fps or fps[positioner_id].initialised is False:
            raise ValueError("Positioner is not connected.")
        if fps[positioner_id].disabled or fps[positioner_id].offline:
            raise ValueError("Positioner has been disabled.")

        await fps[positioner_id].home(alpha=alpha, beta=beta)

    return


@jaeger.command()
@pass_fps
@cli_coro
async def list_positioners(fps_maker: FPSWrapper):
    """Returns a list of connected positioners."""

    async with fps_maker as fps:
        return list(fps.positioners)


@jaeger.command()
@click.argument("positioner_id", metavar="POSITIONER", type=int)
@pass_fps
@cli_coro
async def status(fps_maker: FPSWrapper, positioner_id: int):
    """Returns the status of a positioner with low-level initialisation."""

    async with fps_maker as fps:
        if isinstance(fps, VirtualFPS):
            raise JaegerError("Cannot get status of virtual positioner.")

        pos = Positioner(positioner_id, fps)

        try:
            await pos.update_firmware_version()
            print(f"Firmware: {pos.firmware}")
            print(f"Bootloader: {pos.is_bootloader()}")
        except Exception as err:
            raise JaegerError(f"Failed retrieving firmware: {err}")

        try:
            await pos.update_status()
            bit_names = ", ".join(bit.name for bit in pos.status.active_bits)
            print(f"Status: {pos.status.value} ({bit_names})")
        except Exception as err:
            raise JaegerError(f"Failed retrieving status: {err}")

        try:
            await pos.update_position()
            print(f"Position: alpha={pos.position[0]:.3f}, beta={pos.position[1]:.3f}")
        except Exception as err:
            raise JaegerError(f"Failed retrieving position: {err}")


@jaeger.command()
@pass_fps
@cli_coro
async def unlock(fps_maker: FPSWrapper):
    """Unlocks the FPS."""

    warnings.filterwarnings(
        "ignore",
        message=".+FPS was collided and has been locked.+",
        category=JaegerUserWarning,
    )

    async with fps_maker as fps:
        await fps.unlock()

    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)


if __name__ == "__main__":
    jaeger()
