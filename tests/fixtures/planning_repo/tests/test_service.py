from package.service import process_label


def test_process_label():
    assert process_label(" Ada ") == "ada"
