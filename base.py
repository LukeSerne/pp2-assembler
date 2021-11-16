import enum

class AddressingMode(enum.Flag):
    LABEL_VALUE         = 0x0001
    VALUE               = 0x0002
    REGISTER            = 0x0004
    INDEXED             = 0x0008
    REG_INDEXED         = 0x0010
    POST_INC            = 0x0020
    PRE_DEC             = 0x0040
    IND_INDEXED         = 0x0080
    IND_REG_INDEXED     = 0x0100

    ANY_ADDRESSING_MODE = 0x01FF

class Token(enum.Flag):
    AM_LABEL            = 0x0001
    AM_VALUE            = 0x0002
    AM_REGISTER         = 0x0004
    AM_INDEXED          = 0x0008
    AM_REG_INDEXED      = 0x0010
    AM_POST_INC         = 0x0020
    AM_PRE_DEC          = 0x0040
    AM_IND_INDEXED      = 0x0080
    AM_IND_REG_INDEXED  = 0x0100

    ANY_ADDRESSING_MODE = 0x01FF

    DATA                = 0x0200
    MNEMONIC            = 0x0400
    LABEL               = 0x0800
    CODE_SEGMENT_START  = 0x1000
    DATA_SEGMENT_START  = 0x2000


# Section 4.4
BinaryInstructions = {
    "LOAD", "ADD", "SUB", "CMP", "MULS", "MULL", "CHCK", "DIV", "MOD", "DVMOD",
    "AND", "OR", "XOR", "STOR"
}

# Section 4.5
UnaryInstructions = {
    "JMP", "JSR", "CLRI", "SETI", "PSEM", "VSEM"
}

# Section 4.6
BranchInstructions = {
    "BRA", "BRS", "BEQ", "BNE", "BCS", "BCC", "BLS", "BHI", "BVC", "BVS", "BPL",
    "BMI", "BLT", "BGE", "BLE", "BGT"
}

# Section 4.7
Traps = {
    "TRA0", "TRA1", "TREQ", "TRNE", "TRCS", "TRCC", "TRLS", "TRHI", "TRVC",
    "TRVS", "TRPL", "TRMI", "TRLT", "TRGE", "TRLE", "TRGT", "RST"
}

# Section 4.8
MiscInstructions = {
    "RTS", "RTE", "PUSH", "PULL", "CONS"
}

# Dict to map number of operands to possible mnemonics
Instructions = {
    0: Traps | {"RTS", "RTE"},
    1: UnaryInstructions | BranchInstructions | {"PUSH", "PULL", "CONS"},
    2: BinaryInstructions,
}

# Dict to map the mnemonic to operand types
InstructionOperands = {

    "RTE": [],
    "TRA0": [], "TRA1": [], "TREQ": [], "TRNE": [], "TRCS": [], "TRCC": [], "TRLS": [], "TRHI": [], "TRVC": [],
    "TRVS": [], "TRPL": [], "TRMI": [], "TRLT": [], "TRGE": [], "TRLE": [], "TRGT": [], "RST": [],

    "JMP": [Token.ANY_ADDRESSING_MODE ^ Token.AM_VALUE],
    "JSR": [Token.ANY_ADDRESSING_MODE ^ Token.AM_VALUE],
    "CLRI": [Token.AM_VALUE],
    "SETI": [Token.AM_VALUE],
    "PSEM": [Token.ANY_ADDRESSING_MODE ^ Token.AM_VALUE ^ Token.AM_REGISTER],
    "VSEM": [Token.ANY_ADDRESSING_MODE ^ Token.AM_VALUE ^ Token.AM_REGISTER],
    "BRA": [Token.AM_LABEL],
    "BRS": [Token.AM_LABEL],
    "BEQ": [Token.AM_LABEL],
    "BNE": [Token.AM_LABEL],
    "BCS": [Token.AM_LABEL],
    "BCC": [Token.AM_LABEL],
    "BLS": [Token.AM_LABEL],
    "BHI": [Token.AM_LABEL],
    "BVC": [Token.AM_LABEL],
    "BVS": [Token.AM_LABEL],
    "BPL": [Token.AM_LABEL],
    "BMI": [Token.AM_LABEL],
    "BLT": [Token.AM_LABEL],
    "BGE": [Token.AM_LABEL],
    "BLE": [Token.AM_LABEL],
    "BGT": [Token.AM_LABEL],

    "CONS": [Token.AM_VALUE],

    "LOAD": [Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE],
    "ADD":  [Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE],
    "SUB":  [Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE],
    "CMP":  [Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE],
    "MULS": [Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE],
    "MULL": [Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE],
    "CHCK": [Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE],
    "DIV":  [Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE],
    "MOD":  [Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE],
    "DVMOD":[Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE],
    "AND":  [Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE],
    "OR":   [Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE],
    "XOR":  [Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE],
    "STOR": [Token.AM_REGISTER, Token.ANY_ADDRESSING_MODE ^ Token.AM_VALUE ^ Token.AM_REGISTER],
}