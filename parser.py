import base

class Parser:
    def __init__(self, input_):
        """
        Initialises the parser
        """
        self.input = input_
        self.code = []
        self.data = []

    def parseSections(self):
        # process the file line by line
        segment = None
        self.aliases = dict()
        self.datapoints = dict()

        for line in self.input:
            # ignore everything after ;
            line = line.split(';')[0]

            # split line into tokens separated by whitespace, be careful, because
            # we don't want any spaces inside [] to be split. So, first split on
            # [
            tokens = line.split('[')
            if len(tokens) > 1:
                ind = tokens[1].split('+')

                # strip everything after ]
                ind[-1] = ind[-1].split(']')[0]

                if ind:
                    # a + was found and removed, so add it back in
                    ind = [ind[0].rstrip(), '+', ind[1].lstrip()]

                tokens = tokens[0].split()
                tokens.append(ind)
            else:
                tokens = tokens[0].split()

            if '@CODE' in tokens:
                if segment == 'code':
                    raise ValueError('CODE segment can only be started once')

                i = tokens.index('@CODE')

                if i + 1 < len(tokens):
                    addr = self.getValue(tokens[i + 1])
                else:
                    addr = 0x3ffff

                # length is to be calculated later
                len_ = None
                self.code = [['@C', addr, len_]]

                segment = 'code'

            elif '@DATA' in tokens:
                if segment == 'data':
                    raise ValueError('DATA segment can only be started once')

                i = tokens.index('@DATA')

                if i + 1 < len(tokens):
                    addr = self.getValue(tokens[i + 1])
                else:
                    addr = 0x3ffff

                # length is to be calculated later
                len_ = None
                self.data = [['@D', addr, len_]]
                address = 0
                curdatapoint = -1
                defining = None

                segment = 'data'

            elif '@END' in tokens:
                break

            elif '@INCLUDE' in tokens:
                raise NotImplementedError("Include statements are not yet supported.")

            elif tokens:
                if segment == 'data':

                    # first token could be a new and unique name
                    if tokens[0] != curdatapoint:
                        name = tokens[0].strip()[:-1]

                        assert name not in self.datapoints

                        self.datapoints[name] = address
                        curdatapoint = name
                        tokens = tokens[1:]

                    for token in tokens:
                        if defining == 'array':
                            if tokens[i][-1] == ',':
                                num = self.getValue(tokens[i][:-1])
                            else:
                                num = self.getValue(tokens[i])
                                defining = None

                            self.data += [0] * num
                            address += num

                        elif defining == 'word':
                            if tokens[i][-1] == ',':
                                self.data.append(self.getValue(tokens[i][:-1]))
                            else:
                                self.data.append(self.getValue(tokens[i]))
                                defining = None

                        elif tokens[i] == 'DS':
                            defining = 'array'

                        elif tokens[i] == 'DW':
                            defining = 'word'

                elif segment == 'code':
                    if 'EQU' in tokens:
                        i = tokens.index('EQU')

                        # EQU cannot be the first or last element in tokens
                        assert 0 < i < len(tokens) - 1

                        name = tokens[i - 1].strip()
                        value = self.getValue(tokens[i + 1])

                        # EQU cannot use a name that's already taken
                        assert name not in self.aliases

                        self.aliases[name] = value
                    else:
                        self.code.append(tokens)
                else:
                    raise ValueError("No active segment")

        # replace aliases
        i = 0
        while i < len(self.code):
            instruction = self.code[i]
            j = 0
            while j < len(instruction):
                operand = instruction[j]
                if isinstance(operand, list):
                    k = 0
                    while k < len(operand):
                        if operand[k] in self.aliases:
                            self.code[i][j][k] = self.aliases[operand[k]]
                        elif operand[k] in self.datapoints:
                            self.code[i][j][k] = self.datapoints[operand[k]]
                        k += 1
                elif operand in self.aliases:
                    self.code[i][j] = self.aliases[operand]
                elif operand in self.datapoints:
                    self.code[i][j] = self.datapoints[operand]
                j += 1
            i += 1

    def isValidAddressThing(self, list_):
        if isinstance(list_, int):
            # val
            return True

        if isinstance(list_, str):
            str_ = list_

            # val
            if self.isValue(str_):
                return True

            # reg
            if self.isRegister(str_):
                return True

        elif len(list_) == 1:
            str_ = list_[0]

            # [--reg]
            if str_.startswith('--') and self.isRegister(str_[2:]):
                return True

            # [reg++]
            if str_.startswith('++') and self.isRegister(str_[:-2]):
                return True

            # unofficial: [reg] == [reg + 0]
            if self.isRegister(str_[0]):
                list_.append('+')
                list_.append(0)
                return True

            # unofficial: [[reg]] == [[reg] + 0]
            if str_[-1:0] == '][' and self.isRegister(str_[1:-1]):
                list_.append('+')
                list_.append(0)
                return True

        elif len(list_) == 3:
            if self.isRegister(list_[0]):
                # [reg + reg]
                if list_[1] == '+' and self.isRegister(list_[2]):
                    return True

                # [reg + val]
                if list_[1] == '+' and self.isValue(list_[2]):
                    return True

                # unofficial: [reg - val] = [reg + -val]
                if list_[1] == '-' and self.isValue(list_[2]):
                    list_[2] = -self.getValue(list_[2])
                    return True

            elif list_[0][0] == '[' and list_[0][3] == ']' and self.isRegister(list_[0][1:3]):
                # [[reg] + reg]
                if list_[1] == '+' and self.isRegister(list_[2]):
                    return True

                # [[reg] + val]
                if list_[1] == '+' and self.isValue(list_[2]):
                    return True

                # unofficial: [[reg] - val] = [[reg] + -val]
                if list_[1] == '-' and self.isValue(list_[2]):
                    list_[2] = -self.getValue(list_[2])
                    return True

        return False

    def getAddressingMode(self, list_) -> base.AddressingMode:
        if isinstance(list_, int):
            # val - mode 0
            return base.AddressingMode.VALUE

        if isinstance(list_, str):
            str_ = list_

            # val - mode 0
            if self.isValue(str_):
                return base.AddressingMode.VALUE

            # reg - mode 1
            if self.isRegister(str_):
                return base.AddressingMode.REGISTER

        elif len(list_) == 1:
            str_ = list_[0]

            # [--reg] - mode 5
            if str_[:2] == '--' and self.isRegister(str_[2:]):
                return base.AddressingMode.AUTO_PRE_DEC

            # [reg++] - mode 4
            if str_[-2:] == '++' and self.isRegister(str_[:-2]):
                return base.AddressingMode.AUTO_POST_INC

        elif len(list_) == 3:
            if self.isRegister(list_[0]):
                # [reg + reg] - mode 3
                if list_[1] == '+' and self.isRegister(list_[2]):
                    return base.AddressingMode.REG_INDEXED

                # [reg + val] - mode 2
                if list_[1] == '+' and self.isValue(list_[2]):
                    return base.AddressingMode.INDEXED

            elif list_[0][0] == '[' and list_[0][3] == ']' and self.isRegister(list_[0][1:3]):
                # [[reg] + reg]
                if list_[1] == '+' and self.isRegister(list_[2]):
                    return base.AddressingMode.IND_REG_INDEXED

                # [[reg] + val]
                if list_[1] == '+' and self.isValue(list_[2]):
                    return base.AddressingMode.IND_INDEXED

        raise ValueError(f"Cannot determine addressing mode of {list_!r}")


    def getValue(self, str_):
        if isinstance(str_, int):
            return str_

        if str_[0] == '%':
            # binary
            base = 2
            str_ = str_[1:]
        elif str_[0] == '$':
            # hexadecimal
            base = 16
            str_ = str_[1:]
        else:
            base = 10

        return int(str_, base)


    def isValue(self, str_):
        if isinstance(str_, int):
            return True

        if str_[0] not in '%$':
            # decimal
            allowed = '0123456789'
        elif str_[0] == '%':
            # binary
            allowed = '01'
            str_ = str_[1:]
        else:
            # hexadecimal
            allowed = '0123456789abcdef'
            str_ = str_[1:].lower()

        for d in str_:
            if d not in allowed:
                return False

        return True


    def getRegister(self, str_):
        # remove all whitespace and make the string lowercase
        str_ = ''.join(str_.lower().split())

        if str_ in ['gb', 'sp']:
            return (str_ == 'sp') + 6

        try:
            n = int(str_[-1])
        except ValueError:
            raise ValueError(f"Could not parse register {str_!r}")

        if n < 0 or 7 < n:
            raise ValueError('invalid register %s' % str_)

        return n


    def isRegister(self, str_):
        if not isinstance(str_, str):
            return False

        str_ = ''.join(str_.lower().split())

        return (len(str_) == 2) and ((str_ in ['gb', 'sp']) or (str_[0].lower() == 'r' and 0 <= int(str_[-1]) <= 7))
