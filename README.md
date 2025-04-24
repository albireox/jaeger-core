# jaeger-core

Core library to handle MPS fibre positioners.

This code is based on the current code for [jaeger](https://github.com/sdss/jaeger) with changes that remove dependencies on specific SDSS hardware and software. In the future we expect `jaeger` to depend on this library.

For more compreggensive documentation, please see the [jaeger documentation](https://sdss-jaeger.readthedocs.io/en/latest/) which should be relevant in most ways. The library structure should be similar but objects must be imported from `jaeger.core` instead of `jaeger`.

## Getting started

`jaeger-core` can be run as a library. To initialise an `FPS` instance you first need to set up a configuration file with the IP to your Ixaat CAN@net device. Create a file `~/.jaeger.yaml` with the following content:

```yaml
profiles:
  default: cannet
  cannet:
    interface: cannet
    channels:
      - 10.1.10.11
    port: 19228
    buses: [1, 2, 3, 4]
    bitrate: 1000000
    timeout: 1
    status_interval: 5
```

replacing the IP with that of your device. The you can initialise an `FPS` instance with:

```python
>>> from jaeger.core import FPS

>>> fps = FPS()

# Initialise the FPS instance
>>> await fps.initialise()

# Get the list of positioners connected to the FPS
>>>  print(fps.positioners.keys())
dict_keys([497])

# Move positioner 497 to alpha=10, beta=100
>>> await fps.goto({497: (10.0, 100.0)})

# Or alternatively
>>> await fps[497].goto(10.0, 100.0)

# Update the status and position of positioner 497
>>> await fps.update_status()
True
>>> await fps.update_position()
array([[497.        ,  10.00628851, 100.00349164]])

# Retrieve information about the positioner
p497 = fps[497]
>>> p497.status
<PositionerStatusV4_1.SYSTEM_INITIALIZED|TRAJECTORY_ALPHA_RECEIVED|TRAJECTORY_BETA_RECEIVED|LOW_POWER_AFTER_MOVE|DISPLACEMENT_COMPLETED|DISPLACEMENT_COMPLETED_ALPHA|DISPLACEMENT_COMPLETED_BETA|CLOSED_LOOP_ALPHA|CLOSED_LOOP_BETA|MOTOR_ALPHA_CALIBRATED|MOTOR_BETA_CALIBRATED|DATUM_ALPHA_CALIBRATED|DATUM_BETA_CALIBRATED|DATUM_ALPHA_INITIALIZED|DATUM_BETA_INITIALIZED|COGGING_ALPHA_CALIBRATED: 2377148385>
>>> p497.alpha
np.float64(10.006288513541222)
>>> p497.beta
np.float64(100.00349164009094)
```

The positioners can also be accessed via the `jaeger-core` CLI.

```bash
$ jaeger status 497
Firmware: 04.01.21
Bootloader: False
Status: 2377148385 (SYSTEM_INITIALIZED, TRAJECTORY_ALPHA_RECEIVED, TRAJECTORY_BETA_RECEIVED, LOW_POWER_AFTER_MOVE, DISPLACEMENT_COMPLETED, DISPLACEMENT_COMPLETED_ALPHA, DISPLACEMENT_COMPLETED_BETA, CLOSED_LOOP_ALPHA, CLOSED_LOOP_BETA, MOTOR_ALPHA_CALIBRATED, MOTOR_BETA_CALIBRATED, DATUM_ALPHA_CALIBRATED, DATUM_BETA_CALIBRATED, DATUM_ALPHA_INITIALIZED, DATUM_BETA_INITIALIZED, COGGING_ALPHA_CALIBRATED)
Position: alpha=10.007, beta=100.006
```

## Actor

The `jaeger-core` library can also be used as an actor. The actor is a TCP server that accepts commands and replies with data in a standard SDSS format (this may be changed in the future). To run the actor, from the command line, run:

```bash
$ jaeger actor start --debug
```

(or without `--debug` to run as a daemon in the background). Then open a TCP socket to localhost in port 19990. You can then send commands and receive responses. To get a list of available commands do

```bash
help
1 0 >
1 0 w help="Usage: jaeger [OPTIONS] COMMAND [ARGS]..."
1 0 w help
1 0 w help=Options:
1 0 w help="  --help  Show this message and exit."
1 0 w help
1 0 w help=Commands:
1 0 w help="  can                   Allows to connect/disconnect the CAN interfaces."
1 0 w help="  current               Sets the current of the positioner."
1 0 w help="  debug                 Debug and engineering tools."
1 0 w help="  disable               Disables a positioner"
1 0 w help="  enable                Enables a positioner"
1 0 w help="  get-command-model     Returns a dictionary representation of the..."
1 0 w help="  get_schema            Returns the schema of the actor as a JSON schema."
1 0 w help="  goto                  Sends positioners to a given (alpha, beta) position."
1 0 w help="  hall                  Turns the hall sensor on/off."
1 0 w help="  help                  Shows the help."
1 0 w help="  initialise            Initialises positioners."
1 0 w help="  keyword               Prints human-readable information about a keyword."
1 0 w help="  led                   Turns the positioner LED on/off."
1 0 w help="  ping                  Pings the actor."
1 0 w help="  pollers               Handle the positioner pollers."
1 0 w help="  reload                Reinitialise the FPS."
1 0 w help="  set-collision-margin  Change the collision margin."
1 0 w help="  speed                 Sets the ``(alpha, beta)`` speed in RPM on the..."
1 0 w help="  status                Reports the position and status bit of a list of..."
1 0 w help="  stop                  Stops the positioners and clear flags."
1 0 w help="  talk                  Send a direct command to the CAN network and show..."
1 0 w help="  testing               Commands for testing."
1 0 w help="  trajectory            Sends a trajectory from a file."
1 0 w help="  unlock                Unlocks the FPS."
1 0 w help="  version               Returns the versions used."
1 0 :
```

To move a positioner, use the `goto` command:

```bash
goto 497 10.0 100.0
1 0 >
1 0 d text="Sending trajectory data."
1 0 d text="Trajectory sent in 0.0 seconds."
1 0 i move_time=8.88
1 0 i text="Starting trajectory ..."
0 0 i fps_status=0x12
0 0 i fps_status=0x11
1 0 i text="All positioners have reached their destinations."
1 0 :
```

or to retrieve the status of all positioners:

```bash
status
1 0 >
0 0 d alive_at=1745536411.324908
1 0 i locked=F
1 0 i n_positioners=1
1 0 i fps_status=0x11
1 0 i positioner_status=497,99.9906,200.0005,0x8db067e1,T,F,F,F,04.01.21,1,4,?
1 0 :
```

Refer to the [documentation](https://sdss-jaeger.readthedocs.io/en/latest/actor.html#jaeger-actor) for more details on the available commands. More details on the datamodel of the SDSS actor can be found [here](https://clu.readthedocs.io/en/latest/legacy.html).
