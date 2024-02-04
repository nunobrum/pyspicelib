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
# Name:        asc_editor.py
# Purpose:     Class made to update directly the LTspice ASC files
#
# Author:      Nuno Brum (nuno.brum@gmail.com)
#
# Licence:     refer to the LICENSE file
# -------------------------------------------------------------------------------
import pathlib
from pathlib import Path
from typing import Union, Tuple, List
import re
import logging
from .base_editor import BaseEditor, format_eng, ComponentNotFoundError, ParameterNotFoundError, PARAM_REGEX, \
    UNIQUE_SIMULATION_DOT_INSTRUCTIONS, Point, Line, Text, SchematicComponent, ERotation, HorAlign, VerAlign

_logger = logging.getLogger("spicelib.AscEditor")

TEXT_REGEX = re.compile(r"TEXT (-?\d+)\s+(-?\d+)\s+(Left|Right|Top|Bottom)\s(\d+)\s*(?P<type>[!;])(?P<text>.*)",
                        re.IGNORECASE)
TEXT_REGEX_X = 1
TEXT_REGEX_Y = 2
TEXT_REGEX_ALIGN = 3
TEXT_REGEX_SIZE = 4
TEXT_REGEX_TYPE = 5
TEXT_REGEX_TEXT = 6

END_LINE_TERM = "\n"


ASC_ROTATION_DICT = {
    'R0': ERotation.R0,
    'R90': ERotation.R90,
    'R180': ERotation.R180,
    'R270': ERotation.R270,
}

ASC_INV_ROTATION_DICT = {val: key for key, val in ASC_ROTATION_DICT.items()}


def asc_text_align_set(text: Text, alignment: str):
    if alignment == 'Left':
        text.textAlignment = HorAlign.LEFT
        text.verticalAlignment = VerAlign.CENTER
    elif alignment == 'Center':
        text.textAlignment = HorAlign.CENTER
        text.verticalAlignment = VerAlign.CENTER
    elif alignment == 'Right':
        text.textAlignment = HorAlign.RIGHT
        text.verticalAlignment = VerAlign.CENTER
    elif alignment == 'VTop':
        text.textAlignment = HorAlign.CENTER
        text.verticalAlignment = VerAlign.TOP
    elif alignment == 'VCenter':
        text.textAlignment = HorAlign.CENTER
        text.verticalAlignment = VerAlign.CENTER
    elif alignment == 'VBottom':
        text.textAlignment = HorAlign.LEFT
        text.verticalAlignment = VerAlign.BOTTOM
    else:
        # Default
        text.textAlignment = HorAlign.LEFT
        text.verticalAlignment = VerAlign.BOTTOM
    return text


def asc_text_align_get(text: Text) -> str:
    if text.verticalAlignment == VerAlign.CENTER:
        if text.textAlignment == HorAlign.RIGHT:
            return 'Right'
        elif text.textAlignment == HorAlign.CENTER:
            return 'Center'
        else:
            return 'Left'
    else:
        if text.verticalAlignment == VerAlign.TOP:
            return 'VTop'
        elif text.verticalAlignment == VerAlign.CENTER:
            return 'VCenter'
        elif text.verticalAlignment == VerAlign.BOTTOM:
            return 'VBottom'
        else:
            return 'Left'


