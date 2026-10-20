from package.api import create_user


def test_create_user():
    assert create_user({"name": "Ada"})["name"] == "Ada"
