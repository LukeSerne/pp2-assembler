# Assembler for the PP2
# - because Computer Systems doesn't fix their own assembler
#
# Made in 2018 by Luke Serné
import re

import base
import parser

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

        # parses the code and data sections
        self.parser.parseSections()

        # first do the code segment
        self.assembleCode()

        # TODO: the data segment

    def assembleCode(self):
        segcode = self.parser.code

        # compile the regexes for extra speed
        re_label = re.compile(r"([a-zA-Z][a-zA-Z\d]*)\s*:")

        # relative address
        address = 0

        # Code blocks are blocks of code with no labels in them. They are indexed
        # by a label name
        codeblocks = dict()
        curblock = None

        # skip the opening code
        segcode = segcode[1:]

        print(segcode)

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
