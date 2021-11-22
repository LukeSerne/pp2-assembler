# Assembler for the PP2
# - because Computer Systems doesn't fix their own assembler
#
# Made in 2018 by Luke Serné
import re
import typing

import base
import parser

class Segment:
    address: typing.Optional[int] = None
    size: int = 0
    entries: typing.Union[list[list[int]], list[int], type(None)] = None

    def __init__(self):
        self.entries = []

class Assembler:
    def __init__(self, input_, output_, verbose_):
        self.input = input_
        self.output = output_
        self.verbose = verbose_

    def assemble(self):
        # read input file
        with open(self.input, 'r') as f:
            content = f.read()

        # parse input
        self.parser = parser.Parser(content)

        # parses the code and data sections - tokenises everything, removes
        # comments, gets the aliases and initialises the data
        tokens, aliases = self.parser.parseSections()

        code, data, stack = self.assemble_2(tokens, aliases)

        self.write_output(code, data, stack, self.output)

    def write_output(self, code: Segment, data: Segment, stack: Segment, output_filename: str):
        """
        Writes everything to a hex file.
        """
        with open(output_filename, "w") as f:
            # First code
            f.write(f"@C {code.address:05x} {code.size:05x}\n")

            for instruction in code.entries:
                f.write(" ".join(f"{entry:05x}" for entry in instruction))
                f.write("\n")

            f.write("\n")

            # Then data (optional)
            if data.address is None:
                f.write(f"@D {data.address:05x} {data.size:05x}\n")

                f.write(" ".join(f"{word:05x}" for (_, word) in data.entries))

                f.write("\n\n")

            # Then stack (optional)
            if stack.address is None:
                f.write(f"@S {stack.address:05x} {stack.size:05x}\n")

                f.write("\n")

            # Then end
            f.write(".\n")

    def assemble_2(self, tokens: list, aliases: list) -> tuple:
        """
        Assembles the tokens into more numbers and splits it up into code, data
        and stack. Also converts everything into segments.

        - CODE: Resolves label references, calculates shortest length.
        - DATA: Calculates length
        - STACK: Default (address: 0x3ffff, size: 0xf0)
        """
        # TODO: Split this function into multiple shorter funtions

        # Create the three segments
        data = Segment()
        code = Segment()
        stack = Segment()

        # TODO: Don't hardcode the stack address and size
        stack.address = 0x3ffff
        stack.size = 0xf0

        # Resolve label addresses
        address = 0
        long_form_tokens = []
        all_tokens = []  # code and data tokens - type: list[tuple[int, Token]]

        for token in tokens:
            if token[0] == base.Token.DATA_SEGMENT_START:

                if data.address is not None:
                    raise ValueError("Can only start data segment once")

                data.address = token[1]

            elif token[0] == base.Token.CODE_SEGMENT_START:

                if code.address is not None:
                    raise ValueError("Can only start code segment once")

                code.address = token[1]

            elif token[0] == base.Token.LABEL:
                name = token[1]
                aliases[name] = address

            elif token[0] == base.Token.DATA:
                value = token[1]
                data.entries.append(token)
                all_tokens.append((address, token))

                address += 1

            elif token[0] == base.Token.MNEMONIC:
                _, mnemonic, operands = token
                all_tokens.append((address, token))

                # Check if this instruction will use long form. At this point,
                # we have not yet resolved the labels (they are not even all in
                # the aliases dict). In those cases, we assume the long form is
                # used, and we adjust later.
                if self.maybe_uses_long_form(address, mnemonic, operands, aliases):
                    long_form_tokens.append((address, token))
                    address += 2
                else:
                    address += 1


        # Figure out which instructions truly use long form. Note that since we
        # overestimated the number of long form instructions, only long form
        # instructions will actually use short form, not the other way around.
        while True:
            newly_reduced = {}

            for i, (addr, token) in enumerate(long_form_tokens):
                _, mnemonic, operands = token

                if not self.maybe_uses_long_form(addr, mnemonic, operands, aliases):
                    newly_reduced[i] = addr

            x = len(long_form_tokens)

            # Remove the reduced tokens from the list
            for i in reversed(newly_reduced):
                del long_form_tokens[i]

            assert len(long_form_tokens) + len(newly_reduced) == x

            # No instructions changed from long form to short form - the system
            # reached a stable state.
            if not newly_reduced:
                break

            # Update the addresses of the aliases and tokens
            for alias in aliases:
                value = aliases[alias]

                # maybe reduce it
                count = 0
                for x in newly_reduced.values():
                    if x < value:
                        count += 1

                aliases[alias] -= count

            for i, (address, token) in enumerate(all_tokens):
                # maybe reduce it
                count = 0
                for x in newly_reduced.values():
                    if x < address:
                        count += 1

                address -= count

                all_tokens[i] = (address, token)

        # Resolve all aliases.
        for i, (address, token) in enumerate(all_tokens):
            all_tokens[i] = (address, self.resolve_aliases(address, token, aliases))

        # Calculate data size
        data.size = len(data.entries)

        # Fill code segment
        code.size = 0

        for address, token in all_tokens:
            if token[0] == base.Token.DATA:
                continue

            if token[0] != base.Token.MNEMONIC:
                raise ValueError(f"Bad code token {token}")

            _, mnemonic, operands = token

            encoding = self.encode_mnemonic(mnemonic, operands)
            code.entries.append(encoding)
            code.size += len(encoding)

            # TODO: Deduce mnemonic and operands from encoding
            if len(encoding) == 2:
                encoding_str = f"{encoding[0]:05x} {encoding[1]:05x}"
            else:
                encoding_str = f"{encoding[0]:05x} {'':5}"

            if self.verbose:
                print(f"{address:05x} {encoding_str} {mnemonic:5} {self.operands_to_str(operands)}")

        return code, data, stack

    def resolve_aliases(self, address: int, token: tuple, aliases: dict) -> tuple[base.Token, list]:
        type_ = token[0]
        if type_ == base.Token.MNEMONIC:
            _, mnemonic, operands = token

            new_operands = []
            for operand in operands:
                operand_type = operand[0]

                if operand_type == base.Token.AM_LABEL:
                    name = operand[1]
                    value = aliases[name]

                    if mnemonic in base.BranchInstructions:
                        if self.uses_long_form(address, mnemonic, operands, aliases):
                            delta = 2
                        else:
                            delta = 1

                        value -= address + delta
                        value %= 2 ** 18

                    new_operands.append((base.Token.AM_VALUE, value))

                elif operand_type in base.Token.AM_INDEXED | base.Token.AM_IND_INDEXED:
                    value = operand[2]

                    if isinstance(value, str):
                        value = aliases[value]

                    new_operands.append((operand_type, operand[1], value))
                else:
                    new_operands.append(operand)

            return (type_, mnemonic, new_operands)

        if type_ == base.Token.DATA:
            return token

        return token

    def maybe_uses_long_form(self, address: int, mnemonic: str, operands: list, aliases: dict[str, int] = {}) -> bool:
        return self._uses_long_form(address, mnemonic, operands, aliases) is not False

    def uses_long_form(self, address: int, mnemonic: str, operands: list, aliases: dict[str, int] = {}) -> bool:
        return self._uses_long_form(address, mnemonic, operands, aliases) is True

    def _uses_long_form(self, address: int, mnemonic: str, operands: list, aliases: dict[str, int] = {}) -> typing.Optional[bool]:
        """
        Returns None on unknown label.
        """

        for operand in operands:
            type_ = operand[0]

            if type_ in base.Token.AM_LABEL | base.Token.AM_VALUE:
                if type_ == base.Token.AM_LABEL:
                    name = operand[1]

                    if name not in aliases:
                        return None

                    value = aliases[name]
                else:
                    value = operand[1]

                if mnemonic in base.BranchInstructions:
                    # Do we need long form, assuming this instruction is not
                    # long form?
                    value -= address + 1
                    value %= 2 ** 18
                    size = 9

                else:
                    size = 8

                if 2 ** (size - 1) <= value < 2 ** 18 - 2 ** (size - 1):
                    return True

            if type_ in base.Token.AM_INDEXED | base.Token.AM_IND_INDEXED:
                value = operand[2]

                if isinstance(value, str):
                    if value not in aliases:
                        return None

                    value = aliases[value]

                if not 0 <= value < 31:
                    return True

        return False

    def operands_to_str(self, operands: list) -> str:
        """
        Converts a list of operands to a nice string.
        """
        def operand_to_str(operand) -> str:
            type_ = operand[0]

            if type_ == base.Token.AM_LABEL:
                return f"{operand[1]}"
            if type_ == base.Token.AM_VALUE:
                return f"0x{operand[1]:05x}"
            if type_ == base.Token.AM_REGISTER:
                return f"r{operand[1]}"
            if type_ == base.Token.AM_INDEXED:
                return f"[r{operand[1]} + 0x{operand[2]:05x}]"
            if type_ == base.Token.AM_REG_INDEXED:
                return f"[r{operand[1]} + r{operand[2]}]"
            if type_ == base.Token.AM_POST_INC:
                return f"[r{operand[1]}++]"
            if type_ == base.Token.AM_PRE_DEC:
                return f"[--r{operand[1]}]"
            if type_ == base.Token.AM_IND_INDEXED:
                return f"[[r{operand[1]}] + 0x{operand[2]:05x}]"
            if type_ == base.Token.AM_IND_REG_INDEXED:
                return f"[[r{operand[1]}] + r{operand[2]}]"

            return f"{operand}"

        return ", ".join(
            operand_to_str(operand)
            for operand in operands
        )

    def encode_addressing_mode(self, addressing_mode: int) -> list[int]:
        """
        List of words - 2 iff long form. Empty list if unknown addressing mode.
        """
        mode = addressing_mode[0]
        use_long_form = False
        value = 0

        if mode == base.Token.AM_VALUE:
            aaa = 0
            value = addressing_mode[1]

            if 2 ** 7 <= value < 2 ** 18 - 2 ** 7:
                # long form required
                sss = 1 << 7
                use_long_form = True
            else:
                sss = value & 0xFF

        elif mode == base.Token.AM_REGISTER:
            aaa = 1
            sss = addressing_mode[1] & 7

        elif mode == base.Token.AM_INDEXED:
            _, reg, value = addressing_mode

            aaa = 4
            sss = (reg & 7) << 5

            if not (0 <= value <= 30):
                # long form required
                sss |= 31
                use_long_form = True
            else:
                sss |= value & 0x1F

        elif mode == base.Token.AM_REG_INDEXED:
            _, reg0, reg1 = addressing_mode

            aaa, sss = 5, ((reg0 & 7) << 5) | (reg1 & 7)

        elif mode == base.Token.AM_POST_INC:
            reg = addressing_mode[1]

            aaa, sss = 5, ((reg & 7) << 5) | 0b10_001

        elif mode == base.Token.AM_PRE_DEC:
            reg = addressing_mode[1]

            aaa, sss = 5, ((reg & 7) << 5) | 0b11_111

        elif mode == base.Token.AM_IND_INDEXED:
            _, reg, value = addressing_mode

            aaa = 6
            sss = (reg & 7) << 5

            if not (0 <= value <= 30):
                # long form required
                sss |= 31
                use_long_form = True
            else:
                sss |= value & 0x1F

        elif mode == base.Token.AM_IND_REG_INDEXED:
            _, reg0, reg1 = addressing_mode

            aaa, sss = 7, (reg0 & 7) << 5 | (reg1 & 7)

        else:
            # Invalid addressing mode - return empty list
            return []

        # NOTE: 2 and 3 are reserved for future additions
        assert aaa not in (2, 3)

        result = [(aaa << 8) | sss]

        if use_long_form:
            result.append(value)

        return result

    def encode_mnemonic(self, mnemonic: str, operands: list[tuple[base.Token, int]]) -> list[int]:
        """
        Encodes a mnemonic to a list of words as integers.
        """
        if mnemonic == "CONS":
            # Cons is so simple - special case it
            assert len(operands) == 1 and operands[0][0] == base.Token.AM_VALUE
            return [operands[0][1]]

        if mnemonic == "RTE":
            # RTE is so unique - hardcode it
            assert not operands
            return [0b0000_100_101_111_10_001]

        if mnemonic in base.BranchInstructions:

            assert len(operands) == 1 and operands[0][0] == base.Token.AM_VALUE
            opcode = [
                "BRA", "BRS", "BEQ", "BNE", "BCS", "BCC", "BLS", "BHI", "BVC",
                "BVS", "BPL", "BMI", "BLT", "BGE", "BLE", "BGT"
            ].index(mnemonic)

            displacement = operands[0][1]
            if 2 ** 8 <= displacement < 2 ** 18 - 2 ** 8:
                # need long form
                values = [1 << 8, displacement]
            else:
                values = [displacement & ((1 << 9) - 1)]

            encoded = ((opcode & 0xF) << 9) | (values[0] & 0x1FF)

            # now save it
            result = [encoded]

            if len(values) == 2:
                result.append(values[1])

            return result

        if mnemonic in base.Traps:
            assert not operands

            if mnemonic == "RST":
                return [0b0000_111_0000_0_000000]

            traps = ["TRA0", "TRA1", "TREQ", "TRNE", "TRCS", "TRCC", "TRLS", "TRHI", "TRVC", "TRVS", "TRPL", "TRMI", "TRLT", "TRGE", "TRLE", "TRGT"]
            id_ = traps.index(mnemonic)

            return [(7 << 11) | (id_ << 7) | (1 << 4) | id_]

        if mnemonic in base.UnaryInstructions:
            un_insn = ["JMP", "JSR", "CLRI", "SETI", "PSEM", "VSEM"]
            id_ = un_insn.index(mnemonic)

            addressing_encoding = self.encode_addressing_mode(operands[0])

            if not addressing_encoding:
                raise ValueError(f"Invalid addressing mode {operands[0]}")

            result = [(1 << 14) | (id_ << 11) | addressing_encoding[0] & 0x7FF]

            if len(addressing_encoding) == 2:
                result.append(addressing_encoding[1])

            return result

        if mnemonic in base.BinaryInstructions:
            # TODO: Move to base.py or something
            binary_opcodes = ["LOAD", "ADD", "SUB", "CMP", "MULS", "MULL", "CHCK", "DIV", "MOD", "DVMOD", "AND", "OR", "XOR", "STOR"]

            # Encode the various parts
            opcode = 2 + binary_opcodes.index(mnemonic)
            reg = operands[0][1]
            addressing_encoding = self.encode_addressing_mode(operands[1])

            if not addressing_encoding:
                raise ValueError(f"Invalid addressing mode {operands[1]}")

            encoded = ((opcode & 0xF) << 14) | ((reg & 7) << 11) | (addressing_encoding[0] & 0x7FF)

            # now save it
            result = [encoded]

            if len(addressing_encoding) == 2:
                result.append(addressing_encoding[1])

            return result

        if mnemonic in base.Instructions[len(operands)]:
            raise ValueError(f"Unimplemented instruction {mnemonic} with {len(operands)} operands.")

        raise ValueError(f"Unknown instruction {mnemonic} with {len(operands)} operands.")
