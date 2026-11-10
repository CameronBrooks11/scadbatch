import pytest

from scadbatch.params import ScadRange, coerce_cell, construct_d_flags, to_scad_literal


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, "true"),
        (False, "false"),
        (5, "5"),
        (-3, "-3"),
        (2.5, "2.5"),
        (1e-05, "1e-05"),
        (10.0, "10.0"),
        ("hello", '"hello"'),
        ("", '""'),
        ('say "hi"', '"say \\"hi\\""'),
        ("back\\slash", '"back\\\\slash"'),
        ("two\nlines", '"two\\nlines"'),
        ([1, 2, 3], "[1, 2, 3]"),
        ([[0, 0], [1, 1]], "[[0, 0], [1, 1]]"),
        (["a", True, None, 2.5], '["a", true, undef, 2.5]'),
        ((1, 2), "[1, 2]"),
        ([], "[]"),
        (None, "undef"),
        (ScadRange(0, 10), "[0 : 10]"),
        (ScadRange(0, 10, 2), "[0 : 2 : 10]"),
    ],
)
def test_to_scad_literal(value, expected):
    assert to_scad_literal(value) == expected


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_floats_are_rejected(value):
    with pytest.raises(ValueError, match="non-finite"):
        to_scad_literal(value)


def test_unsupported_types_are_rejected():
    with pytest.raises(TypeError, match="dict"):
        to_scad_literal({"a": 1})


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("true", True),
        ("False", False),
        (" TRUE ", True),
        ("undef", None),
        ("12", 12),
        ("-7", -7),
        ("2.5", 2.5),
        ("2.50", 2.5),
        (".5", 0.5),
        ("1e3", 1000.0),
        (" 12 ", 12),
        ("007", 7),  # numeric grammar wins; quote it to keep the string
        ('"007"', "007"),
        ('"true"', "true"),
        ('""', ""),
        ("hello", "hello"),
        ("Welcome to...", "Welcome to..."),
        ("inf", "inf"),  # not a number in OpenSCAD's grammar
        ("nan", "nan"),
        ("1.2.3", "1.2.3"),
        ("[1,2,3]", [1, 2, 3]),
        ("[ 1 , 2 ]", [1, 2]),
        ("[[0,0],[1,1]]", [[0, 0], [1, 1]]),
        ('["a", "b c"]', ["a", "b c"]),
        ("[true, undef, -1.5e2]", [True, None, -150.0]),
        ("[]", []),
        ('["quote\\"d"]', ['quote"d']),
        ('["a\\nb"]', ["a\nb"]),  # OpenSCAD escape semantics inside vector literals
        ('["c:\\\\dir"]', ["c:\\dir"]),
        ('["\\u00e9\\x41\\U01F600"]', ["\u00e9A\U0001f600"]),
        ('["\\q"]', ["\\q"]),  # unknown escape kept as written
        ("[1, 2,]", [1, 2]),  # trailing comma, as OpenSCAD allows
        ("[0:10]", ScadRange(0, 10)),
        ("[0 : 2 : 10]", ScadRange(0, 10, 2)),
        ("[-1.5:0.5:1.5]", ScadRange(-1.5, 1.5, 0.5)),
    ],
)
def test_coerce_cell(text, expected):
    assert coerce_cell(text) == expected


def test_coerce_cell_keeps_plain_strings_verbatim():
    assert coerce_cell("  padded  ") == "  padded  "


@pytest.mark.parametrize(
    "text",
    [
        "[1, 2",
        "[1 2]",
        "[,]",
        '["open]',
        "[1] x",
        "[1,,2]",
        "[abc]",
        "[1+2, 3]",  # expressions are not literals
        "[1:2:3:4]",
        "[1:2, 3]",
        '["\\u12"]',
    ],
)
def test_malformed_vectors_are_rejected(text):
    with pytest.raises(ValueError, match="Invalid vector"):
        coerce_cell(text)


def test_out_of_range_number_is_named_as_such():
    with pytest.raises(ValueError, match="'1e400' is out of range"):
        coerce_cell("1e400")


def test_deep_nesting_is_a_value_error():
    with pytest.raises(ValueError, match="nesting too deep"):
        coerce_cell("[" * 5000 + "]" * 5000)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, "-Dk=true"),
        (5, "-Dk=5"),
        (2.5, "-Dk=2.5"),
        ("true", "-Dk=true"),
        ("12", "-Dk=12"),
        ("hello", '-Dk="hello"'),
        ('"007"', '-Dk="007"'),
        ('say "hi"', '-Dk="say \\"hi\\""'),
        ("[1,2,3]", "-Dk=[1, 2, 3]"),
        ([1, "a"], '-Dk=[1, "a"]'),
        (None, "-Dk=undef"),
        ("undef", "-Dk=undef"),
    ],
)
def test_construct_d_flags_serialization(value, expected):
    assert construct_d_flags({"k": value}) == [expected]


def test_exported_filename_is_not_a_parameter():
    assert construct_d_flags({"exported_filename": "part_a", "width": 10}) == ["-Dwidth=10"]


def test_preserves_parameter_order():
    assert construct_d_flags({"b": 1, "a": 2, "c": 3}) == ["-Db=1", "-Da=2", "-Dc=3"]


def test_malformed_vector_in_parameters_names_the_parameter():
    with pytest.raises(ValueError, match="Parameter 'pts': Invalid vector"):
        construct_d_flags({"pts": "[1, 2"})


def _nested(depth, innermost=1):
    """A vector nested `depth` deep, built in Python: json.loads cannot deliver one this
    deep on every interpreter, and the point is the serializer, not the reader."""
    value = innermost
    for _ in range(depth):
        value = [value]
    return value


def test_a_value_nested_past_the_recursion_limit_reports_rather_than_tracebacks():
    """`to_scad_literal` recurses per level, and `RecursionError` is not a `ValueError`,
    so neither CLI handler caught it and it reached the user as a traceback (#75)."""
    with pytest.raises(ValueError, match="nests too deeply"):
        to_scad_literal(_nested(10_000))


def test_a_deeply_but_not_absurdly_nested_value_still_serializes():
    """The pair matters: a serializer that refused everything would pass the test above."""
    assert to_scad_literal(_nested(50)) == "[" * 50 + "1" + "]" * 50
