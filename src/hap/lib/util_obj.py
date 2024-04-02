class Result:
    pass


class ValidationResult(Result):
    def __init__(self, valid: bool, message: str):
        self.valid = valid
        self.message = message
