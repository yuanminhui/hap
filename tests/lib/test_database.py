import psycopg2
import pytest
from unittest.mock import mock_open, patch, MagicMock

from hap.lib.config import Config
import hap.lib.database as db


### Test for class `DatabaseConnectionInfo` ###


class TestDatabaseConnectionInfo:
    @pytest.fixture
    def db_conn_info(self):
        return db.DatabaseConnectionInfo(
            host="localhost",
            port=5432,
            user="user",
            password="password",
            dbname="dbname",
        )

    def test_init(self, db_conn_info):
        assert db_conn_info.host == "localhost"
        assert db_conn_info.port == 5432
        assert db_conn_info.user == "user"
        assert db_conn_info.password == "password"
        assert db_conn_info.dbname == "dbname"

    def test_is_complete(self, db_conn_info):
        assert db_conn_info.is_complete()
        db_conn_info.port = None
        assert not db_conn_info.is_complete()

    def test_str(self, db_conn_info):
        expected = "host=localhost port=5432 user=user password=password dbname=dbname"
        assert str(db_conn_info) == expected

    def test_repr(self, db_conn_info):
        expected = "DatabaseConnectionInfo(host=localhost, port=5432, user=user, password=password, dbname=dbname)"
        assert repr(db_conn_info) == expected

    def test_to_dict(self, db_conn_info):
        expected = {
            "host": "localhost",
            "port": 5432,
            "user": "user",
            "password": "password",
            "dbname": "dbname",
        }
        assert db_conn_info.to_dict() == expected

    def test_from_dict(self):
        input_dict = {
            "host": "localhost",
            "port": 5432,
            "user": "user",
            "password": "password",
            "dbname": "dbname",
        }
        conn_info = db.DatabaseConnectionInfo()
        conn_info.from_dict(input_dict)
        assert conn_info.host == "localhost"
        assert conn_info.port == 5432
        assert conn_info.user == "user"
        assert conn_info.password == "password"
        assert conn_info.dbname == "dbname"


### Test for function `get_connection_info` ###


@pytest.fixture
def mock_env_complete(monkeypatch):
    """Mock environment variables with complete information."""
    env_vars = {
        "HAP_DB_HOST": "env_host",
        "HAP_DB_PORT": "5432",
        "HAP_DB_USER": "env_user",
        "HAP_DB_PASSWORD": "env_pass",
        "HAP_DB_DBNAME": "env_dbname",
    }
    for var, value in env_vars.items():
        monkeypatch.setenv(var, value)
    return env_vars


@pytest.fixture
def mock_env_partial(monkeypatch):
    """Mock environment variables with partial information."""
    env_vars = {
        "HAP_DB_HOST": "env_host_partial",
        "HAP_DB_USER": "env_user_partial",
    }
    for var, value in env_vars.items():
        monkeypatch.setenv(var, value)
    return env_vars


@pytest.fixture
def mock_config_complete(mocker):
    """Mock configuration file with complete information."""
    config_values = {
        "db.host": "file_host",
        "db.port": "1234",
        "db.user": "file_user",
        "db.password": "file_pass",
        "db.dbname": "file_dbname",
    }
    mocker.patch.object(Config, "load_from_file")
    mocker.patch.object(
        Config, "get_nested_value", side_effect=lambda key: config_values.get(key)
    )
    return config_values


@pytest.fixture
def mock_config_empty(mocker):
    """Mock an empty configuration file."""
    mocker.patch.object(Config, "load_from_file")
    mocker.patch.object(Config, "get_nested_value", side_effect=lambda key: None)


def test_get_connection_info_env_overrides_config(
    mock_env_complete, mock_config_complete, mocker
):
    """Environment variables override configuration file values."""
    mocker.patch("hap.lib.database.DatabaseConnectionInfo.from_config")
    connection_info = db.get_connection_info()

    for key, expected_value in mock_env_complete.items():
        key = key.lower().replace("hap_db_", "")
        assert (
            connection_info[key] == expected_value
            if key != "port"
            else int(expected_value)
        )


def test_get_connection_info_partial_env(
    mock_env_partial, mock_config_complete, mocker
):
    """Environment variables partially override configuration file values."""
    mocker.patch("hap.lib.database.DatabaseConnectionInfo.from_config")
    connection_info = db.get_connection_info()

    assert connection_info["host"] == mock_env_partial["HAP_DB_HOST"]
    assert connection_info["user"] == mock_env_partial["HAP_DB_USER"]
    assert connection_info["port"] == int(mock_config_complete["db.port"])
    assert connection_info["password"] == mock_config_complete["db.password"]
    assert connection_info["dbname"] == mock_config_complete["db.dbname"]


def test_get_connection_info_config_only(mock_config_complete, mocker):
    """Configuration file provides all connection information if environment variables are missing."""
    mocker.patch("os.environ", return_value={})  # Mock empty environment
    mocker.patch("hap.lib.database.DatabaseConnectionInfo.from_config")

    connection_info = db.get_connection_info()

    for key, expected_value in mock_config_complete.items():
        key = key.replace("db.", "")
        assert (
            connection_info[key] == expected_value
            if key != "port"
            else int(expected_value)
        )


def test_get_connection_info_no_info(mock_config_empty, mocker):
    """No connection information provided by either environment variables or configuration file."""
    mocker.patch("os.environ", return_value={})  # Mock empty environment
    mocker.patch("hap.lib.database.DatabaseConnectionInfo.from_config")

    connection_info = db.get_connection_info()

    expected_keys = ["host", "port", "user", "password", "dbname"]
    for key in expected_keys:
        assert connection_info.get(key) is None


