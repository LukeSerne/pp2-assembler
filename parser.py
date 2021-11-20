import typing
import re

import base

class Segment:
    _content: list[tuple]

    def __init__(self):
        self._content = []

    def add(self, arg):
        self._content.append(arg)


class Parser:
    def __init__(self, input_):
        """
        Initialises the parser
        """
        self.input = input_
        self.code = []
        self.data = []

    def parseSections(self) -> list:
        # process the file line by line
        segment = None  # 'code', 'data' or None
        aliases = {}
        tokens = []

        # Tokenise based on spaces
        for line in self.input.split("\n"):
            if ";" in line:
                line = line[:line.index(";")]

            line = line.strip()
            if not line:
                continue

            if line.startswith("@"):
                if "=" in line:
                    name, value = line.split("=")
                    name = name.strip()
                    value = value.strip()
                else:
                    name, value = line, None

                if name == "@CODE":
                    segment = "code"

                    if value is None:
                        value = 0x3ffff
                    else:
                        value = self.get_value(value)

                    tokens.append((base.Token.CODE_SEGMENT_START, value))

                elif name == "@DATA":
                    segment = "data"

                    if value is None:
                        value = 0x3ffff
                    else:
                        value = self.getValue(value)

                    tokens.append((base.Token.DATA_SEGMENT_START, value))

                elif name == "@END" and value is None:
                    break
                elif name == "@INCLUDE":
                    raise NotImplementedError("Include statements are not supported.")
                elif name == "@STACK":
                    raise NotImplementedError("Stack statements are not supported.")
                elif name == "@STACKSIZE":
                    raise NotImplementedError("Stacksize statements are not supported.")
                else:
                    raise ValueError(f"Invalid token {line!r}")

            elif "EQU" in (x := line.split()):
                # An EQU alias: [label] EQU [value]
                if len(x) != 3:
                    raise ValueError(f"Invalid EQU-statement: Wrong number of operands. {line!r} -> {x}")

                label, equ, value = x
                if equ != "EQU":
                    raise ValueError(f"Invalid EQU-statement: Wrong position of EQU keyword. {line!r} -> {x}")

                aliases[label] = self.get_value(value)

            elif segment == "data":
                # lines are [label] DW [value](,[value])*
                #        or [label] DS [length]
                x = line.split(maxsplit=2)

                if len(x) != 3:
                    raise ValueError(f"Invalid data line: {line!r} -> {x}")

                label, op, values = x

                if op == "DW":
                    # Define a single word
                    tokens.append((base.Token.LABEL, label))

                    for i, v in enumerate(values.split(",")):
                        tokens.append((base.Token.DATA, self.get_value(v.strip())))

                    # Improvement: add sizeof(<label>) as an implicit EQU
                    aliases[f"sizeof({label})"] = i + 1
                elif op == "DS":
                    # Define an array
                    tokens.append((base.Token.LABEL, label))
                    size = self.get_value(value.strip())

                    for _ in range(size):
                        tokens.append((base.Token.DATA, 0))

                    aliases[f"sizeof({label})"] = size

            elif segment == "code":
                # check if this is a label
                if ":" in line:
                    label_name, after_label = line.split(":")
                    tokens.append((base.Token.LABEL, label_name))

                    # Check if we need to parse an instruction after the colon
                    after_label = after_label.strip()
                    if not after_label:
                        continue

                    line = after_label

                # continue with the instruction
                try:
                    mnemonic, operands_str = line.split(maxsplit=1)

                    # split operands by regex (because of the optional comma)
                    operands = re.split(r"\s*,?\s+", operands_str)
                except ValueError:  # There was no space after the mnemonic
                    mnemonic, operands = line, []

                known_mnemonics = base.Instructions.get(len(operands), None)

                error_prefix = f"Could not parse {line!r} as code:"

                if not known_mnemonics:
                    raise ValueError(f"{error_prefix} Bad number of operands: {operands}.")

                if mnemonic.upper() not in known_mnemonics:
                    raise ValueError(f"{error_prefix} Unknown mnemonic {mnemonic!r} with {len(operands)} operands.")

                parsed_ops = self.parse_operands(operands)

                # Handle simplified mnemonics
                if mnemonic.upper() == "RTS":
                    if parsed_ops:
                        raise ValueError(f"{error_prefix} RTS instruction takes no operands - got {operands}")

                    mnemonic = "JMP"
                    parsed_ops = [(base.Token.AM_POST_INC, 7)]
                elif mnemonic.upper() == "PUSH":
                    if len(parsed_ops) != 1 or parsed_ops[0][0] != base.Token.AM_REGISTER:
                        raise ValueError(f"{error_prefix} PUSH instruction takes 1 register operand - got {operands}")

                    mnemonic = "STOR"
                    parsed_ops = [parsed_ops[0], (base.Token.AM_PRE_DEC, 7)]
                elif mnemonic.upper() == "PULL":
                    if len(parsed_ops) != 1 or parsed_ops[0][0] != base.Token.AM_REGISTER:
                        raise ValueError(f"{error_prefix} LOAD instruction takes 1 register operand - got {operands}")

                    mnemonic = "LOAD"
                    parsed_ops = [parsed_ops[0], (base.Token.AM_POST_INC, 7)]

                expected_types = base.InstructionOperands[mnemonic.upper()]

                for (got, *_), expected in zip(parsed_ops, expected_types):
                    if got not in expected:
                        raise ValueError(f"{error_prefix} Invalid operand types. Expected operand types {expected_types}, got {parsed_ops}.")

                # Add the line to the segment
                tokens.append((base.Token.MNEMONIC, mnemonic.upper(), parsed_ops))

            else:
                raise ValueError(f"Text outside segment - segment is {segment}")

        return tokens, aliases


    def parse_operands(self, operands: list[str]) -> list[typing.Union[tuple[base.Token, typing.Union[int, str]], tuple[base.Token, int, int]]]:
        """
        Given a list of operands, returns a list of tokenised operands.
        """

        value = r"((?:-?[0-9]+)|(?:#[0-9a-fA-F]+)|(?:%[01]+)|(?:'..?')|(?:\"..?\"))"
        register = r"((?:[rR][0-7])|SP|GB)"

        value_re = re.compile(value)
        register_re = re.compile(register)

        indexed_re = re.compile(r"\s*".join([r"\[", register, r"\+", value, r"\]"]))
        reg_indexed_re = re.compile(r"\s*".join([r"\[", register, r"\+", register, r"\]"]))
        post_inc_re = re.compile(r"\s*".join([r"\[", register, r"\+\+", r"\]"]))
        pre_dec_re = re.compile(r"\s*".join([r"\[", r"--", register, r"\]"]))
        ind_indexed_re = re.compile(r"\s*".join([r"\[", r"\[", register, r"\]", r"\+", value, r"\]"]))
        ind_reg_indexed_re = re.compile(r"\s*".join([r"\[", r"\[", register, r"\]", r"\+", register, r"\]"]))

        tokens = []

        for operand in operands:
            name = operand.strip()

            if value_re.match(name):
                n = self.get_value(name)

                tokens.append((base.Token.AM_VALUE, n))
            elif register_re.match(name):
                n = self.get_reg(name)

                tokens.append((base.Token.AM_REGISTER, n))
            elif (m := indexed_re.match(name)):
                reg, disp = m.groups()

                reg = self.get_reg(reg)
                disp = self.get_value(disp)

                tokens.append((base.Token.AM_INDEXED, reg, disp))
            elif (m := reg_indexed_re.match(name)):
                reg0, reg1 = m.groups()

                reg0 = self.get_reg(reg0)
                reg1 = self.get_reg(reg1)

                tokens.append((base.Token.AM_REG_INDEXED, reg0, reg1))
            elif (m := post_inc_re.match(name)):
                reg, = m.groups()
                reg = self.get_reg(reg)

                tokens.append((base.Token.AM_POST_INC, reg))
            elif (m := pre_dec_re.match(name)):
                reg, = m.groups()
                reg = self.get_reg(reg)

                tokens.append((base.Token.AM_PRE_DEC, reg))
            elif (m := ind_indexed_re.match(name)):
                reg, disp = m.groups()

                reg = self.get_reg(reg)
                disp = self.get_value(disp)

                tokens.append((base.Token.AM_IND_INDEXED, reg, disp))
            elif (m := ind_reg_indexed_re.match(name)):
                reg0, reg1 = m.groups()

                reg0 = self.get_reg(reg0)
                reg1 = self.get_reg(reg1)

                tokens.append((base.Token.AM_IND_REG_INDEXED, reg0, reg1))
            else:  # must be a label
                # TODO: Maybe do some extra checks here?
                tokens.append((base.Token.AM_LABEL, name))

        return tokens



        # for line in self.input:
        #     # ignore everything after ;
        #     line = line.split(';')[0]

        #     # split line into tokens separated by whitespace, be careful, because
        #     # we don't want any spaces inside [] to be split. So, first split on
        #     # [
        #     tokens = line.split('[')
        #     if len(tokens) > 1:
        #         ind = tokens[1].split('+')

        #         # strip everything after ]
        #         ind[-1] = ind[-1].split(']')[0]

        #         if ind:
        #             # a + was found and removed, so add it back in
        #             ind = [ind[0].rstrip(), '+', ind[1].lstrip()]

        #         tokens = tokens[0].split()
        #         tokens.append(ind)
        #     else:
        #         tokens = tokens[0].split()

        #     if '@CODE' in tokens:
        #         if segment == 'code':
        #             raise ValueError('CODE segment can only be started once')

        #         i = tokens.index('@CODE')

        #         if i + 1 < len(tokens):
        #             addr = self.getValue(tokens[i + 1])
        #         else:
        #             addr = 0x3ffff

        #         # length is to be calculated later
        #         len_ = None
        #         self.code = [['@C', addr, len_]]

        #         segment = 'code'

        #     elif '@DATA' in tokens:
        #         if segment == 'data':
        #             raise ValueError('DATA segment can only be started once')

        #         i = tokens.index('@DATA')

        #         if i + 1 < len(tokens):
        #             addr = self.getValue(tokens[i + 1])
        #         else:
        #             addr = 0x3ffff

        #         # length is to be calculated later
        #         len_ = None
        #         self.data = [['@D', addr, len_]]
        #         address = 0
        #         curdatapoint = -1
        #         defining = None

        #         segment = 'data'

        #     elif '@END' in tokens:
        #         break

        #     elif '@INCLUDE' in tokens:
        #         raise NotImplementedError("Include statements are not yet supported.")

        #     elif tokens:
        #         if segment == 'data':

        #             # first token could be a new and unique name
        #             if tokens[0] != curdatapoint:
        #                 name = tokens[0].strip()[:-1]

        #                 assert name not in self.datapoints

        #                 self.datapoints[name] = address
        #                 curdatapoint = name
        #                 tokens = tokens[1:]

        #             for token in tokens:
        #                 if defining == 'array':
        #                     if tokens[i][-1] == ',':
        #                         num = self.getValue(tokens[i][:-1])
        #                     else:
        #                         num = self.getValue(tokens[i])
        #                         defining = None

        #                     self.data += [0] * num
        #                     address += num

        #                 elif defining == 'word':
        #                     if tokens[i][-1] == ',':
        #                         self.data.append(self.getValue(tokens[i][:-1]))
        #                     else:
        #                         self.data.append(self.getValue(tokens[i]))
        #                         defining = None

        #                 elif tokens[i] == 'DS':
        #                     defining = 'array'

        #                 elif tokens[i] == 'DW':
        #                     defining = 'word'

        #         elif segment == 'code':
        #             if 'EQU' in tokens:
        #                 i = tokens.index('EQU')

        #                 # EQU cannot be the first or last element in tokens
        #                 assert 0 < i < len(tokens) - 1

        #                 name = tokens[i - 1].strip()
        #                 value = self.getValue(tokens[i + 1])

        #                 # EQU cannot use a name that's already taken
        #                 assert name not in self.aliases

        #                 self.aliases[name] = value
        #             else:
        #                 self.code.append(tokens)
        #         else:
        #             raise ValueError("No active segment")

        # # replace aliases
        # for i, instruction in enumerate(self.code):
        #     instruction = self.code[i]

        #     for j, operand in enumerate(instruction):
        #         if isinstance(operand, list):
        #             for k in range(len(operand)):
        #                 if operand[k] in self.aliases:
        #                     self.code[i][j][k] = self.aliases[operand[k]]
        #                 elif operand[k] in self.datapoints:
        #                     self.code[i][j][k] = self.datapoints[operand[k]]

        #         elif operand in self.aliases:
        #             self.code[i][j] = self.aliases[operand]
        #         elif operand in self.datapoints:
        #             self.code[i][j] = self.datapoints[operand]

    def get_reg(self, reg_str: str) -> int:
        """
        Converts a register representation to an int
        """
        # Register aliases
        if reg_str == "SP":
            reg_str = "R7"
        elif reg_str == "GB":
            reg_str = "R6"

        r, n = reg_str

        if not (r in "rR" and 0 <= int(n) <= 7):
            raise ValueError(f"Could not parse register {reg_str}")

        return int(n)

    def get_value(self, str_value: str) -> int:
        """
        Converts a literal value to an integer. See section 4.1.
        """
        if str_value.startswith("%"):  # binary
            _, sign_bit, *value_part = str_value
            full_value = "".join(value_part).rjust(18, sign_bit)

            return int(full_value, 2) % 2 ** 18
        elif str_value.startswith("$"):  # hexadecimal
            _, full_value = str_value

            return int(full_value, 16) % 2 ** 18
        elif str_value.startswith("'") or str_value.startswith('"'):  # ascii
            _, *chars, _ = str_value

            # no need for modular reduction, since these values can never exceed
            # 2 ** 18
            if len(chars) == 1:
                return ord(chars[0])
            elif len(chars) != 2:
                raise ValueError(f"Cannot parse value {str_value!r} as ASCII literal: Wrong number of characters ({len(chars)}) - must be 1 or 2.")

            return (ord(chars[1]) << 8) | ord(chars[0])
        else:  # decimal
            return int(str_value, 10) % 2 ** 18
