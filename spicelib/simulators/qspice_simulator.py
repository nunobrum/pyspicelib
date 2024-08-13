#!/usr/bin/env python
# coding=utf-8

# -------------------------------------------------------------------------------
#
#  ███████╗██████╗ ██╗ ██████╗███████╗██╗     ██╗██████╗
#  ██╔════╝██╔══██╗██║██╔════╝██╔════╝██║     ██║██╔══██╗
#  ███████╗██████╔╝██║██║     █████╗  ██║     ██║██████╔╝
#  ╚════██║██╔═══╝ ██║██║     ██╔══╝  ██║     ██║██╔══██╗
#  ███████║██║     ██║╚██████╗███████╗███████╗██║██████╔╝
#  ╚══════╝╚═╝     ╚═╝ ╚═════╝╚══════╝╚══════╝╚═╝╚═════╝
#
# Name:        qspice_simulator.py
# Purpose:     Represents QSPICE
#
# Author:      Nuno Brum (nuno.brum@gmail.com)
#
# Created:     26-08-2023
# Licence:     refer to the LICENSE file
# -------------------------------------------------------------------------------
import sys
import os

from pathlib import Path
import logging
from ..sim.simulator import Simulator, run_function, SpiceSimulatorError

_logger = logging.getLogger("spicelib.QSpiceSimulator")


class Qspice(Simulator):
    """Stores the simulator location and command line options and is responsible for generating netlists and running
    simulations."""
    raw_extension = '.qraw'  # In QSPICE all traces have double precision. This means that qraw files are not compatible
    # with LTSPICE
    
    # windows paths (that are also valid for wine)
    # Please note that os.path.expanduser and os.path.join are sensitive to the style of slash.
    # Placed in order of preference. The first to be found will be used.
    _spice_exe_win_paths = ["~/Qspice/QSPICE64.exe",
                            "~/AppData/Local/Programs/Qspice/QSPICE64.exe",
                            "C:/Program Files/QSPICE/QSPICE64.exe"]
    
    # the default lib paths, as used by get_default_library_paths
    _default_lib_paths = ["C:/Program Files/QSPICE",
                          "~/Documents/QSPICE"]

    """Searches on the any usual locations for a simulator"""
    # defaults:
    spice_exe = []
    process_name = None  
        
    if sys.platform == "linux" or sys.platform == "darwin":
        # status mid 2024: Qspice has limited support for running under linux+wine, and none for MacOS+wine
        # TODO: when the situation gets more mature, add support for wine. See LTspice for an example.
        spice_exe = []
        process_name = None
    else:  # Windows (well, also aix, wasi, emscripten,... where it will fail.)
        for exe in _spice_exe_win_paths:
            if exe.startswith("~"):
                # expand here, as I use _spice_exe_win_paths also for linux, and expanding earlier will fail
                exe = os.path.expanduser(exe)
            if os.path.exists(exe):
                spice_exe = [exe]
                process_name = Path(exe).name
                break        

    # fall through        
    if len(spice_exe) == 0:
        spice_exe = []
        process_name = None
    else:
        _logger.debug(f"Found Qspice installed in: '{spice_exe}' ")

    qspice_args = {
        'ASCII'     : ['-ASCII'],  # Use ASCII file format for the output data(.qraw) file.
        'binary'    : ['-binary'],  # Use binary file format for the output data(.qraw) file.
        'BSIM1'    : ['-BSIM1'],  # Use the charge-conserving BSIM1 charge model for MOS1, MOS2, and MOS3.
        'Meyer'    : ['-Meyer'],  # Use the Meyer Capacitance model for MOS1, MOS2, and MOS3.
        'o'         : ['-o', '<path>'],  # Specify the name of a file for the console output.
        # 'p'         : ['-p'],  # Take the netlist piped from stdin. Not used in this implementation.
        'ProtectSelections': ['-ProtectSelections', '<path>'],  # Protect sections marked with .prot/.unprot with encryption.
        'ProtectSubcircuits': ['-ProtectSubcircuits', '<path>'],  # Protect the body of subcircuits with encryption.
        'r'       : ['-r', '<path>'],  # Specify the name of the output data(.qraw) file.
    }

    @classmethod
    def valid_switch(cls, switch, path='') -> list:
        """
        Validates a command line switch. The following options are available for QSPICE:
            * 'ASCII': Use ASCII file format for the output data(.qraw) file.

            * 'binary': Use binary file format for the output data(.qraw) file.

            * 'BSIM1': Use the charge-conserving BSIM1 charge model for MOS1, MOS2, and MOS3.

            * 'Meyer': Use the Meyer Capacitance model for MOS1, MOS2, and MOS3.

            * 'o <path>': Specify the name of a file for the console output.

            * 'ProtectSelections <path>': Protect sections marked with .prot/.unprot with encryption.

            * 'ProtectSubcircuits <path>': Protect the body of subcircuits with encryption.

            * 'r <path>': Specify the name of the output data(.qraw) file.


        :param switch: switch to be added. If the switch is not on the list above, it should be correctly formatted with
                       the preceding '-' switch
        :type switch: str
        :param path: path to the file related to the switch being given.
        :type path: str, optional
        :return: Nothing
        :rtype: None
        """
        if switch in cls.qspice_args:
            switches = cls.qspice_args[switch]
            switches = [switch.replace('<path>', path) for switch in switches]
            return switches
        else:
            raise ValueError("Invalid switch for class ")

    @classmethod
    def run(cls, netlist_file, cmd_line_switches, timeout):
        if not cls.spice_exe:
            _logger.error("================== ALERT! ====================")
            _logger.error("Unable to find the QSPICE executable.")
            _logger.error("A specific location of the QSPICE can be set")
            _logger.error("using the create_from(<location>) class method")
            _logger.error("==============================================")
            raise SpiceSimulatorError("Simulator executable not found.")
        log_file = Path(netlist_file).with_suffix('.log').as_posix()
        cmd_run = cls.spice_exe + ['-o', log_file] + [netlist_file] + cmd_line_switches
        # start execution
        return run_function(cmd_run, timeout=timeout)