### Test for function `test_connection` ###


@pytest.fixture
def mock_connection_info():
    """Provide mock database connection information."""
    return {
        "host": "localhost",
        "port": 5432,
        "user": "test_user",
        "password": "test_password",
        "dbname": "test_db",
    }


def test_test_connection_success(mock_connection_info, mocker):
    """Test successful database connection."""
    mock_connect = mocker.patch("psycopg2.connect")
    connection_info = db.test_connection(mock_connection_info)

    mock_connect.assert_called_once_with(**mock_connection_info)
    assert connection_info == mock_connection_info


def test_test_connection_incomplete_info():
    """Test connection with incomplete information raises ValueError."""
    incomplete_info = {
        "host": "localhost",
        "user": "test_user",
        # Missing 'port', 'password', and 'dbname'
    }
    with pytest.raises(ValueError):
        db.test_connection(incomplete_info)


def test_test_connection_failure(mock_connection_info, mocker):
    """Test failure to connect raises psycopg2.OperationalError."""
    mock_connect = mocker.patch(
        "psycopg2.connect", side_effect=psycopg2.OperationalError
    )

    with pytest.raises(psycopg2.OperationalError):
        db.test_connection(mock_connection_info)

    mock_connect.assert_called_once_with(**mock_connection_info)


### Test for function `connect` ###


def test_connect_success(mock_connection_info, mocker):
    """Test successful database connection returns a connection object."""
    mock_connect = mocker.patch("psycopg2.connect")

    conn = db.connect(mock_connection_info)

    mock_connect.assert_called_once_with(**mock_connection_info)
    assert mock_connect.return_value == conn


def test_connect_failure(mock_connection_info, mocker):
    """Test connection failure due to incorrect information raises OperationalError."""
    mock_connect = mocker.patch(
        "psycopg2.connect", side_effect=psycopg2.OperationalError
    )

    with pytest.raises(psycopg2.OperationalError):
        db.connect(mock_connection_info)

    mock_connect.assert_called_once_with(**mock_connection_info)


### Test for function `create_tables_if_not_exist` ###


def test_create_tables_if_not_exist_success(mocker):
    """Test that SQL commands are executed correctly from the SQL file."""
    mock_conn = mocker.MagicMock()
    mock_cursor = mock_conn.cursor.return_value
    mock_sql_content = "CREATE TABLES"

    mocker.patch("builtins.open", mocker.mock_open(read_data=mock_sql_content))

    db.create_tables_if_not_exist(mock_conn)

    mocker.patch("builtins.open").assert_called_once_with("create_tables.sql", "r")
    mock_cursor.execute.assert_called_once_with(mock_sql_content)


def test_create_tables_if_not_exist_sql_error(mocker):
    """Test handling of SQL execution errors."""
    mock_conn = mocker.MagicMock()
    mock_cursor = mock_conn.cursor.return_value
    mock_cursor.execute.side_effect = psycopg2.Error

    mocker.patch("builtins.open", mocker.mock_open(read_data="INVALID SQL;"))

    with pytest.raises(psycopg2.Error):
        db.create_tables_if_not_exist(mock_conn)

    mocker.patch("builtins.open").assert_called_once_with("create_tables.sql", "r")
    mock_conn.rollback.assert_called_once()


def test_create_tables_if_not_exist_file_not_found(mocker):
    """Test handling of the SQL file not being found."""
    mock_conn = mocker.MagicMock()

    mocker.patch("builtins.open", mocker.mock_open())
    mock_open = mocker.patch("builtins.open", side_effect=FileNotFoundError)

    with pytest.raises(FileNotFoundError):
        db.create_tables_if_not_exist(mock_conn)

    mock_open.assert_called_once_with("create_tables.sql", "r")


### Test for function `get_next_id_from_table` ###


@pytest.fixture
def mock_conn_and_cursor(mocker):
    """Mock the database connection and cursor."""
    mock_conn = mocker.MagicMock()
    mock_cursor = mock_conn.cursor.return_value
    return mock_conn, mock_cursor


def test_get_next_id_from_table_with_data(mock_conn_and_cursor):
    """Test retrieving the next ID from a table with existing records."""
    mock_conn, mock_cursor = mock_conn_and_cursor
    mock_cursor.fetchone.return_value = [5]  # Simulate the current max ID is 5

    next_id = db.get_next_id_from_table(mock_conn, "test_table")

    assert next_id == 6
    mock_cursor.execute.assert_called_with("SELECT MAX(id) FROM test_table")


def test_get_next_id_from_table_empty_table(mock_conn_and_cursor):
    """Test retrieving the next ID from an empty table."""
    mock_conn, mock_cursor = mock_conn_and_cursor
    mock_cursor.fetchone.return_value = [None]  # Simulate an empty table

    next_id = db.get_next_id_from_table(mock_conn, "test_table")

    assert next_id == 1
    mock_cursor.execute.assert_called_with("SELECT MAX(id) FROM test_table")


def test_get_next_id_from_table_sql_error(mock_conn_and_cursor):
    """Test handling of SQL execution errors."""
    mock_conn, mock_cursor = mock_conn_and_cursor
    mock_cursor.execute.side_effect = psycopg2.Error

    with pytest.raises(psycopg2.Error):
        db.get_next_id_from_table(mock_conn, "test_table")
