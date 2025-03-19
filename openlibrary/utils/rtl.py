import unicodedata

def is_rtl(text):
    """
    Check if the given text is right-to-left (RTL) using Unicode bidirectional properties.
    :param text: str
    :return: bool
    """
    for char in text:
        direction = unicodedata.bidirectional(char)
        if direction in ("R", "AL"):  # 'R' = Right-to-Left, 'AL' = Arabic Letter
            return True
    return False
