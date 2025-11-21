import string
import random

def generate_room_code(length=6):
    # Alfabeto sin caracteres ambiguos
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))
