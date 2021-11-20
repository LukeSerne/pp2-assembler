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

        self.write_output(code, data, stack, f"test/test.hex")

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
            f.write(f"@D {data.address:05x} {data.size:05x}\n")

            f.write(" ".join(f"{word:05x}" for (_, word) in data.entries))

            f.write("\n\n")

            # Then stack (optional)
            f.write(f"@S {stack.address:05x} {stack.size:05x}\n")

            f.write("\n")

            # Then end
            f.write(".\n\n")



    def assemble_2(self, tokens, aliases) -> tuple:
        """
        Assembles the tokens into more numbers and splits it up into code, data
        and stack. Also converts everything into segments.

        - CODE: Resolves label references, calculates shortest length.
        - DATA: Calculates length
        - STACK: Default (address: 0x3ffff, size: 0xf0)
        """

        # Code blocks are blocks of code with no labels in them. They are indexed
        # by a label name
        codeblocks = {}
        curblock = None

        # Aggregate all data in this list
        data = Segment()
        code = Segment()
        stack = Segment()

        # TODO: Don't hardcode this
        stack.address = 0x3ffff
        stack.size = 0xf0

        # Resolve label addresses
        next_segment_start = address = 0
        possible_gaps = []

        addressed_tokens = {}  # dict[int, base.Token]
        long_form_tokens = []
        all_tokens = []  # code and data tokens
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
                addressed_tokens[address] = token
                data.entries.append(token)
                all_tokens.append((address, token))

                address += 1

            elif token[0] == base.Token.MNEMONIC:
                _, mnemonic, operands = token
                addressed_tokens[address] = token
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

        print("Done!")
        print(long_form_tokens)
        print(aliases)

        # Resolve all aliases.
        for i, (address, token) in enumerate(all_tokens):
            all_tokens[i] = (address, self.resolve_aliases(address, token, aliases))

        del address
        del token
        del i
        del value

        # Calculate data size
        data.size = len(data.entries)

        # Fill code segment
        code.size = 0

        # TODO: Don't assume code starts at data.size
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

            print(f"{address:05x} {encoding_str} {mnemonic:5} {self.operands_to_str(operands)}")

        return code, data, stack

    def resolve_aliases(self, address: int, token: ..., aliases: dict) -> tuple[base.Token, list]:
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

    def maybe_uses_long_form(self, *args):
        return self._uses_long_form(*args) is not False

    def uses_long_form(self, *args):
        return self._uses_long_form(*args) is True

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

            result = [(1 << 14) | (id_ << 11) | addressing_encoding[0]]

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


        # get out all labels
        for command in segcode:

            # if this command is a label ...
            if command[1] == ":":
                # save its relative address in a dict
                name = command[0]

                # check if label was already used
                if name in codeblocks:
                    raise ValueError("label '%s' used multiple times" % name)

                codeblocks[name] = []
                curblock = codeblocks[name]

                if len(command) > 2:
                    curblock.append(self.parseInstruction(command[2:]))

            else:
                if curblock is None:
                    # maybe the file doesn't start with a label
                    print("Warning! Instruction detected before first label!")
                    codeblocks[0] = []
                    curblock = codeblocks[0]

                curblock.append(self.parseInstruction(command))

        # now pass over everything to convert to byte code
        byteblocks = {}

        UnOPToValList = ['jmp', 'jsr', 'clri', 'seti', 'psem', 'vsem']
        BrOPToValList = ['bra', 'brs', 'beq', 'bne', 'bcs', 'bcc', 'bls', 'bhi'
                        'bvc', 'bvs', 'bpl', 'bmi', 'blt', 'bge', 'ble', 'bgt']
        BinOPToValList = [None, None, 'load', 'add', 'sub', 'cmp', 'muls', 'mull'
                        'chck', 'div', 'mod', 'dvmd', 'and', 'or', 'xor', 'stor']

        for label in codeblocks:
            print('parsing label %s...' % label)
            code = codeblocks[label]

            for instruction in code:
                if len(instruction) == 3:
                    # binary instruction
                    opc = BinOPToValList.index(instruction[0].lower())
                    reg = instruction[1]

                    if isinstance(instruction[2], list):
                        # long form
                        val = instruction[2][0]

                        encoded = ((opc & 0xF) << 14) | ((reg & 7) << 11) | (val & 0x7FF)

                        # now save it
                        byteblocks[label].append(encoded)
                        byteblocks[label].append(instruction[2][1])
                    else:
                        # short form
                        val = instruction[2]

                        encoded = ((opc & 0xF) << 14) | ((reg & 7) << 11) | (val & 0x7FF)

                        byteblocks[label].append(encoded)

                elif len(instruction) == 2:
                    print(f"Not yet implemented unary instruction: {instruction}")

        print(byteblocks)

    def parseInstruction(self, command: list):
        name = command[0].upper()

        # TODO: PSEM and VSEM are both in NoOperandInstructions and
        # UnaryInstructions. Check how the official assembler handles
        # this case.
        if name in {'PSEM', 'VSEM'}:
            raise NotImplementedError("PSEM and VSEM cannot be used yet.")

        # add this instruction to the current code block
        if len(command) == 1:
            if name not in NoOperandInstructions:
                raise ValueError(f"Unsupported instruction {name!r} (as {command})")
            instruction = [name]

        elif len(command) == 2 and name not in {"PUSH", "PULL"}:
            if name not in EffectiveUnary:
                raise ValueError(f"Unsupported instruction {name!r} (as {command})")
            instruction = [name, command[1]]

        else:
            # push/pull translation
            if name == "PUSH":
                name = "STOR"
                command = [name, '[--R7]']
            elif name == "PULL":
                name = "LOAD"
                command = [name, '[R7++]']

            if name not in BinaryInstructions:
                raise ValueError(f"Unsupported instruction {name!r} (as {command})")

            # binary instruction, followed by a register and address/value/register
            register = command[1]
            other = command[2]

            # encode it
            try:
                register = self.parser.getRegister(register)
            except ValueError:
                raise ValueError(f"Could not parse register {register!r} of command {command!r}")
            other, longval = self.assembleAddress(other, name)
            instruction = [name, register, other]

            # long value
            if longval is not None:
                instruction[-1] = [other, longval]

        return instruction

    def assembleAddress(self, address, instruction):
        """
        Assembles an address
        """
        # check input
        if not self.parser.isValidAddressThing(address):
            raise ValueError("%s \"%s\" cannot be represented by an addressing mode" % (str(address), instruction))

        # get mode
        mode = self.parser.getAddressingMode(address)

        # by default, use a short instruction
        long_ = False

        if mode == base.AddressingMode.VALUE:
            if instruction in ["psem", "vsem", "stor", "jmp", "jsr"]:
                raise ValueError("direct values cannot be used with instruction %s" % instruction.upper())

            value = self.parser.getValue(address)

            if value > 254:
                long_ = True
                longval = value
                value = 0xFF

        elif mode == base.AddressingMode.REGISTER:
            if instruction in ["psem", "vsem", "stor"]:
                raise ValueError("direct registers cannot be used with instruction %s" % instruction.upper())

            value = self.parser.getRegister(address)

        elif mode == base.AddressingMode.INDEXED:
            # [reg + disp]
            reg, dsp = address[0], address[2]

            reg = self.parser.getRegister(reg)
            dsp = self.parser.getValue(dsp)

            # maybe use long form
            if dsp > 30:
                long_ = True
                longval = disp
                dsp = 0x1F

            value = (reg << 5) | (dsp & 0x1F)

        elif mode == base.AddressingMode.REG_INDEXED:
            # [reg0 + reg1]
            reg0, reg1 = address[0], address[2]

            reg0 = self.parser.getRegister(reg0)
            reg1 = self.parser.getRegister(reg1)

            value = (reg0 << 5) | reg1

        elif mode == base.AddressingMode.AUTO_POST_INC:
            # [reg++]
            reg = address[0][1:-3]
            reg = self.parser.getRegister(reg)

            value = (reg << 5) | 0x11

        elif mode == base.AddressingMode.AUTO_PRE_DEC:
            # [--reg]
            reg = address[0][3:-1]
            reg = self.parser.getRegister(reg)

            value = (reg << 5) | 0x1F

        elif mode == base.AddressingMode.IND_INDEXED:
            # [[reg] + dsp]
            reg, dsp = address[0], address[2]
            reg = reg0[1:-1]

            reg = self.parser.getRegister(reg)
            dsp = self.parser.getValue(dsp)

            # maybe use long form
            if dsp > 30:
                long_ = True
                longval = disp
                dsp = 0x1F

            value = (reg << 5) | (dsp & 0x1F)

        elif mode == base.AddressingMode.IND_REG_INDEXED:
            # [[reg0] + reg1]
            reg0, reg1 = address[0], address[2]
            reg0 = reg0[1:-1]

            reg0 = self.parser.getRegister(reg0)
            reg1 = self.parser.getRegister(reg1)

            value = (reg0 << 5) | reg1

        if not long_:
            longval = None

        if mode == 3 or mode == 4:
            encoded = 5
        elif mode == 2:
            encoded = 4
        else:
            encoded = mode

        return ((encoded << 8) | (value & 0xFF), longval)
