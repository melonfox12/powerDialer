import unittest

from tests.test_dialer_session.part_1 import Part1
from tests.test_dialer_session.part_2 import Part2
from tests.test_dialer_session.part_3 import Part3
from tests.test_dialer_session.part_4 import Part4


class DialerSessionTests(Part1, Part2, Part3, Part4, unittest.TestCase):
    pass
