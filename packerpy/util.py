
def parse_list(raw, delimiter=","):
    if isinstance(raw, list):
        return raw
    elif isinstance(raw, str):
        return raw.split(delimiter)
    else:
        raise ValueError(f"Invalid type {type(raw)}. Only list or str allowed.")
