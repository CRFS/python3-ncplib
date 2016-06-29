import unittest
from ncplib import uint


UINT_VALUES = [0, 10, 4294967295]

INVALID_UINT_VALUES = [-1, 4294967296]


class UintTestCase(unittest.TestCase):

    def testValidUint(self):
        for value in UINT_VALUES:
            with self.subTest(value=value):
                self.assertIsInstance(uint(value), uint)

    def testInvalidUint(self):
        for value in INVALID_UINT_VALUES:
            with self.subTest(value=value), self.assertRaises(ValueError):
                uint(value)
