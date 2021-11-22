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
    def __init__(self, input_string):
        """
        Initialises the parser
        """
        self.input = input_string
        self.input_pos = 0

    def get_next_term(self, peek: bool = False, extra_delimiters: str = "", match_parentheses: bool = False) -> typing.Optional[str]:
        """
        Returns the next non-comment space separated word (or any other delimiter).
        If peek is set to True, the 'input_pos' will not be advanced. If
        match_parentheses is set to True, square bracket parentheses will be
        matched.
        """
        pos = self.input_pos

        # Loop to exit comment
        while True:
            # Skip until the first non-whitespace character, ie. not one of:
            # ' ', '\n', '\t', '\r', '\f' and '\v'
            while pos < len(self.input) and self.input[pos].isspace():
                pos += 1

            # Return None to signal end of file
            if pos == len(self.input):
                if not peek:
                    self.input_pos = pos

                return None

            if self.input[pos] != ";":
                break

            pos = 1 + self.input.find("\n", pos)

            if pos == 0:  # No newline found - return None
                if not peek:
                    self.input_pos = pos

                return None

        # Find the end of the word by finding the next whitespace character.
        end_pos = pos
        nesting = 0
        while end_pos < len(self.input):
            if self.input[end_pos] == "[":
                nesting += 1
            elif self.input[end_pos] == "]":
                nesting -= 1

            if (not match_parentheses or nesting == 0) and (self.input[end_pos].isspace() or self.input[end_pos] == ";" or self.input[end_pos] in extra_delimiters):
                break

            end_pos += 1

        result = self.input[pos:end_pos]

        if self.input[end_pos] in extra_delimiters:
            end_pos += 1

        # Update the input_pos value
        if not peek:
            self.input_pos = end_pos

        return result

    def parseSections(self) -> list:
        # process the file line by line
        segment = None  # 'code', 'data' or None
        aliases = {}
        tokens = []

        # Tokenise based on spaces
        while (term := self.get_next_term()) is not None:

            if term == "@CODE":
                if self.get_next_term(peek=True) == "=":
                    self.get_next_term()  # To consume the '='

                    term = self.get_next_term()
                    address = self.get_value(self.get_next_term())
                    if address is None:
                        raise ValueError(f"Expected a number literal after '@CODE =' - got {term!r}")
                else:
                    address = 0x3ffff

                tokens.append((base.Token.CODE_SEGMENT_START, address))
                segment = "code"

            elif term == "@DATA":
                if self.get_next_term(peek=True) == "=":
                    self.get_next_term()  # To consume the '='

                    term = self.get_next_term()
                    address = self.get_value(term)
                    if address is None:
                        raise ValueError(f"Expected a number literal after '@DATA =' - got {term!r}")
                else:
                    address = 0x3ffff

                tokens.append((base.Token.DATA_SEGMENT_START, address))
                segment = "data"

            elif term == "@END":
                break
            elif term in {"@STACK", "@STACKSIZE", "@INCLUDE"}:
                raise NotImplementedError(f"Statement {term} is not supported.")

            elif self.get_next_term(peek=True) == "EQU":
                # An EQU alias: [term] EQU [value]
                self.get_next_term()  # To consume the 'EQU'
                value_term = self.get_next_term()
                value = self.get_value(value_term)

                if value is None:
                    raise ValueError(f"Expected a number literal after '{term} EQU' - got {value_term!r}")

                aliases[term] = value

            elif segment == "data":
                # lines are [term]:? DW [value](,[value])*
                #        or [term]:? DS [length]

                label = term.removesuffix(":")
                op = self.get_next_term()

                if op == "DW":
                    # Define some words
                    tokens.append((base.Token.LABEL, label))

                    count = 0

                    while (value := self.get_value(self.get_next_term(peek=True, extra_delimiters=","))) is not None:
                        self.get_next_term(extra_delimiters=",")  # to consume the value
                        tokens.append((base.Token.DATA, value))
                        count += 1

                    # Improvement: add sizeof(<label>) as an implicit EQU
                    aliases[f"sizeof({label})"] = count

                elif op == "DS":
                    # Define an array ("storage")
                    tokens.append((base.Token.LABEL, label))
                    size = self.get_value(self.get_next_term())

                    for _ in range(size):
                        tokens.append((base.Token.DATA, 0))

                    # Improvement: add sizeof(<label>) as an implicit EQU
                    aliases[f"sizeof({label})"] = size

                else:
                    raise ValueError(f"Unknown data definition type: {op!r}")

            elif segment == "code":
                # check if this is a label
                if term.endswith(":"):
                    label = term.removesuffix(":")
                    tokens.append((base.Token.LABEL, label))
                else:
                    # Mnemonics are case-insensitive
                    mnemonic = term.upper()

                    for operands_count in base.Instructions:
                        if mnemonic in base.Instructions[operands_count]:
                            break
                    else:
                        raise ValueError(f"Unknown mnemonic {term!r} encountered.")

                    operands = []
                    for i in range(operands_count):
                        operands.append(self.get_next_term(match_parentheses=True))

                    parsed_ops = self.parse_operands(operands)

                    mnemonic, parsed_ops = self.handle_simplified_mnemonics(mnemonic, parsed_ops)

                    expected_types = base.InstructionOperands[mnemonic]

                    for (got, *_), expected in zip(parsed_ops, expected_types):
                        if got not in expected:
                            raise ValueError(f"Invalid operand types. Expected operand types {expected_types}, got {parsed_ops}.")

                    # Add the line to the segment
                    tokens.append((base.Token.MNEMONIC, mnemonic, parsed_ops))

            else:
                raise ValueError(f"Term {term!r} outside segment - segment is {segment}")

        return tokens, aliases

    def handle_simplified_mnemonics(self, mnemonic: str, parsed_ops: list) -> tuple[str, list]:
        """
        This function translates the simplified mnemonic into their full form.
        """
        if mnemonic == "RTS":
            # JMP [SP++] -> JMP [r7++]
            return "JMP", [(base.Token.AM_POST_INC, 7)]

        if mnemonic == "PUSH":
            if parsed_ops[0][0] != base.Token.AM_REGISTER:
                raise ValueError(f"PUSH instruction takes a register operand - got {parsed_ops}")

            # STOR rX, [--SP] -> STOR rX, [--r7]
            return "STOR", [parsed_ops[0], (base.Token.AM_PRE_DEC, 7)]

        if mnemonic == "PULL":
            if parsed_ops[0][0] != base.Token.AM_REGISTER:
                raise ValueError(f"PULL instruction takes a register operand - got {parsed_ops}")

            # LOAD rX, [SP++] -> LOAD rX, [r7++]
            return "LOAD", [parsed_ops[0], (base.Token.AM_POST_INC, 7)]

        return mnemonic, parsed_ops

    def parse_operands(self, operands: list[str]) -> list[typing.Union[tuple[base.Token, typing.Union[int, str]], tuple[base.Token, int, int]]]:
        """
        Given a list of operands, returns a list of tokenised operands.
        """

        value_or_label = r"((?:-?\s*[0-9]+)|(?:\$[0-9a-fA-F]+)|(?:%[01]+)|(?:'..?')|(?:\"..?\")|(?:[a-zA-Z0-9_]+))"
        register = r"((?:[rR][0-7])|SP|GB)"

        value_re = re.compile(value_or_label)
        register_re = re.compile(register)

        indexed_re = re.compile(r"\s*".join([r"\[", register, r"[\+-]", value_or_label, r"\]"]))
        reg_indexed_re = re.compile(r"\s*".join([r"\[", register, r"\+", register, r"\]"]))
        post_inc_re = re.compile(r"\s*".join([r"\[", register, r"\+\+", r"\]"]))
        pre_dec_re = re.compile(r"\s*".join([r"\[", r"--", register, r"\]"]))
        ind_indexed_re = re.compile(r"\s*".join([r"\[", r"\[", register, r"\]", r"[\+-]", value_or_label, r"\]"]))
        ind_reg_indexed_re = re.compile(r"\s*".join([r"\[", r"\[", register, r"\]", r"\+", register, r"\]"]))

        tokens = []

        for operand in operands:
            name = operand.strip()

            if register_re.fullmatch(name):
                n = self.get_reg(name)

                tokens.append((base.Token.AM_REGISTER, n))
            elif (m := reg_indexed_re.fullmatch(name)):
                reg0, reg1 = m.groups()

                reg0 = self.get_reg(reg0)
                reg1 = self.get_reg(reg1)

                tokens.append((base.Token.AM_REG_INDEXED, reg0, reg1))
            elif (m := indexed_re.fullmatch(name)):
                reg, disp = m.groups()

                reg = self.get_reg(reg)
                res = self.get_value(disp)

                # If disp is a label, it cannot be resolved, so keep the string
                if res is not None:
                    disp = res

                tokens.append((base.Token.AM_INDEXED, reg, disp))
            elif (m := post_inc_re.fullmatch(name)):
                reg, = m.groups()
                reg = self.get_reg(reg)

                tokens.append((base.Token.AM_POST_INC, reg))
            elif (m := pre_dec_re.fullmatch(name)):
                reg, = m.groups()
                reg = self.get_reg(reg)

                tokens.append((base.Token.AM_PRE_DEC, reg))
            elif (m := ind_indexed_re.fullmatch(name)):
                reg, disp = m.groups()

                reg = self.get_reg(reg)
                res = self.get_value(disp)

                # If disp is a label, it cannot be resolved, so keep the string
                if res is not None:
                    disp = res

                tokens.append((base.Token.AM_IND_INDEXED, reg, disp))
            elif (m := ind_reg_indexed_re.fullmatch(name)):
                reg0, reg1 = m.groups()

                reg0 = self.get_reg(reg0)
                reg1 = self.get_reg(reg1)

                tokens.append((base.Token.AM_IND_REG_INDEXED, reg0, reg1))
            elif value_re.fullmatch(name):
                n = self.get_value(name)

                if n is not None:
                    tokens.append((base.Token.AM_VALUE, n))
                else:
                    tokens.append((base.Token.AM_LABEL, name))

            else:  # must be a label
                print(f"Warning: Unknown operand thing: {name!r} - assuming it's a label")
                tokens.append((base.Token.AM_LABEL, name))

        return tokens

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

    def get_value(self, str_value: str) -> typing.Optional[int]:
        """
        Converts a literal value to an integer. See section 4.1.
        Returns None on failure.
        """
        try:
            if str_value.startswith("%"):  # binary
                _, sign_bit, *value_part = str_value
                full_value = "".join(value_part).rjust(18, sign_bit)

                return int(full_value, 2) % 2 ** 18
            elif str_value.startswith("$"):  # hexadecimal
                full_value = str_value[1:]

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
        except ValueError:
            return None
