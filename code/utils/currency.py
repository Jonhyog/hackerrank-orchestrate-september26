from enum import Enum


class Currency(str, Enum):
    EUR = "EUR"
    IDR = "IDR"
    INR = "INR"
    USD = "USD"
    ZAR = "ZAR"
