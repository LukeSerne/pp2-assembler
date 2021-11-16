import enum

class AddressingMode(enum.Enum):
    VALUE = enum.auto()
    REGISTER = enum.auto()
    INDEXED = enum.auto()
    REG_INDEXED = enum.auto()
    AUTO_POST_INC = enum.auto()
    AUTO_PRE_DEC = enum.auto()
    IND_INDEXED = enum.auto()
    IND_REG_INDEXED = enum.auto()
