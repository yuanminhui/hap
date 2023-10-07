def remove_suffix_containing(string: str, suffix: str) -> str:
    i = string.rfind(suffix)
    str = string[:i] if i != -1 else string
    return str