class AscEditor(BaseEditor):
    """Class made to update directly the LTspice ASC files"""

    def __init__(self, asc_file: str):
        super().__init__()
        self.version = 4
        self.sheet = (0, 0)
        self._asc_file_path = Path(asc_file)
        if not self._asc_file_path.exists():
            raise FileNotFoundError(f"File {asc_file} not found")
        # read the file into memory
        self.reset_netlist()

    @property
    def circuit_file(self) -> Path:
        return self._asc_file_path

    def save_netlist(self, run_netlist_file: Union[str, Path]) -> None:
        if isinstance(run_netlist_file, str):
            run_netlist_file = Path(run_netlist_file)
        run_netlist_file = run_netlist_file.with_suffix(".asc")
        with open(run_netlist_file, 'w') as asc:
            _logger.info(f"Writing ASC file {run_netlist_file}")

            asc.write(f"Version {self.version}" + END_LINE_TERM)
            asc.write(f"SHEET {self.sheet}" + END_LINE_TERM)
            for wire in self._wires:
                asc.write(f"WIRE {wire.V1.X} {wire.V1.Y} {wire.V2.X} {wire.V2.Y}" + END_LINE_TERM)
            for flag in self._labels:
                asc.write(f"FLAG {flag.coord.X} {flag.coord.Y} {flag.text}" + END_LINE_TERM)
            for component in self._components.values():
                symbol = component.symbol
                posX = component.position.X
                posY = component.position.Y
                rotation = ASC_INV_ROTATION_DICT[component.rotation]
                asc.write(f"SYMBOL {symbol} {posX} {posY} {rotation}" + END_LINE_TERM)
                for attr, value in component.attributes.items():
                    if attr.startswith('WINDOW') and isinstance(value, Text):
                        posX = value.coord.X
                        posY = value.coord.Y
                        alignment = asc_text_align_get(value)
                        size = value.size
                        asc.write(f"{attr} {posX} {posY} {alignment} {size}" + END_LINE_TERM)
                asc.write(f"SYMATTR InstName {component.reference}" + END_LINE_TERM)
                for attr, value in component.attributes.items():
                    if not attr.startswith('WINDOW'):
                        asc.write(f"SYMATTR {attr} {value}" + END_LINE_TERM)
            for directive in self._directives:
                posX = directive.coord.X
                posY = directive.coord.Y
                alignment = asc_text_align_get(directive)
                size = directive.size
                if size < 0:  # Negative size means that the directive type is a comment
                    size = -size
                    directive_type = '?'
                else:
                    directive_type = '!'
                asc.write(f"TEXT {posX} {posY} {alignment} {size} {directive_type}{directive.text}" + END_LINE_TERM)

    def reset_netlist(self):
        super().reset_netlist()
        with open(self._asc_file_path, 'r') as asc_file:
            _logger.info(f"Reading ASC file {self._asc_file_path}")
            component = None
            _logger.debug("Parsing ASC file")
            for line in asc_file:
                if line.startswith("SYMBOL"):
                    tag, symbol, posX, posY, rotation = line.split()
                    if component is not None:
                        assert component.reference is not None, "Component InstName was not given"
                        self._components[component.reference] = component
                    component = SchematicComponent()
                    component.symbol = symbol
                    component.position.X = int(posX)
                    component.position.Y = int(posY)
                    if rotation in ASC_ROTATION_DICT:
                        component.rotation = ASC_ROTATION_DICT[rotation]
                    else:
                        raise ValueError(f"Invalid Rotation value: {rotation}")
                elif line.startswith("WINDOW"):
                    assert component is not None, "Syntax Error: WINDOW clause without SYMBOL"
                    tag, num_ref, posX, posY, alignment, size = line.split()
                    coord = Point(int(posX), int(posY))
                    text = Text(coord=coord, text=num_ref, size=size)
                    text = asc_text_align_set(text, alignment)
                    component.attributes['WINDOW ' + num_ref] = text

                elif line.startswith("SYMATTR"):
                    assert component is not None, "Syntax Error: SYMATTR clause without SYMBOL"
                    tag, ref, text = line.split(maxsplit=2)
                    text = text.strip()  # Gets rid of the \n terminator
                    if ref == "InstName":
                        component.reference = text
                    else:
                        component.attributes[ref] = text
                elif line.startswith("TEXT"):
                    match = TEXT_REGEX.match(line)
                    if match:
                        text = match.group(TEXT_REGEX_TEXT)
                        X = int(match.group(TEXT_REGEX_X))
                        Y = int(match.group(TEXT_REGEX_Y))
                        coord = Point(X, Y)
                        size = int(match.group(TEXT_REGEX_SIZE))
                        if match.group(TEXT_REGEX_TYPE) != "!":
                            size = -size  # This is used to signal that it is a comment
                        alignment = match.group(TEXT_REGEX_ALIGN)
                        text = Text(coord=coord, text=text.strip(), size=size)
                        text = asc_text_align_set(text, alignment)
                        self._directives.append(text)

                elif line.startswith("WIRE"):
                    tag, x1, y1, x2, y2 = line.split()
                    v1 = Point(int(x1), int(y1))
                    v2 = Point(int(x2), int(y2))
                    wire = Line(v1, v2)
                    self._wires.append(wire)
                elif line.startswith("FLAG"):
                    tag, posX, posY, text = line.split(maxsplit=4)
                    coord = Point(int(posX), int(posY))
                    flag = Text(coord=coord, text=text)
                    self._labels.append(flag)
                elif line.startswith("Version"):
                    tag, version = line.split()
                    assert version in ["4"], f"Unsupported version : {version}"
                    self.version = version
                elif line.startswith("SHEET "):
                    self.sheet = line[len("SHEET "):].strip()
                else:
                    raise NotImplementedError("Primitive not supported for ASC file\n" 
                                              f'"{line}"')
            if component is not None:
                assert component.reference is not None, "Component InstName was not given"
                self._components[component.reference] = component

    def get_component_info(self, component) -> SchematicComponent:
        """Returns the component information as a dictionary"""
        if component not in self._components:
            _logger.error(f"Component {component} not found in ASC file")
            raise ComponentNotFoundError(f"Component {component} not found in ASC file")
        return self._components[component]

    def _get_directive(self, command, search_expression: re.Pattern):
        command_upped = command.upper()
        for directive in self._directives:
            if directive.text.startswith(command_upped):
                match = search_expression.search(directive.text)
                if match:
                    return match, directive
        return None, None

    def get_parameter(self, param: str) -> (str, Text):
        param_regex = re.compile(PARAM_REGEX % param, re.IGNORECASE)
        match, directive = self._get_directive(".PARAM", param_regex)
        if match:
            return match.group('value'), directive
        else:
            raise ParameterNotFoundError(f"Parameter {param} not found in ASC file")

    def set_parameter(self, param: str, value: Union[str, int, float]) -> None:
        match, directive = self.get_parameter(param)
        if match:
            _logger.debug(f"Parameter {param} found in ASC file, updating it")
            if isinstance(value, (int, float)):
                value_str = format_eng(value)
            else:
                value_str = value
            start, stop = match.group('replace').span
            directive.text = f"{directive.text[:start]}{param}={value_str}{directive.text[stop:]}"
            _logger.info(f"Parameter {param} updated to {value_str}")
        else:
            # Was not found so we need to add it,
            _logger.debug(f"Parameter {param} not found in ASC file, adding it")
            x, y = self._get_text_space()
            coord = Point(x, y)
            text = ".param {}={}".format(param, value)
            directive = Text(coord=coord, text=text, size=2)
            _logger.info(f"Parameter {param} added with value {value}")
            self._directives.append(directive)


    def set_component_value(self, device: str, value: Union[str, int, float]) -> None:
        component = self.get_component_info(device)
        if "Value" in component.attributes:
            if isinstance(value, str):
                value_str = value
            else:
                value_str = format_eng(value)
            component.attributes["Value"] = value_str
            _logger.info(f"Component {device} updated to {value_str}")
        else:
            _logger.error(f"Component {device} does not have a Value attribute")
            raise ComponentNotFoundError(f"Component {device} does not have a Value attribute")

    def set_element_model(self, element: str, model: str) -> None:
        component = self.get_component_info(element)
        component.symbol = model
        _logger.info(f"Component {element} updated to {model}")

    def get_component_value(self, element: str) -> str:
        comp_info = self.get_component_info(element)
        if "Value" not in comp_info.attributes:
            _logger.error(f"Component {element} does not have a Value attribute")
            raise ComponentNotFoundError(f"Component {element} does not have a Value attribute")
        return comp_info.attributes["Value"]

    def get_components(self, prefixes='*') -> list:
        if prefixes == '*':
            return list(self._components.keys())
        return [k for k in self._components.keys() if k[0] in prefixes]

    def remove_component(self, designator: str):
        del self._components[designator]

    def _get_text_space(self):
        """
        Returns the coordinate on the Schematic File canvas where a text can be appended.
        """
        min_x = 100000  # High enough to be sure it will be replaced
        max_x = -100000
        min_y = 100000  # High enough to be sure it will be replaced
        max_y = -100000
        _, x, y = self.sheet.split()
        min_x = min(min_x, int(x))
        min_y = min(min_y, int(y))
        for wire in self._wires:
            min_x = min(min_x, wire.V1.X, wire.V2.X)
            max_x = max(max_x, wire.V1.X, wire.V2.X)
            min_y = min(min_y, wire.V1.Y, wire.V2.X)
            max_y = max(max_y, wire.V1.Y, wire.V2.X)
        for flag in self._labels:
            min_x = min(min_x, flag.coord.X)
            max_x = max(max_x, flag.coord.X)
            min_y = min(min_y, flag.coord.Y)
            max_y = max(max_y, flag.coord.Y)
        for directive in self._directives:
            min_x = min(min_x, directive.coord.X)
            max_x = max(max_x, directive.coord.X)
            min_y = min(min_y, directive.coord.Y)
            max_y = max(max_y, directive.coord.Y)
        for component in self._components.values():
            min_x = min(min_x, component.position.X)
            max_x = max(max_x, component.position.X)
            min_y = min(min_y, component.position.Y)
            max_y = max(max_y, component.position.Y)

        return min_x, max_y + 24  # Setting the text in the bottom left corner of the canvas

    def add_instruction(self, instruction: str) -> None:
        instruction = instruction.strip()  # Clean any end of line terminators
        command = instruction.split()[0].upper()

        if command in UNIQUE_SIMULATION_DOT_INSTRUCTIONS:
            # Before adding new instruction, if it is a unique instruction, we just replace it
            i = 0
            while i < len(self._directives):
                line_no, line = self._directives[i]
                command = line.split()[0].upper()
                if command in UNIQUE_SIMULATION_DOT_INSTRUCTIONS:
                    line = self._asc_file_lines[line_no]
                    self._asc_file_lines[line_no] = line[:line.find("!")] + instruction + END_LINE_TERM
                    self._parse_asc_file()
                    return  # Job done, can exit this method
                i += 1
        elif command.startswith('.PARAM'):
            raise RuntimeError('The .PARAM instruction should be added using the "set_parameter" method')
        # If we get here, then the instruction was not found, so we need to add it
        x, y = self._get_text_space()
        self._asc_file_lines.append("TEXT {} {} Left 2 !{}".format(x, y, instruction) + END_LINE_TERM)
        self._parse_asc_file()

    def remove_instruction(self, instruction: str) -> None:
        i = 0
        while i < len(self._directives):
            line_no, line = self._directives[i]
            if instruction in line:
                del self._asc_file_lines[line_no]
                _logger.info(f"Instruction {line} removed")
                self._parse_asc_file()
                return  # Job done, can exit this method
            i += 1

        msg = f'Instruction "{instruction}" not found'
        _logger.error(msg)
        raise RuntimeError(msg)

    def remove_Xinstruction(self, search_pattern: str) -> None:
        regex = re.compile(search_pattern, re.IGNORECASE)
        instr_removed = False
        i = 0
        while i < len(self._directives):
            line_no, line = self._directives[i]
            if regex.match(line):
                instr_removed = True
                del self._asc_file_lines[line_no]
                _logger.info(f"Instruction {line} removed")
                self._parse_asc_file()  # This is needed to update the self._directives list
            else:
                i += 1
        if not instr_removed:
            msg = f'Instructions matching "{search_pattern}" not found'
            _logger.error(msg)